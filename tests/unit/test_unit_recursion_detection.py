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
from tasktree.state import StateManager


class TestCallChainEntryFormatting(unittest.TestCase):
    """Tests for call chain entry formatting helper."""

    def test_make_call_chain_entry_basic(self):
        """Test basic call chain entry creation."""
        entry = Executor._make_call_chain_entry("abc123", "my-task")
        self.assertEqual(entry, "abc123:my-task")

    def test_make_call_chain_entry_with_args_hash(self):
        """Test call chain entry with cache key including args hash."""
        entry = Executor._make_call_chain_entry("abc123__def456", "my-task")
        self.assertEqual(entry, "abc123__def456:my-task")

    def test_make_call_chain_entry_with_fqn(self):
        """Test call chain entry with fully-qualified task name."""
        entry = Executor._make_call_chain_entry("abc123", "other.build")
        self.assertEqual(entry, "abc123:other.build")


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
            output_type=TaskOutputTypes.ON_ERR, logger=logger_stub
        )
        self.state_manager = StateManager(self.project_root)

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

        executor = Executor(
            self.recipe, self.state_manager, logger_stub, make_process_runner
        )

        # Mock subprocess execution
        with patch.object(executor, "_run_command_as_script"):
            # Should not raise - no cycle
            executor._run_task(task, {}, self.process_runner)

    @patch.dict(os.environ, {"TT_CALL_CHAIN": "parent-task"}, clear=False)
    def test_call_chain_single_task(self):
        """Test call chain with a single parent task."""
        task = Task(name="child-task", cmd="echo 'child'")
        self.recipe.tasks["child-task"] = task

        executor = Executor(
            self.recipe, self.state_manager, logger_stub, make_process_runner
        )

        # Simulate being called from parent-task (set via @patch.dict)
        with patch.object(executor, "_run_command_as_script"):
            # Should not raise - no cycle
            executor._run_task(task, {}, self.process_runner)

    @patch.dict(os.environ, {"TT_CALL_CHAIN": "parent-task,child-task"}, clear=False)
    def test_call_chain_multiple_tasks(self):
        """Test call chain with multiple parent tasks."""
        task = Task(name="grandchild-task", cmd="echo 'grandchild'")
        self.recipe.tasks["grandchild-task"] = task

        executor = Executor(
            self.recipe, self.state_manager, logger_stub, make_process_runner
        )

        # Simulate being called from parent->child (set via @patch.dict)
        with patch.object(executor, "_run_command_as_script"):
            # Should not raise - no cycle
            executor._run_task(task, {}, self.process_runner)

    def test_parse_call_chain_with_cache_keys(self):
        """Test parsing call chain entries in 'cache_key:task_name' format."""
        chain = "abc123:task-a,def456:task-b,ghi789:task-c"
        result = Executor._parse_call_chain(chain)

        expected = [
            ("abc123", "task-a"),
            ("def456", "task-b"),
            ("ghi789", "task-c"),
        ]
        self.assertEqual(result, expected)

    def test_parse_call_chain_empty(self):
        """Test parsing empty call chain."""
        result = Executor._parse_call_chain("")
        self.assertEqual(result, [])

    def test_parse_call_chain_with_whitespace(self):
        """Test parsing call chain handles whitespace correctly."""
        chain = "abc123:task-a , def456:task-b  ,  ghi789:task-c"
        result = Executor._parse_call_chain(chain)

        expected = [
            ("abc123", "task-a"),
            ("def456", "task-b"),
            ("ghi789", "task-c"),
        ]
        self.assertEqual(result, expected)


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
            output_type=TaskOutputTypes.ON_ERR, logger=logger_stub
        )
        self.state_manager = StateManager(self.project_root)

    def tearDown(self):
        """Clean up test fixtures."""
        self.tmpdir.cleanup()

    def test_direct_recursion_detected(self):
        """Test that direct recursion (A calls A) is detected."""
        task = Task(name="self-caller", cmd="tt self-caller")
        self.recipe.tasks["self-caller"] = task

        executor = Executor(
            self.recipe, self.state_manager, logger_stub, make_process_runner
        )

        # Generate cache key for this task
        cache_key = executor._cache_key(task, {})
        call_chain = executor._make_call_chain_entry(cache_key, "self-caller")

        # Simulate task calling itself
        with patch.dict(os.environ, {"TT_CALL_CHAIN": call_chain}, clear=False):
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
            output_type=TaskOutputTypes.ON_ERR, logger=logger_stub
        )
        self.state_manager = StateManager(self.project_root)

    def tearDown(self):
        """Clean up test fixtures."""
        self.tmpdir.cleanup()

    def test_indirect_recursion_2_tasks(self):
        """Test that 2-task cycle (A → B → A) is detected."""
        task_a = Task(name="task-a", cmd="tt task-b")
        task_b = Task(name="task-b", cmd="tt task-a")
        self.recipe.tasks["task-a"] = task_a
        self.recipe.tasks["task-b"] = task_b

        executor = Executor(
            self.recipe, self.state_manager, logger_stub, make_process_runner
        )

        # Build call chain: task-a → task-b (simulating we're in task-b about to call task-a)
        key_a = executor._cache_key(task_a, {})
        key_b = executor._cache_key(task_b, {})
        entry_a = executor._make_call_chain_entry(key_a, "task-a")
        entry_b = executor._make_call_chain_entry(key_b, "task-b")
        call_chain = f"{entry_a},{entry_b}"

        # Simulate: task-a calls task-b, task-b tries to call task-a
        with patch.dict(os.environ, {"TT_CALL_CHAIN": call_chain}, clear=False):
            with self.assertRaises(ExecutionError) as cm:
                executor._run_task(task_a, {}, self.process_runner)

        error_msg = str(cm.exception)
        self.assertIn("Recursion detected", error_msg)
        self.assertIn("task-a → task-b → task-a", error_msg)

    def test_indirect_recursion_3_tasks(self):
        """Test that 3-task cycle (A → B → C → A) is detected."""
        task_a = Task(name="task-a", cmd="tt task-b")
        task_b = Task(name="task-b", cmd="tt task-c")
        task_c = Task(name="task-c", cmd="tt task-a")
        self.recipe.tasks["task-a"] = task_a
        self.recipe.tasks["task-b"] = task_b
        self.recipe.tasks["task-c"] = task_c

        executor = Executor(
            self.recipe, self.state_manager, logger_stub, make_process_runner
        )

        # Build call chain: task-a → task-b → task-c
        key_a = executor._cache_key(task_a, {})
        key_b = executor._cache_key(task_b, {})
        key_c = executor._cache_key(task_c, {})
        entry_a = executor._make_call_chain_entry(key_a, "task-a")
        entry_b = executor._make_call_chain_entry(key_b, "task-b")
        entry_c = executor._make_call_chain_entry(key_c, "task-c")
        call_chain = f"{entry_a},{entry_b},{entry_c}"

        # Simulate: task-a → task-b → task-c → task-a (trying to call task-a again)
        with patch.dict(os.environ, {"TT_CALL_CHAIN": call_chain}, clear=False):
            with self.assertRaises(ExecutionError) as cm:
                executor._run_task(task_a, {}, self.process_runner)

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
            output_type=TaskOutputTypes.ON_ERR, logger=logger_stub
        )
        self.state_manager = StateManager(self.project_root)

    def tearDown(self):
        """Clean up test fixtures."""
        self.tmpdir.cleanup()

    @patch.dict(os.environ, {"TT_CALL_CHAIN": "task-a,task-b,task-c,task-d"}, clear=False)
    def test_deep_chain_no_cycle(self):
        """Test that deep chain (A → B → C → D → E) without cycle succeeds."""
        task = Task(name="task-e", cmd="echo 'task-e'")
        self.recipe.tasks["task-e"] = task

        executor = Executor(
            self.recipe, self.state_manager, logger_stub, make_process_runner
        )

        # Simulate: task-a → task-b → task-c → task-d → task-e (set via @patch.dict)
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
            output_type=TaskOutputTypes.ON_ERR, logger=logger_stub
        )
        self.state_manager = StateManager(self.project_root)

    def tearDown(self):
        """Clean up test fixtures."""
        self.tmpdir.cleanup()

    def test_error_message_shows_full_cycle(self):
        """Test that error message shows the full cycle path."""
        test_task = Task(name="test", cmd="tt lint")
        lint_task = Task(name="lint", cmd="tt build")
        build_task = Task(name="build", cmd="tt build")
        self.recipe.tasks["test"] = test_task
        self.recipe.tasks["lint"] = lint_task
        self.recipe.tasks["build"] = build_task

        executor = Executor(
            self.recipe, self.state_manager, logger_stub, make_process_runner
        )

        # Build call chain: test → lint → build
        key_test = executor._cache_key(test_task, {})
        key_lint = executor._cache_key(lint_task, {})
        key_build = executor._cache_key(build_task, {})
        entry_test = executor._make_call_chain_entry(key_test, "test")
        entry_lint = executor._make_call_chain_entry(key_lint, "lint")
        entry_build = executor._make_call_chain_entry(key_build, "build")
        call_chain = f"{entry_test},{entry_lint},{entry_build}"

        # Simulate: test → lint → build → build (cycle starts at build)
        with patch.dict(os.environ, {"TT_CALL_CHAIN": call_chain}, clear=False):
            with self.assertRaises(ExecutionError) as cm:
                executor._run_task(build_task, {}, self.process_runner)

        error_msg = str(cm.exception)
        # Should show cycle starting from where it was first seen
        self.assertIn("build → build", error_msg)

    def test_error_message_shows_task_name(self):
        """Test that error message highlights the problematic task."""
        task = Task(name="my-task", cmd="tt my-task")
        self.recipe.tasks["my-task"] = task

        executor = Executor(
            self.recipe, self.state_manager, logger_stub, make_process_runner
        )

        # Build call chain with my-task already in it
        cache_key = executor._cache_key(task, {})
        call_chain = executor._make_call_chain_entry(cache_key, "my-task")

        # Simulate: my-task calling itself
        with patch.dict(os.environ, {"TT_CALL_CHAIN": call_chain}, clear=False):
            with self.assertRaises(ExecutionError) as cm:
                executor._run_task(task, {}, self.process_runner)

        error_msg = str(cm.exception)
        self.assertIn("Task 'my-task'", error_msg)
        self.assertIn("already running", error_msg)


class TestSameTaskDifferentArgs(unittest.TestCase):
    """Test that same task with different args does NOT trigger recursion."""

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
            output_type=TaskOutputTypes.ON_ERR, logger=logger_stub
        )
        self.state_manager = StateManager(self.project_root)

    def tearDown(self):
        """Clean up test fixtures."""
        self.tmpdir.cleanup()

    def test_same_task_different_args_no_recursion(self):
        """Test that build(mode=debug) → test → build(mode=release) does not trigger recursion."""
        # Create task with args
        task = Task(
            name="build",
            cmd="echo 'building'",
            args=[{"mode": {"type": "str", "default": "debug"}}],
        )
        self.recipe.tasks["build"] = task

        executor = Executor(
            self.recipe, self.state_manager, logger_stub, make_process_runner
        )

        # Simulate: build(mode=debug) is already in the chain
        # We're now calling build(mode=release) - different args, should NOT recurse
        debug_cache_key = executor._cache_key(task, {"mode": "debug"})
        debug_entry = executor._make_call_chain_entry(debug_cache_key, "build")

        with patch.dict(os.environ, {"TT_CALL_CHAIN": debug_entry}, clear=False):
            # Mock subprocess execution
            with patch.object(executor, "_run_command_as_script"):
                # Should NOT raise - different args means different cache key
                executor._run_task(task, {"mode": "release"}, self.process_runner)

    def test_same_task_same_args_does_recurse(self):
        """Test that build(mode=debug) → test → build(mode=debug) DOES trigger recursion."""
        # Create task with args
        task = Task(
            name="build",
            cmd="echo 'building'",
            args=[{"mode": {"type": "str", "default": "debug"}}],
        )
        self.recipe.tasks["build"] = task

        executor = Executor(
            self.recipe, self.state_manager, logger_stub, make_process_runner
        )

        # Simulate: build(mode=debug) is already in the chain
        # We're now calling build(mode=debug) again - same args, SHOULD recurse
        debug_cache_key = executor._cache_key(task, {"mode": "debug"})
        debug_entry = executor._make_call_chain_entry(debug_cache_key, "build")

        with patch.dict(os.environ, {"TT_CALL_CHAIN": debug_entry}, clear=False):
            # Should raise ExecutionError for recursion
            with self.assertRaises(ExecutionError) as cm:
                executor._run_task(task, {"mode": "debug"}, self.process_runner)

            error_msg = str(cm.exception)
            self.assertIn("Recursion detected", error_msg)
            self.assertIn("build → build", error_msg)


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
            output_type=TaskOutputTypes.ON_ERR, logger=logger_stub
        )
        self.state_manager = StateManager(self.project_root)

    def tearDown(self):
        """Clean up test fixtures."""
        self.tmpdir.cleanup()

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
        # Create all the tasks in the chain
        task_root = Task(name="root", cmd="echo 'root'")
        task_b = Task(name="task-b", cmd="echo 'task-b'")
        task_e = Task(name="task-e", cmd="echo 'task-e'")
        task_h = Task(name="task-h", cmd="echo 'task-h'")
        task_i = Task(name="task-i", cmd="echo 'task-i'")
        task_j = Task(name="task-j", cmd="echo 'task-j'")
        task_k = Task(name="task-k", cmd="echo 'task-k'")

        self.recipe.tasks["root"] = task_root
        self.recipe.tasks["task-b"] = task_b
        self.recipe.tasks["task-e"] = task_e
        self.recipe.tasks["task-h"] = task_h
        self.recipe.tasks["task-i"] = task_i
        self.recipe.tasks["task-j"] = task_j
        self.recipe.tasks["task-k"] = task_k

        executor = Executor(
            self.recipe, self.state_manager, logger_stub, make_process_runner
        )

        # Build call chain: root → task-b → task-e → task-h → task-i → task-j → task-k
        key_root = executor._cache_key(task_root, {})
        key_b = executor._cache_key(task_b, {})
        key_e = executor._cache_key(task_e, {})
        key_h = executor._cache_key(task_h, {})
        key_i = executor._cache_key(task_i, {})
        key_j = executor._cache_key(task_j, {})
        key_k = executor._cache_key(task_k, {})

        entries = [
            executor._make_call_chain_entry(key_root, "root"),
            executor._make_call_chain_entry(key_b, "task-b"),
            executor._make_call_chain_entry(key_e, "task-e"),
            executor._make_call_chain_entry(key_h, "task-h"),
            executor._make_call_chain_entry(key_i, "task-i"),
            executor._make_call_chain_entry(key_j, "task-j"),
            executor._make_call_chain_entry(key_k, "task-k"),
        ]
        call_chain = ",".join(entries)

        # Simulate: K tries to call E again (E is already in chain)
        with patch.dict(os.environ, {"TT_CALL_CHAIN": call_chain}, clear=False):
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
            output_type=TaskOutputTypes.ON_ERR, logger=logger_stub
        )
        self.state_manager = StateManager(self.project_root)

    def tearDown(self):
        """Clean up test fixtures."""
        self.tmpdir.cleanup()

    def test_fqn_without_import_prefix(self):
        """Test that local task names have no prefix."""
        task = Task(name="local-task", cmd="echo 'local'")
        self.recipe.tasks["local-task"] = task

        executor = Executor(
            self.recipe, self.state_manager, logger_stub, make_process_runner
        )

        # Build call chain with local-task already in it
        cache_key = executor._cache_key(task, {})
        call_chain = executor._make_call_chain_entry(cache_key, "local-task")

        # Task name should be used as-is for local tasks
        with patch.dict(os.environ, {"TT_CALL_CHAIN": call_chain}, clear=False):
            with self.assertRaises(ExecutionError) as cm:
                executor._run_task(task, {}, self.process_runner)

        error_msg = str(cm.exception)
        self.assertIn("local-task → local-task", error_msg)

    def test_fqn_with_import_prefix(self):
        """Test that imported task names include prefix."""
        # Simulate an imported task with prefix
        task = Task(name="other.build", cmd="echo 'build'")
        self.recipe.tasks["other.build"] = task

        executor = Executor(
            self.recipe, self.state_manager, logger_stub, make_process_runner
        )

        # Build call chain with imported task already in it
        cache_key = executor._cache_key(task, {})
        call_chain = executor._make_call_chain_entry(cache_key, "other.build")

        # Simulate calling imported task that recursively calls itself
        with patch.dict(os.environ, {"TT_CALL_CHAIN": call_chain}, clear=False):
            with self.assertRaises(ExecutionError) as cm:
                executor._run_task(task, {}, self.process_runner)

        error_msg = str(cm.exception)
        self.assertIn("other.build → other.build", error_msg)


if __name__ == "__main__":
    unittest.main()
