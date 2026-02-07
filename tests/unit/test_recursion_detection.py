"""Tests for recursion detection in nested task invocations (Phase 3)."""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from helpers.logging import logger_stub
from tasktree.executor import Executor, ExecutionError
from tasktree.parser import Recipe, Task
from tasktree.process_runner import TaskOutputTypes, make_process_runner


class TestCallChainParsing(unittest.TestCase):
    """Tests for TT_CALL_CHAIN parsing and validation."""

    def setUp(self):
        """Set up test fixtures."""
        self.tmpdir = TemporaryDirectory()
        self.project_root = Path(self.tmpdir.name)
        self.recipe = Recipe(
            project_root=self.project_root,
            recipe_path=self.project_root / "tasktree.yaml",
            tasks={},
            runners={},
            variables={},
        )
        self.process_runner = make_process_runner(
            task_output=TaskOutputTypes.ON_ERROR, logger=logger_stub
        )

    def tearDown(self):
        """Clean up test fixtures."""
        self.tmpdir.cleanup()

    def test_call_chain_empty_on_top_level(self):
        """Test that call chain is empty for top-level invocation."""
        # Ensure TT_CALL_CHAIN is not set
        if "TT_CALL_CHAIN" in os.environ:
            del os.environ["TT_CALL_CHAIN"]

        task = Task(name="test-task", cmd="echo 'test'")
        self.recipe.tasks["test-task"] = task

        executor = Executor(self.recipe, force=False, dry_run=False, only=False)

        # Mock subprocess execution
        with patch.object(executor, "_run_command_as_script"):
            # Should not raise - no cycle
            executor._run_task(task, {}, self.process_runner)

    def test_call_chain_single_task(self):
        """Test call chain with a single parent task."""
        task = Task(name="child-task", cmd="echo 'child'")
        self.recipe.tasks["child-task"] = task

        executor = Executor(self.recipe, force=False, dry_run=False, only=False)

        # Simulate being called from parent-task
        os.environ["TT_CALL_CHAIN"] = "parent-task"

        try:
            with patch.object(executor, "_run_command_as_script"):
                # Should not raise - no cycle
                executor._run_task(task, {}, self.process_runner)
        finally:
            del os.environ["TT_CALL_CHAIN"]

    def test_call_chain_multiple_tasks(self):
        """Test call chain with multiple parent tasks."""
        task = Task(name="grandchild-task", cmd="echo 'grandchild'")
        self.recipe.tasks["grandchild-task"] = task

        executor = Executor(self.recipe, force=False, dry_run=False, only=False)

        # Simulate being called from parent->child
        os.environ["TT_CALL_CHAIN"] = "parent-task,child-task"

        try:
            with patch.object(executor, "_run_command_as_script"):
                # Should not raise - no cycle
                executor._run_task(task, {}, self.process_runner)
        finally:
            del os.environ["TT_CALL_CHAIN"]


class TestDirectRecursion(unittest.TestCase):
    """Tests for direct recursion detection."""

    def setUp(self):
        """Set up test fixtures."""
        self.tmpdir = TemporaryDirectory()
        self.project_root = Path(self.tmpdir.name)
        self.recipe = Recipe(
            project_root=self.project_root,
            recipe_path=self.project_root / "tasktree.yaml",
            tasks={},
            runners={},
            variables={},
        )
        self.process_runner = make_process_runner(
            task_output=TaskOutputTypes.ON_ERROR, logger=logger_stub
        )

    def tearDown(self):
        """Clean up test fixtures."""
        self.tmpdir.cleanup()
        if "TT_CALL_CHAIN" in os.environ:
            del os.environ["TT_CALL_CHAIN"]

    def test_direct_recursion_detected(self):
        """Test that direct recursion (A calls A) is detected."""
        task = Task(name="self-caller", cmd="tt self-caller")
        self.recipe.tasks["self-caller"] = task

        executor = Executor(self.recipe, force=False, dry_run=False, only=False)

        # Simulate task calling itself
        os.environ["TT_CALL_CHAIN"] = "self-caller"

        with self.assertRaises(ExecutionError) as cm:
            executor._run_task(task, {}, self.process_runner)

        # Verify error message
        error_msg = str(cm.exception)
        self.assertIn("Recursion detected", error_msg)
        self.assertIn("self-caller → self-caller", error_msg)
        self.assertIn("infinite loop", error_msg)


class TestIndirectRecursion(unittest.TestCase):
    """Tests for indirect recursion detection."""

    def setUp(self):
        """Set up test fixtures."""
        self.tmpdir = TemporaryDirectory()
        self.project_root = Path(self.tmpdir.name)
        self.recipe = Recipe(
            project_root=self.project_root,
            recipe_path=self.project_root / "tasktree.yaml",
            tasks={},
            runners={},
            variables={},
        )
        self.process_runner = make_process_runner(
            task_output=TaskOutputTypes.ON_ERROR, logger=logger_stub
        )

    def tearDown(self):
        """Clean up test fixtures."""
        self.tmpdir.cleanup()
        if "TT_CALL_CHAIN" in os.environ:
            del os.environ["TT_CALL_CHAIN"]

    def test_indirect_recursion_2_tasks(self):
        """Test that 2-task cycle (A → B → A) is detected."""
        task = Task(name="task-a", cmd="tt task-b")
        self.recipe.tasks["task-a"] = task

        executor = Executor(self.recipe, force=False, dry_run=False, only=False)

        # Simulate: task-a calls task-b, task-b tries to call task-a
        os.environ["TT_CALL_CHAIN"] = "task-a,task-b"

        with self.assertRaises(ExecutionError) as cm:
            executor._run_task(task, {}, self.process_runner)

        error_msg = str(cm.exception)
        self.assertIn("Recursion detected", error_msg)
        self.assertIn("task-a → task-b → task-a", error_msg)

    def test_indirect_recursion_3_tasks(self):
        """Test that 3-task cycle (A → B → C → A) is detected."""
        task = Task(name="task-a", cmd="tt task-b")
        self.recipe.tasks["task-a"] = task

        executor = Executor(self.recipe, force=False, dry_run=False, only=False)

        # Simulate: task-a → task-b → task-c → task-a
        os.environ["TT_CALL_CHAIN"] = "task-a,task-b,task-c"

        with self.assertRaises(ExecutionError) as cm:
            executor._run_task(task, {}, self.process_runner)

        error_msg = str(cm.exception)
        self.assertIn("Recursion detected", error_msg)
        self.assertIn("task-a → task-b → task-c → task-a", error_msg)


class TestDeepChainNoCycle(unittest.TestCase):
    """Tests for deep call chains without cycles."""

    def setUp(self):
        """Set up test fixtures."""
        self.tmpdir = TemporaryDirectory()
        self.project_root = Path(self.tmpdir.name)
        self.recipe = Recipe(
            project_root=self.project_root,
            recipe_path=self.project_root / "tasktree.yaml",
            tasks={},
            runners={},
            variables={},
        )
        self.process_runner = make_process_runner(
            task_output=TaskOutputTypes.ON_ERROR, logger=logger_stub
        )

    def tearDown(self):
        """Clean up test fixtures."""
        self.tmpdir.cleanup()
        if "TT_CALL_CHAIN" in os.environ:
            del os.environ["TT_CALL_CHAIN"]

    def test_deep_chain_no_cycle(self):
        """Test that deep chain (A → B → C → D → E) without cycle succeeds."""
        task = Task(name="task-e", cmd="echo 'task-e'")
        self.recipe.tasks["task-e"] = task

        executor = Executor(self.recipe, force=False, dry_run=False, only=False)

        # Simulate: task-a → task-b → task-c → task-d → task-e
        os.environ["TT_CALL_CHAIN"] = "task-a,task-b,task-c,task-d"

        with patch.object(executor, "_run_command_as_script"):
            # Should not raise - no cycle
            executor._run_task(task, {}, self.process_runner)


class TestErrorMessageFormatting(unittest.TestCase):
    """Tests for error message formatting."""

    def setUp(self):
        """Set up test fixtures."""
        self.tmpdir = TemporaryDirectory()
        self.project_root = Path(self.tmpdir.name)
        self.recipe = Recipe(
            project_root=self.project_root,
            recipe_path=self.project_root / "tasktree.yaml",
            tasks={},
            runners={},
            variables={},
        )
        self.process_runner = make_process_runner(
            task_output=TaskOutputTypes.ON_ERROR, logger=logger_stub
        )

    def tearDown(self):
        """Clean up test fixtures."""
        self.tmpdir.cleanup()
        if "TT_CALL_CHAIN" in os.environ:
            del os.environ["TT_CALL_CHAIN"]

    def test_error_message_shows_full_cycle(self):
        """Test that error message shows the full cycle path."""
        task = Task(name="build", cmd="tt build")
        self.recipe.tasks["build"] = task

        executor = Executor(self.recipe, force=False, dry_run=False, only=False)

        # Simulate: test → lint → build → build (cycle starts at build)
        os.environ["TT_CALL_CHAIN"] = "test,lint,build"

        with self.assertRaises(ExecutionError) as cm:
            executor._run_task(task, {}, self.process_runner)

        error_msg = str(cm.exception)
        # Should show cycle starting from where it was first seen
        self.assertIn("build → build", error_msg)

    def test_error_message_shows_task_name(self):
        """Test that error message highlights the problematic task."""
        task = Task(name="my-task", cmd="tt my-task")
        self.recipe.tasks["my-task"] = task

        executor = Executor(self.recipe, force=False, dry_run=False, only=False)

        os.environ["TT_CALL_CHAIN"] = "my-task"

        with self.assertRaises(ExecutionError) as cm:
            executor._run_task(task, {}, self.process_runner)

        error_msg = str(cm.exception)
        self.assertIn("Task 'my-task'", error_msg)
        self.assertIn("already running", error_msg)


class TestComplexBranchingTopology(unittest.TestCase):
    """Test complex branching topology with 5-member cycle."""

    def setUp(self):
        """Set up test fixtures."""
        self.tmpdir = TemporaryDirectory()
        self.project_root = Path(self.tmpdir.name)
        self.recipe = Recipe(
            project_root=self.project_root,
            recipe_path=self.project_root / "tasktree.yaml",
            tasks={},
            runners={},
            variables={},
        )
        self.process_runner = make_process_runner(
            task_output=TaskOutputTypes.ON_ERROR, logger=logger_stub
        )

    def tearDown(self):
        """Clean up test fixtures."""
        self.tmpdir.cleanup()
        if "TT_CALL_CHAIN" in os.environ:
            del os.environ["TT_CALL_CHAIN"]

    def test_complex_branching_topology_with_5_member_cycle(self):
        """
        Test complex branching topology with 5-member cycle.

        Topology:
             root
            /    \\
           A      B
          / \\    / \\
         C   D  E   F
          \\ /    \\ /
           G      H
           |      |
           I ─────┘
           |
           J
           |
           K ─────> E  (creates 5-member cycle: E → H → I → J → K → E)

        Execution flow:
        1. root calls A and B
        2. A calls C and D
        3. B calls E and F
        4. C and D both call G
        5. E and F both call H
        6. G calls I
        7. H calls I (I already executed, skips in practice)
        8. I calls J
        9. J calls K
        10. K calls E ← CYCLE DETECTED (E → H → I → J → K → E)

        For this unit test, we simulate the call chain at the point where
        K tries to call E, and E is already in the chain.
        """
        # Create task E (the one that will be detected as recursing)
        task_e = Task(name="task-e", cmd="echo 'task-e'")
        self.recipe.tasks["task-e"] = task_e

        executor = Executor(self.recipe, force=False, dry_run=False, only=False)

        # Simulate the call chain: root → B → E → H → I → J → K
        # Now K tries to call E again
        os.environ["TT_CALL_CHAIN"] = "root,task-b,task-e,task-h,task-i,task-j,task-k"

        with self.assertRaises(ExecutionError) as cm:
            executor._run_task(task_e, {}, self.process_runner)

        error_msg = str(cm.exception)
        self.assertIn("Recursion detected", error_msg)
        # The cycle should show: task-e → task-h → task-i → task-j → task-k → task-e
        self.assertIn("task-e → task-h → task-i → task-j → task-k → task-e", error_msg)
        self.assertIn("Task 'task-e'", error_msg)
        self.assertIn("infinite loop", error_msg)


class TestFullyQualifiedTaskNames(unittest.TestCase):
    """Tests for fully-qualified task names with import prefixes."""

    def setUp(self):
        """Set up test fixtures."""
        self.tmpdir = TemporaryDirectory()
        self.project_root = Path(self.tmpdir.name)
        self.recipe = Recipe(
            project_root=self.project_root,
            recipe_path=self.project_root / "tasktree.yaml",
            tasks={},
            runners={},
            variables={},
        )
        self.process_runner = make_process_runner(
            task_output=TaskOutputTypes.ON_ERROR, logger=logger_stub
        )

    def tearDown(self):
        """Clean up test fixtures."""
        self.tmpdir.cleanup()
        if "TT_CALL_CHAIN" in os.environ:
            del os.environ["TT_CALL_CHAIN"]

    def test_fqn_without_import_prefix(self):
        """Test that local task names have no prefix."""
        task = Task(name="local-task", cmd="echo 'local'")
        self.recipe.tasks["local-task"] = task

        executor = Executor(self.recipe, force=False, dry_run=False, only=False)

        # Task name should be used as-is for local tasks
        os.environ["TT_CALL_CHAIN"] = "local-task"

        with self.assertRaises(ExecutionError) as cm:
            executor._run_task(task, {}, self.process_runner)

        error_msg = str(cm.exception)
        self.assertIn("local-task → local-task", error_msg)

    def test_fqn_with_import_prefix(self):
        """Test that imported task names include prefix."""
        # Simulate an imported task with prefix
        task = Task(name="other.build", cmd="echo 'build'")
        self.recipe.tasks["other.build"] = task

        executor = Executor(self.recipe, force=False, dry_run=False, only=False)

        # Simulate calling imported task that recursively calls itself
        os.environ["TT_CALL_CHAIN"] = "other.build"

        with self.assertRaises(ExecutionError) as cm:
            executor._run_task(task, {}, self.process_runner)

        error_msg = str(cm.exception)
        self.assertIn("other.build → other.build", error_msg)


if __name__ == "__main__":
    unittest.main()
