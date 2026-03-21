"""Unit tests for runner definition tracking."""

import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from helpers.logging import logger_stub
import tasktree.docker as docker_module
from tasktree.executor import Executor
from tasktree.hasher import hash_runner_definition
from tasktree.parser import DockerArgs, Runner, Recipe, ShellConfig, Task
from tasktree.process_runner import TaskOutputTypes, make_process_runner
from tasktree.state import StateManager, TaskState


class TestHashRunnerDefinition(unittest.TestCase):
    """
    Test runner definition hashing.
    """

    def test_hash_runner_definition_deterministic(self):
        """
        Test that hashing same runner twice produces same hash.
        """

        runner = Runner(
            name="test",
            shell=ShellConfig(cmd=["bash", "-c"], preamble="set -e"),
        )

        hash1 = hash_runner_definition(runner)
        hash2 = hash_runner_definition(runner)

        self.assertEqual(hash1, hash2)
        self.assertEqual(len(hash1), 16)  # 16-character hash

    def test_hash_runner_definition_shell_change(self):
        """
        Test that changing shell produces different hash.
        """

        runner1 = Runner(
            name="test",
            shell=ShellConfig(cmd=["bash", "-c"]),
        )
        runner2 = Runner(
            name="test",
            shell=ShellConfig(cmd=["zsh", "-c"]),
        )

        hash1 = hash_runner_definition(runner1)
        hash2 = hash_runner_definition(runner2)

        self.assertNotEqual(hash1, hash2)

    def test_hash_runner_definition_args_change(self):
        """
        Test that changing docker run args produces different hash.
        """

        runner1 = Runner(
            name="test",
            dockerfile="Dockerfile",
            context=".",
            args=DockerArgs(run=["--rm"]),
        )
        runner2 = Runner(
            name="test",
            dockerfile="Dockerfile",
            context=".",
            args=DockerArgs(run=["--rm", "--network=host"]),
        )

        hash1 = hash_runner_definition(runner1)
        hash2 = hash_runner_definition(runner2)

        self.assertNotEqual(hash1, hash2)

    def test_hash_runner_definition_preamble_change(self):
        """
        Test that changing preamble produces different hash.
        """

        runner1 = Runner(
            name="test",
            shell=ShellConfig(cmd=["bash", "-c"], preamble=""),
        )
        runner2 = Runner(
            name="test",
            shell=ShellConfig(cmd=["bash", "-c"], preamble="set -e"),
        )

        hash1 = hash_runner_definition(runner1)
        hash2 = hash_runner_definition(runner2)

        self.assertNotEqual(hash1, hash2)

    def test_hash_runner_definition_docker_fields(self):
        """
        Test that changing Docker fields produces different hash.
        """

        runner1 = Runner(
            name="test",
            dockerfile="Dockerfile",
            context=".",
        )
        runner2 = Runner(
            name="test",
            dockerfile="Dockerfile",
            context=".",
            volumes=["./src:/app/src"],
        )

        hash1 = hash_runner_definition(runner1)
        hash2 = hash_runner_definition(runner2)

        self.assertNotEqual(hash1, hash2)

    def test_hash_runner_definition_args_order_independent(self):
        """
        Test that docker run args order doesn't matter (they're sorted in hash).
        """

        runner1 = Runner(
            name="test",
            dockerfile="Dockerfile",
            context=".",
            args=DockerArgs(run=["--rm", "--network=host"]),
        )
        runner2 = Runner(
            name="test",
            dockerfile="Dockerfile",
            context=".",
            args=DockerArgs(run=["--network=host", "--rm"]),
        )

        hash1 = hash_runner_definition(runner1)
        hash2 = hash_runner_definition(runner2)

        self.assertEqual(hash1, hash2)


class TestCheckRunnerChanged(unittest.TestCase):
    """
    Test runner change detection in executor.
    """

    def setUp(self):
        """
        Set up test runner.
        """
        self.project_root = Path("/tmp/test")
        self.runner = Runner(
            name="test",
            shell=ShellConfig(cmd=["bash", "-c"]),
        )
        self.recipe = Recipe(
            tasks={},
            project_root=self.project_root,
            recipe_path=self.project_root / "tasktree.yaml",
            runners={"test": self.runner},
        )
        self.state_manager = StateManager(self.project_root)

        self.executor = Executor(
            self.recipe, self.state_manager, logger_stub, make_process_runner
        )

    def test_check_runner_changed_no_runner(self):
        """
        Test that platform default (no runner) returns False.
        """

        task = Task(name="test", cmd="echo test")
        cached_state = TaskState(last_run=123.0, input_state={})

        result = self.executor._check_runner_changed(
            task,
            cached_state,
            "",
            make_process_runner(TaskOutputTypes.ALL, logger_stub),
        )

        self.assertFalse(result)

    def test_check_runner_changed_first_run(self):
        """
        Test that missing cached hash returns True.
        """

        task = Task(name="test", cmd="echo test", run_in="test")
        cached_state = TaskState(last_run=123.0, input_state={})

        result = self.executor._check_runner_changed(
            task,
            cached_state,
            "test",
            make_process_runner(TaskOutputTypes.ALL, logger_stub),
        )

        self.assertTrue(result)

    def test_check_runner_changed_unchanged(self):
        """
        Test that matching hash returns False.
        """
        task = Task(name="test", cmd="echo test", run_in="test")

        # Compute hash and store in cached state
        runner_hash = hash_runner_definition(self.runner)
        cached_state = TaskState(
            last_run=123.0, input_state={"_runner_hash_test": runner_hash}
        )

        result = self.executor._check_runner_changed(
            task,
            cached_state,
            "test",
            make_process_runner(TaskOutputTypes.ALL, logger_stub),
        )

        self.assertFalse(result)

    def test_check_runner_changed_shell_modified(self):
        """
        Test that modified shell is detected.
        """
        task = Task(name="test", cmd="echo test", run_in="test")

        # Store old hash
        old_runner = Runner(name="test", shell=ShellConfig(cmd=["bash", "-c"]))
        old_hash = hash_runner_definition(old_runner)
        cached_state = TaskState(
            last_run=123.0, input_state={"_runner_hash_test": old_hash}
        )

        # Recipe now has modified runner
        self.recipe.runners["test"] = Runner(name="test", shell=ShellConfig(cmd=["zsh", "-c"]))

        result = self.executor._check_runner_changed(
            task,
            cached_state,
            "test",
            make_process_runner(TaskOutputTypes.ALL, logger_stub),
        )

        self.assertTrue(result)

    def test_check_runner_changed_deleted_runner(self):
        """
        Test that deleted runner returns True.
        """

        task = Task(name="test", cmd="echo test", run_in="test")
        cached_state = TaskState(
            last_run=123.0, input_state={"_runner_hash_test": "somehash"}
        )

        # Delete runner from recipe
        self.recipe.runners = {}

        result = self.executor._check_runner_changed(
            task,
            cached_state,
            "test",
            make_process_runner(TaskOutputTypes.ALL, logger_stub),
        )

        self.assertTrue(result)


class TestCheckDockerImageChanged(unittest.TestCase):
    """
    Test Docker image ID change detection in executor.
    """

    def setUp(self):
        """
        Set up test runner.
        """

        self.project_root = Path("/tmp/test")

        # Create Docker runner
        self.runner = Runner(
            name="builder",
            dockerfile="Dockerfile",
            context=".",
        )
        self.recipe = Recipe(
            tasks={},
            project_root=self.project_root,
            recipe_path=self.project_root / "tasktree.yaml",
            runners={"builder": self.runner},
        )
        self.state_manager = StateManager(self.project_root)
        self.executor = Executor(
            self.recipe, self.state_manager, logger_stub, make_process_runner
        )

    def test_check_docker_image_changed_no_cached_id(self):
        """
        Test that missing cached image ID returns True (first run).
        """

        # Cached state has runner hash but no image ID (old state file)
        runner_hash = hash_runner_definition(self.runner)
        cached_state = TaskState(
            last_run=123.0, input_state={"_runner_hash_builder": runner_hash}
        )

        # Mock docker manager to return image ID
        self.executor.docker_manager.ensure_image_built = Mock(
            return_value=("tt-runner-builder", "sha256:abc123")
        )

        result = self.executor._check_docker_image_changed(
            self.runner,
            cached_state,
            "builder",
            make_process_runner(TaskOutputTypes.ALL, logger_stub),
        )

        self.assertTrue(result)

    def test_check_docker_image_changed_same_id(self):
        """
        Test that matching image ID returns False.
        """

        # Cached state with image ID
        image_id = "sha256:abc123"
        cached_state = TaskState(
            last_run=123.0, input_state={"_docker_image_id_builder": image_id}
        )

        # Mock docker manager to return same image ID
        self.executor.docker_manager.ensure_image_built = Mock(
            return_value=("tt-runner-builder", image_id)
        )

        result = self.executor._check_docker_image_changed(
            self.runner,
            cached_state,
            "builder",
            make_process_runner(TaskOutputTypes.ALL, logger_stub),
        )

        self.assertFalse(result)

    def test_check_docker_image_changed_different_id(self):
        """
        Test that different image ID returns True (unpinned base updated).
        """

        # Cached state with old image ID
        old_image_id = "sha256:abc123"
        cached_state = TaskState(
            last_run=123.0, input_state={"_docker_image_id_builder": old_image_id}
        )

        # Mock docker manager to return new image ID (base image updated)
        new_image_id = "sha256:def456"
        self.executor.docker_manager.ensure_image_built = Mock(
            return_value=("tt-runner-builder", new_image_id)
        )

        result = self.executor._check_docker_image_changed(
            self.runner,
            cached_state,
            "builder",
            make_process_runner(TaskOutputTypes.ALL, logger_stub),
        )

        self.assertTrue(result)

    def test_check_runner_changed_docker_yaml_and_image(self):
        """
        Test that Docker runner checks both YAML hash and image ID.
        """

        task = Task(name="test", cmd="echo test", run_in="builder")

        # Cached state with matching runner hash AND matching image ID
        runner_hash = hash_runner_definition(self.runner)
        image_id = "sha256:abc123"
        cached_state = TaskState(
            last_run=123.0,
            input_state={
                "_runner_hash_builder": runner_hash,
                "_docker_image_id_builder": image_id,
            },
        )

        # Mock docker manager to return same image ID
        self.executor.docker_manager.ensure_image_built = Mock(
            return_value=("tt-runner-builder", image_id)
        )

        # Should return False (both YAML and image ID unchanged)
        result = self.executor._check_runner_changed(
            task,
            cached_state,
            "builder",
            make_process_runner(TaskOutputTypes.ALL, logger_stub),
        )
        self.assertFalse(result)

    def test_check_runner_changed_docker_yaml_changed(self):
        """
        Test that YAML change detected without checking image ID.
        """

        task = Task(name="test", cmd="echo test", run_in="builder")

        # Cached state with OLD runner hash (YAML changed)
        old_runner = Runner(name="builder", dockerfile="OldDockerfile", context=".")
        old_runner_hash = hash_runner_definition(old_runner)

        cached_state = TaskState(
            last_run=123.0,
            input_state={
                "_runner_hash_builder": old_runner_hash,
                "_docker_image_id_builder": "sha256:abc123",
            },
        )

        # Mock should NOT be called (YAML change detected early)
        self.executor.docker_manager.ensure_image_built = Mock()

        # Should return True (YAML changed)
        result = self.executor._check_runner_changed(
            task,
            cached_state,
            "builder",
            make_process_runner(TaskOutputTypes.ALL, logger_stub),
        )
        self.assertTrue(result)

        # Verify docker manager was NOT called (early exit on YAML change)
        self.executor.docker_manager.ensure_image_built.assert_not_called()

    def test_check_runner_changed_returns_true_when_base_image_updated(self):
        """YAML and context unchanged but built image ID differs (base image updated)."""
        task = Task(name="test", cmd="echo test", run_in="builder")

        runner_hash = hash_runner_definition(self.runner)
        old_image_id = "sha256:abc123"
        cached_state = TaskState(
            last_run=123.0,
            input_state={
                "_runner_hash_builder": runner_hash,
                "_docker_image_id_builder": old_image_id,
            },
        )

        # Simulate base image being pulled: same Dockerfile, different resulting image ID
        new_image_id = "sha256:def456"
        self.executor.docker_manager.ensure_image_built = Mock(
            return_value=("tt-runner-builder", new_image_id)
        )

        result = self.executor._check_runner_changed(
            task,
            cached_state,
            "builder",
            make_process_runner(TaskOutputTypes.ALL, logger_stub),
        )

        self.assertTrue(result)

    def test_check_runner_changed_returns_true_when_context_file_modified(self):
        """
        Test that _check_runner_changed returns True when a context file has changed.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            context_dir = project_root / "ctx"
            context_dir.mkdir()
            src_file = context_dir / "app.py"
            src_file.write_text("original")

            runner = Runner(name="builder", dockerfile="Dockerfile", context="ctx")
            recipe = Recipe(
                tasks={},
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
                runners={"builder": runner},
            )
            executor = Executor(recipe, StateManager(project_root), logger_stub, make_process_runner)

            runner_hash = hash_runner_definition(runner)
            # Cache state with a stale mtime for the context file
            stale_mtime = src_file.stat().st_mtime - 1.0
            ctx_key = f"_ctx_builder_{src_file.relative_to(project_root).as_posix()}"
            cached_state = TaskState(
                last_run=123.0,
                input_state={
                    "_runner_hash_builder": runner_hash,
                    ctx_key: stale_mtime,
                },
            )

            executor.docker_manager.ensure_image_built = Mock()

            task = Task(name="test", cmd="echo test", run_in="builder")
            result = executor._check_runner_changed(
                task,
                cached_state,
                "builder",
                make_process_runner(TaskOutputTypes.ALL, logger_stub),
            )

            self.assertTrue(result)
            # ensure_image_built should NOT be called — context change detected first
            executor.docker_manager.ensure_image_built.assert_not_called()

    def test_check_runner_changed_returns_true_when_dockerignore_modified(self):
        """_check_runner_changed returns True when .dockerignore has been modified."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            context_dir = project_root / "ctx"
            context_dir.mkdir()
            (context_dir / "app.py").write_text("code")
            dockerignore = context_dir / ".dockerignore"
            dockerignore.write_text("*.log\n")

            runner = Runner(name="builder", dockerfile="Dockerfile", context="ctx")
            recipe = Recipe(
                tasks={},
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
                runners={"builder": runner},
            )
            executor = Executor(recipe, StateManager(project_root), logger_stub, make_process_runner)

            runner_hash = hash_runner_definition(runner)
            ctx_key = f"_ctx_builder_{(context_dir / 'app.py').relative_to(project_root).as_posix()}"
            dockerignore_key = dockerignore.relative_to(project_root).as_posix()
            cached_state = TaskState(
                last_run=123.0,
                input_state={
                    "_runner_hash_builder": runner_hash,
                    ctx_key: (context_dir / "app.py").stat().st_mtime,
                    dockerignore_key: dockerignore.stat().st_mtime - 1.0,
                },
            )

            executor.docker_manager.ensure_image_built = Mock()

            task = Task(name="test", cmd="echo test", run_in="builder")
            result = executor._check_runner_changed(
                task,
                cached_state,
                "builder",
                make_process_runner(TaskOutputTypes.ALL, logger_stub),
            )

            self.assertTrue(result)
            executor.docker_manager.ensure_image_built.assert_not_called()


class TestDockerInputsToModifiedTimes(unittest.TestCase):
    """
    Test per-file mtime recording for Docker context directory.
    """

    def _make_executor(self, project_root: Path, context_dir: str) -> Executor:
        runner = Runner(name="builder", dockerfile="Dockerfile", context=context_dir)
        recipe = Recipe(
            tasks={},
            project_root=project_root,
            recipe_path=project_root / "tasktree.yaml",
            runners={"builder": runner},
        )
        state_manager = StateManager(project_root)
        return Executor(recipe, state_manager, logger_stub, make_process_runner)

    def test_records_per_file_mtime_keys_for_context(self):
        """
        Files in context directory are stored with _ctx_{env_name}_{relpath} keys.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            context_dir = project_root / "ctx"
            context_dir.mkdir()
            src_file = context_dir / "app.py"
            src_file.write_text("print('hello')")

            executor = self._make_executor(project_root, "ctx")
            env = executor.recipe.runners["builder"]
            result = executor._docker_inputs_to_modified_times("builder", env)

            expected_key = f"_ctx_builder_ctx/app.py"
            self.assertIn(expected_key, result)
            self.assertAlmostEqual(result[expected_key], src_file.stat().st_mtime, places=3)

    def test_records_mtime_for_multiple_context_files(self):
        """
        All files in context directory are recorded.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            context_dir = project_root / "ctx"
            context_dir.mkdir()
            (context_dir / "a.txt").write_text("a")
            (context_dir / "b.txt").write_text("b")
            subdir = context_dir / "sub"
            subdir.mkdir()
            (subdir / "c.txt").write_text("c")

            executor = self._make_executor(project_root, "ctx")
            env = executor.recipe.runners["builder"]
            result = executor._docker_inputs_to_modified_times("builder", env)

            self.assertIn("_ctx_builder_ctx/a.txt", result)
            self.assertIn("_ctx_builder_ctx/b.txt", result)
            self.assertIn("_ctx_builder_ctx/sub/c.txt", result)

    def test_does_not_include_old_single_context_key(self):
        """
        The old _context_{env.context} key is not present — replaced by per-file keys.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            context_dir = project_root / "ctx"
            context_dir.mkdir()
            (context_dir / "app.py").write_text("x")

            executor = self._make_executor(project_root, "ctx")
            env = executor.recipe.runners["builder"]
            result = executor._docker_inputs_to_modified_times("builder", env)

            self.assertNotIn("_context_ctx", result)

    def test_empty_context_directory_produces_no_ctx_keys(self):
        """
        An empty context directory produces no _ctx_* keys.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            context_dir = project_root / "ctx"
            context_dir.mkdir()

            executor = self._make_executor(project_root, "ctx")
            env = executor.recipe.runners["builder"]
            result = executor._docker_inputs_to_modified_times("builder", env)

            ctx_keys = [k for k in result if k.startswith("_ctx_")]
            self.assertEqual(ctx_keys, [])

    def test_nonexistent_context_directory_produces_no_ctx_keys(self):
        """
        A missing context directory is handled gracefully (no _ctx_* keys, no exception).
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            # Do NOT create context dir

            executor = self._make_executor(project_root, "ctx")
            env = executor.recipe.runners["builder"]
            result = executor._docker_inputs_to_modified_times("builder", env)

            ctx_keys = [k for k in result if k.startswith("_ctx_")]
            self.assertEqual(ctx_keys, [])

    def test_respects_dockerignore_patterns(self):
        """
        Files matched by .dockerignore are excluded from mtime tracking.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            context_dir = project_root / "ctx"
            context_dir.mkdir()
            (context_dir / "app.py").write_text("code")
            (context_dir / "notes.log").write_text("log")
            (context_dir / ".dockerignore").write_text("*.log\n")

            executor = self._make_executor(project_root, "ctx")
            env = executor.recipe.runners["builder"]
            result = executor._docker_inputs_to_modified_times("builder", env)

            self.assertIn("_ctx_builder_ctx/app.py", result)
            self.assertNotIn("_ctx_builder_ctx/notes.log", result)

    def test_dockerignore_not_in_ctx_keys(self):
        """
        .dockerignore is tracked under its own explicit key, not as a _ctx_* key.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            context_dir = project_root / "ctx"
            context_dir.mkdir()
            (context_dir / "app.py").write_text("code")
            (context_dir / ".dockerignore").write_text("*.log\n")

            executor = self._make_executor(project_root, "ctx")
            env = executor.recipe.runners["builder"]
            result = executor._docker_inputs_to_modified_times("builder", env)

            self.assertNotIn("_ctx_builder_ctx/.dockerignore", result)
            self.assertIn("ctx/.dockerignore", result)

    def test_records_local_base_image_digest(self):
        """get_local_base_image_digest result stored under _base_img_{env}_{name}."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            context_dir = project_root / "ctx"
            context_dir.mkdir()
            (project_root / "Dockerfile").write_text("FROM python:3.11\nRUN echo hello\n")

            executor = self._make_executor(project_root, "ctx")
            env = executor.recipe.runners["builder"]

            with patch.object(docker_module, "get_local_base_image_digest", return_value="sha256:abc123"):
                result = executor._docker_inputs_to_modified_times("builder", env)

            self.assertEqual(result["_base_img_builder_python:3.11"], "sha256:abc123")

    def test_does_not_record_missing_local_base_image(self):
        """When get_local_base_image_digest returns None, no _base_img_* key is stored."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            context_dir = project_root / "ctx"
            context_dir.mkdir()
            (project_root / "Dockerfile").write_text("FROM python:3.11\n")

            executor = self._make_executor(project_root, "ctx")
            env = executor.recipe.runners["builder"]

            with patch.object(docker_module, "get_local_base_image_digest", return_value=None):
                result = executor._docker_inputs_to_modified_times("builder", env)

            base_img_keys = [k for k in result if k.startswith("_base_img_")]
            self.assertEqual(base_img_keys, [])

    def test_records_multiple_base_images(self):
        """Multi-stage Dockerfile: each FROM image is tracked under its own key."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            context_dir = project_root / "ctx"
            context_dir.mkdir()
            (project_root / "Dockerfile").write_text(
                "FROM python:3.11 AS builder\nFROM alpine:3.18\n"
            )

            executor = self._make_executor(project_root, "ctx")
            env = executor.recipe.runners["builder"]

            digests = {"python:3.11": "sha256:py311", "alpine:3.18": "sha256:alpine318"}
            with patch.object(
                docker_module, "get_local_base_image_digest", side_effect=lambda n: digests.get(n)
            ):
                result = executor._docker_inputs_to_modified_times("builder", env)

            self.assertEqual(result["_base_img_builder_python:3.11"], "sha256:py311")
            self.assertEqual(result["_base_img_builder_alpine:3.18"], "sha256:alpine318")

    def test_all_context_files_included_when_pathspec_unavailable(self):
        """
        When parse_dockerignore returns None (pathspec not installed), all
        context files are still included in mtime tracking.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            context_dir = project_root / "ctx"
            context_dir.mkdir()
            (context_dir / "app.py").write_text("code")
            (context_dir / "notes.log").write_text("log")
            (context_dir / ".dockerignore").write_text("*.log\n")

            executor = self._make_executor(project_root, "ctx")
            env = executor.recipe.runners["builder"]

            with patch.object(docker_module, "parse_dockerignore", return_value=None):
                result = executor._docker_inputs_to_modified_times("builder", env)

            self.assertIn("_ctx_builder_ctx/app.py", result)
            self.assertIn("_ctx_builder_ctx/notes.log", result)


class TestCheckDockerContextChanged(unittest.TestCase):
    """
    Test _check_docker_context_changed() detects context file changes.
    """

    def _make_executor(self, project_root: Path, context_dir: str) -> "Executor":
        runner = Runner(name="builder", dockerfile="Dockerfile", context=context_dir)
        recipe = Recipe(
            tasks={},
            project_root=project_root,
            recipe_path=project_root / "tasktree.yaml",
            runners={"builder": runner},
        )
        state_manager = StateManager(project_root)
        return Executor(recipe, state_manager, logger_stub, make_process_runner)

    def _ctx_key(self, env_name: str, rel_path: str) -> str:
        return f"_ctx_{env_name}_{rel_path}"

    def test_returns_true_when_no_cached_ctx_state_and_files_exist(self):
        """First run: no _ctx_* keys cached but context files exist → True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            context_dir = project_root / "ctx"
            context_dir.mkdir()
            (context_dir / "app.py").write_text("x")

            executor = self._make_executor(project_root, "ctx")
            env = executor.recipe.runners["builder"]
            cached_state = TaskState(last_run=123.0, input_state={})

            result = executor._check_docker_context_changed("builder", env, cached_state)

            self.assertTrue(result)

    def test_returns_false_when_no_cached_ctx_state_and_no_files(self):
        """Empty context dir with no cached state → False (nothing to track)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            context_dir = project_root / "ctx"
            context_dir.mkdir()

            executor = self._make_executor(project_root, "ctx")
            env = executor.recipe.runners["builder"]
            cached_state = TaskState(last_run=123.0, input_state={})

            result = executor._check_docker_context_changed("builder", env, cached_state)

            self.assertFalse(result)

    def test_returns_false_when_context_unchanged(self):
        """Context files match cached mtimes → False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            context_dir = project_root / "ctx"
            context_dir.mkdir()
            src = context_dir / "app.py"
            src.write_text("x")

            executor = self._make_executor(project_root, "ctx")
            env = executor.recipe.runners["builder"]
            mtime = src.stat().st_mtime
            cached_state = TaskState(
                last_run=123.0,
                input_state={self._ctx_key("builder", "ctx/app.py"): mtime},
            )

            result = executor._check_docker_context_changed("builder", env, cached_state)

            self.assertFalse(result)

    def test_returns_true_when_file_modified(self):
        """A context file has a newer mtime than cached → True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            context_dir = project_root / "ctx"
            context_dir.mkdir()
            src = context_dir / "app.py"
            src.write_text("x")

            executor = self._make_executor(project_root, "ctx")
            env = executor.recipe.runners["builder"]
            # Cached mtime is in the past
            cached_state = TaskState(
                last_run=123.0,
                input_state={self._ctx_key("builder", "ctx/app.py"): src.stat().st_mtime - 1.0},
            )

            result = executor._check_docker_context_changed("builder", env, cached_state)

            self.assertTrue(result)

    def test_returns_true_when_new_file_added(self):
        """A new file in context dir that wasn't cached → True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            context_dir = project_root / "ctx"
            context_dir.mkdir()
            old_file = context_dir / "app.py"
            old_file.write_text("x")
            new_file = context_dir / "new.py"
            new_file.write_text("y")

            executor = self._make_executor(project_root, "ctx")
            env = executor.recipe.runners["builder"]
            # Only app.py is in cached state
            cached_state = TaskState(
                last_run=123.0,
                input_state={self._ctx_key("builder", "ctx/app.py"): old_file.stat().st_mtime},
            )

            result = executor._check_docker_context_changed("builder", env, cached_state)

            self.assertTrue(result)

    def test_returns_true_when_file_deleted(self):
        """A file that was cached no longer exists → True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            context_dir = project_root / "ctx"
            context_dir.mkdir()
            remaining = context_dir / "app.py"
            remaining.write_text("x")

            executor = self._make_executor(project_root, "ctx")
            env = executor.recipe.runners["builder"]
            # Cached state references a file that no longer exists
            cached_state = TaskState(
                last_run=123.0,
                input_state={
                    self._ctx_key("builder", "ctx/app.py"): remaining.stat().st_mtime,
                    self._ctx_key("builder", "ctx/deleted.py"): 1234567890.0,
                },
            )

            result = executor._check_docker_context_changed("builder", env, cached_state)

            self.assertTrue(result)

    def test_returns_false_when_context_is_none(self):
        """Runner with no context (env.context is None) → False without raising."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            runner = Runner(name="builder", dockerfile="Dockerfile", context=None)
            recipe = Recipe(
                tasks={},
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
                runners={"builder": runner},
            )
            state_manager = StateManager(project_root)
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)
            env = recipe.runners["builder"]
            cached_state = TaskState(last_run=123.0, input_state={})

            result = executor._check_docker_context_changed("builder", env, cached_state)

            self.assertFalse(result)

    def test_returns_false_when_context_dir_does_not_exist(self):
        """Runner whose context path does not exist on disk → False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            executor = self._make_executor(project_root, "nonexistent_ctx")
            env = executor.recipe.runners["builder"]
            cached_state = TaskState(last_run=123.0, input_state={})

            result = executor._check_docker_context_changed("builder", env, cached_state)

            self.assertFalse(result)

    def test_ignored_file_change_does_not_trigger(self):
        """.dockerignore-excluded file changes do not produce a false positive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            context_dir = project_root / "ctx"
            context_dir.mkdir()

            tracked = context_dir / "app.py"
            tracked.write_text("x")
            ignored = context_dir / "build.log"
            ignored.write_text("log")

            (context_dir / ".dockerignore").write_text("*.log\n")

            executor = self._make_executor(project_root, "ctx")
            env = executor.recipe.runners["builder"]
            mtime = tracked.stat().st_mtime
            dockerignore = context_dir / ".dockerignore"
            dockerignore_key = dockerignore.relative_to(project_root).as_posix()
            # Only app.py is cached; build.log is ignored so not cached either;
            # .dockerignore is cached so its presence doesn't count as a change
            cached_state = TaskState(
                last_run=123.0,
                input_state={
                    self._ctx_key("builder", "ctx/app.py"): mtime,
                    dockerignore_key: dockerignore.stat().st_mtime,
                },
            )

            result = executor._check_docker_context_changed("builder", env, cached_state)

            self.assertFalse(result)


class TestCheckBaseImageDigestsChanged(unittest.TestCase):
    """Test _check_base_image_digests_changed() detects base image digest changes."""

    def _make_executor(self, project_root: Path) -> Executor:
        runner = Runner(name="builder", dockerfile="Dockerfile", context="ctx")
        recipe = Recipe(
            tasks={},
            project_root=project_root,
            recipe_path=project_root / "tasktree.yaml",
            runners={"builder": runner},
        )
        return Executor(recipe, StateManager(project_root), logger_stub, make_process_runner)

    def test_returns_false_when_no_dockerfile(self):
        """Runner with no dockerfile → False without raising."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            runner = Runner(name="builder", dockerfile=None, context=None)
            recipe = Recipe(
                tasks={},
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
                runners={"builder": runner},
            )
            executor = Executor(recipe, StateManager(project_root), logger_stub, make_process_runner)
            cached_state = TaskState(last_run=123.0, input_state={})

            result = executor._check_base_image_digests_changed("builder", runner, cached_state)

            self.assertFalse(result)

    def test_returns_false_when_digest_unchanged(self):
        """Same digest as cached → False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Dockerfile").write_text("FROM python:3.11\n")
            executor = self._make_executor(project_root)
            env = executor.recipe.runners["builder"]
            cached_state = TaskState(
                last_run=123.0,
                input_state={"_base_img_builder_python:3.11": "sha256:abc"},
            )

            with patch.object(docker_module, "get_local_base_image_digest", return_value="sha256:abc"):
                result = executor._check_base_image_digests_changed("builder", env, cached_state)

            self.assertFalse(result)

    def test_returns_true_when_digest_changed(self):
        """Different digest from cached → True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Dockerfile").write_text("FROM python:3.11\n")
            executor = self._make_executor(project_root)
            env = executor.recipe.runners["builder"]
            cached_state = TaskState(
                last_run=123.0,
                input_state={"_base_img_builder_python:3.11": "sha256:v1"},
            )

            with patch.object(docker_module, "get_local_base_image_digest", return_value="sha256:v2"):
                result = executor._check_base_image_digests_changed("builder", env, cached_state)

            self.assertTrue(result)

    def test_returns_false_when_both_none(self):
        """Image not available locally and not cached → False (no false positive)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Dockerfile").write_text("FROM python:3.11\n")
            executor = self._make_executor(project_root)
            env = executor.recipe.runners["builder"]
            cached_state = TaskState(last_run=123.0, input_state={})

            with patch.object(docker_module, "get_local_base_image_digest", return_value=None):
                result = executor._check_base_image_digests_changed("builder", env, cached_state)

            self.assertFalse(result)

    def test_returns_true_when_new_digest_appeared(self):
        """Previously no cached digest (None), now image present locally → True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Dockerfile").write_text("FROM python:3.11\n")
            executor = self._make_executor(project_root)
            env = executor.recipe.runners["builder"]
            cached_state = TaskState(last_run=123.0, input_state={})

            with patch.object(docker_module, "get_local_base_image_digest", return_value="sha256:new"):
                result = executor._check_base_image_digests_changed("builder", env, cached_state)

            self.assertTrue(result)

    def test_returns_true_when_cached_digest_gone(self):
        """Cached digest was present, now Docker returns None → True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "Dockerfile").write_text("FROM python:3.11\n")
            executor = self._make_executor(project_root)
            env = executor.recipe.runners["builder"]
            cached_state = TaskState(
                last_run=123.0,
                input_state={"_base_img_builder_python:3.11": "sha256:old"},
            )

            with patch.object(docker_module, "get_local_base_image_digest", return_value=None):
                result = executor._check_base_image_digests_changed("builder", env, cached_state)

            self.assertTrue(result)

    def test_check_runner_changed_returns_true_when_base_image_digest_changes(self):
        """_check_runner_changed returns True when base image digest differs from cached."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "ctx").mkdir()
            (project_root / "Dockerfile").write_text("FROM python:3.11\n")
            runner = Runner(name="builder", dockerfile="Dockerfile", context="ctx")
            recipe = Recipe(
                tasks={},
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
                runners={"builder": runner},
            )
            executor = Executor(recipe, StateManager(project_root), logger_stub, make_process_runner)
            runner_hash = hash_runner_definition(runner)
            cached_state = TaskState(
                last_run=123.0,
                input_state={
                    "_runner_hash_builder": runner_hash,
                    "_base_img_builder_python:3.11": "sha256:v1",
                },
            )
            executor.docker_manager.ensure_image_built = Mock()
            task = Task(name="test", cmd="echo test", run_in="builder")

            with patch.object(docker_module, "get_local_base_image_digest", return_value="sha256:v2"):
                result = executor._check_runner_changed(
                    task,
                    cached_state,
                    "builder",
                    make_process_runner(TaskOutputTypes.ALL, logger_stub),
                )

            self.assertTrue(result)
            executor.docker_manager.ensure_image_built.assert_not_called()


if __name__ == "__main__":
    unittest.main()
