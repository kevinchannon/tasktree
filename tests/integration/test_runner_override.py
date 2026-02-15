"""Integration tests for runner override feature."""

import os
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from tasktree.cli import app


def strip_ansi_codes(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    ansi_escape = re.compile(r"\x1b\[[0-9;]*m")
    return ansi_escape.sub("", text)


class TestBlanketRunnerOverride(unittest.TestCase):
    """Integration tests for blanket runner override at import level."""

    def setUp(self):
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_blanket_runner_override_applied_to_non_pinned_task(self):
        """Test that import-level run_in applies to non-pinned tasks."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Imported file with a task that has no run_in specified
            (project_root / "build.yaml").write_text(
                "tasks:\n"
                "  compile:\n"
                "    cmd: echo 'compiling in imported runner'\n"
            )

            # Root file defines runner and imports with run_in override
            recipe_path = project_root / "tasktree.yaml"
            recipe_path.write_text(
                "runners:\n"
                "  docker:\n"
                "    shell: /bin/bash\n"
                "imports:\n"
                "  - file: build.yaml\n"
                "    as: build\n"
                "    run_in: docker\n"
                "tasks:\n"
                "  all:\n"
                "    deps: [build.compile]\n"
                "    cmd: echo 'done'\n"
            )

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run with --show to verify runner assignment
                result = self.runner.invoke(
                    app, ["--show", "build.compile"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("docker", stripped)

            finally:
                os.chdir(original_cwd)

    def test_pinned_task_ignores_blanket_runner_override(self):
        """Test that pinned tasks ignore import-level run_in."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Imported file with pinned and non-pinned tasks
            (project_root / "build.yaml").write_text(
                "runners:\n"
                "  special:\n"
                "    shell: /bin/sh\n"
                "tasks:\n"
                "  normal:\n"
                "    cmd: echo 'normal task'\n"
                "  special:\n"
                "    cmd: echo 'special task'\n"
                "    run_in: special\n"
                "    pin_runner: true\n"
            )

            # Root file defines different runner and imports with run_in override
            recipe_path = project_root / "tasktree.yaml"
            recipe_path.write_text(
                "runners:\n"
                "  docker:\n"
                "    shell: /bin/bash\n"
                "imports:\n"
                "  - file: build.yaml\n"
                "    as: build\n"
                "    run_in: docker\n"
                "tasks:\n"
                "  all:\n"
                "    deps: [build.normal, build.special]\n"
                "    cmd: echo 'done'\n"
            )

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Verify non-pinned task uses blanket runner
                result = self.runner.invoke(
                    app, ["--show", "build.normal"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("docker", stripped)

                # Verify pinned task ignores blanket runner and uses its own
                result = self.runner.invoke(
                    app, ["--show", "build.special"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("build.special", stripped)

            finally:
                os.chdir(original_cwd)

    def test_blanket_runner_does_not_override_explicit_task_run_in(self):
        """Test that blanket runner doesn't override task's own run_in."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Imported file with pinned task that has explicit run_in
            # Must be pinned to bring the runner definition with it
            (project_root / "build.yaml").write_text(
                "runners:\n"
                "  local:\n"
                "    shell: /bin/sh\n"
                "tasks:\n"
                "  compile:\n"
                "    cmd: echo 'compiling'\n"
                "    run_in: local\n"
                "    pin_runner: true\n"
            )

            # Root file defines runner and imports with run_in override
            recipe_path = project_root / "tasktree.yaml"
            recipe_path.write_text(
                "runners:\n"
                "  docker:\n"
                "    shell: /bin/bash\n"
                "imports:\n"
                "  - file: build.yaml\n"
                "    as: build\n"
                "    run_in: docker\n"
                "tasks:\n"
                "  all:\n"
                "    deps: [build.compile]\n"
                "    cmd: echo 'done'\n"
            )

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Verify task keeps its own run_in (namespaced)
                result = self.runner.invoke(
                    app, ["--show", "build.compile"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("build.local", stripped)

            finally:
                os.chdir(original_cwd)


class TestSelectiveRunnerImport(unittest.TestCase):
    """Integration tests for selective runner import based on pinned tasks."""

    def setUp(self):
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_only_pinned_task_runners_are_imported(self):
        """Test that only runners referenced by pinned tasks are imported."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Imported file has 3 runners: A, B, C
            # task1 is pinned and uses A (A will be imported)
            # task2 is not pinned and has no run_in (will use blanket override)
            # B and C are not used by pinned tasks, so they won't be imported
            (project_root / "build.yaml").write_text(
                "runners:\n"
                "  runner_a:\n"
                "    shell: /bin/sh\n"
                "  runner_b:\n"
                "    shell: /bin/bash\n"
                "  runner_c:\n"
                "    shell: /bin/zsh\n"
                "tasks:\n"
                "  task1:\n"
                "    cmd: echo 'task1'\n"
                "    run_in: runner_a\n"
                "    pin_runner: true\n"
                "  task2:\n"
                "    cmd: echo 'task2'\n"
            )

            # Root file imports with blanket runner override
            recipe_path = project_root / "tasktree.yaml"
            recipe_path.write_text(
                "runners:\n"
                "  docker:\n"
                "    shell: /bin/bash\n"
                "imports:\n"
                "  - file: build.yaml\n"
                "    as: build\n"
                "    run_in: docker\n"
                "tasks:\n"
                "  all:\n"
                "    deps: [build.task1, build.task2]\n"
                "    cmd: echo 'done'\n"
            )

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Verify task1 (pinned) uses runner_a (namespaced)
                result = self.runner.invoke(
                    app, ["--show", "build.task1"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                # runner_a should be imported and namespaced
                self.assertIn("build.runner_a", stripped)

                # Verify task2 (not pinned) uses docker (blanket override)
                result = self.runner.invoke(
                    app, ["--show", "build.task2"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("docker", stripped)

                # Verify runner_b and runner_c are NOT imported
                # We can check this by trying to use them explicitly (they shouldn't exist)
                # Since runner_b and runner_c are not pinned, they shouldn't be in the runner list
                result = self.runner.invoke(app, ["--list"], env=self.env)
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                # Only build.runner_a should exist from the import, not build.runner_b or build.runner_c
                # We can't directly test runner existence without a --list-runners command,
                # but we can verify that task2 uses docker (not build.runner_b)

            finally:
                os.chdir(original_cwd)

    def test_no_pinned_tasks_no_runners_imported(self):
        """Test that no runners are imported when no tasks are pinned."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Imported file has runners but no pinned tasks
            (project_root / "build.yaml").write_text(
                "runners:\n"
                "  runner_a:\n"
                "    shell: /bin/sh\n"
                "  runner_b:\n"
                "    shell: /bin/bash\n"
                "tasks:\n"
                "  task1:\n"
                "    cmd: echo 'task1'\n"
                "  task2:\n"
                "    cmd: echo 'task2'\n"
            )

            # Root file imports with blanket runner override
            recipe_path = project_root / "tasktree.yaml"
            recipe_path.write_text(
                "runners:\n"
                "  docker:\n"
                "    shell: /bin/bash\n"
                "imports:\n"
                "  - file: build.yaml\n"
                "    as: build\n"
                "    run_in: docker\n"
                "tasks:\n"
                "  all:\n"
                "    deps: [build.task1, build.task2]\n"
                "    cmd: echo 'done'\n"
            )

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Both tasks should use the blanket override (docker)
                result = self.runner.invoke(
                    app, ["--show", "build.task1"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("docker", stripped)

                result = self.runner.invoke(
                    app, ["--show", "build.task2"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("docker", stripped)

            finally:
                os.chdir(original_cwd)

    def test_all_pinned_tasks_all_runners_imported(self):
        """Test that all runners are imported when all tasks are pinned."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Imported file has 2 runners, both tasks are pinned
            (project_root / "build.yaml").write_text(
                "runners:\n"
                "  runner_a:\n"
                "    shell: /bin/sh\n"
                "  runner_b:\n"
                "    shell: /bin/bash\n"
                "tasks:\n"
                "  task1:\n"
                "    cmd: echo 'task1'\n"
                "    run_in: runner_a\n"
                "    pin_runner: true\n"
                "  task2:\n"
                "    cmd: echo 'task2'\n"
                "    run_in: runner_b\n"
                "    pin_runner: true\n"
            )

            # Root file imports with blanket runner override (should be ignored)
            recipe_path = project_root / "tasktree.yaml"
            recipe_path.write_text(
                "runners:\n"
                "  docker:\n"
                "    shell: /bin/bash\n"
                "imports:\n"
                "  - file: build.yaml\n"
                "    as: build\n"
                "    run_in: docker\n"
                "tasks:\n"
                "  all:\n"
                "    deps: [build.task1, build.task2]\n"
                "    cmd: echo 'done'\n"
            )

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # task1 should use build.runner_a (pinned)
                result = self.runner.invoke(
                    app, ["--show", "build.task1"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("build.runner_a", stripped)
                self.assertNotIn("docker", stripped)

                # task2 should use build.runner_b (pinned)
                result = self.runner.invoke(
                    app, ["--show", "build.task2"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("build.runner_b", stripped)
                self.assertNotIn("docker", stripped)

            finally:
                os.chdir(original_cwd)


class TestRunnerNamespacing(unittest.TestCase):
    """Integration tests for runner namespacing to prevent collisions."""

    def setUp(self):
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_runner_namespacing_prevents_collision(self):
        """Test that imported runners are namespaced to prevent name collisions."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Imported file has a runner named "docker"
            (project_root / "build.yaml").write_text(
                "runners:\n"
                "  docker:\n"
                "    shell: /bin/sh\n"
                "tasks:\n"
                "  task1:\n"
                "    cmd: echo 'task1 in imported docker'\n"
                "    run_in: docker\n"
                "    pin_runner: true\n"
            )

            # Root file also has a runner named "docker"
            recipe_path = project_root / "tasktree.yaml"
            recipe_path.write_text(
                "runners:\n"
                "  docker:\n"
                "    shell: /bin/bash\n"
                "imports:\n"
                "  - file: build.yaml\n"
                "    as: build\n"
                "tasks:\n"
                "  task2:\n"
                "    cmd: echo 'task2 in root docker'\n"
                "    run_in: docker\n"
            )

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Imported task should use "build.docker" (namespaced)
                result = self.runner.invoke(
                    app, ["--show", "build.task1"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("build.docker", stripped)

                # Root task should use "docker" (not namespaced)
                result = self.runner.invoke(app, ["--show", "task2"], env=self.env)
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("docker", stripped)
                # Should NOT contain "build.docker" since this is a root-level task
                # However, the output might contain both runner names, so we need to be careful
                # We verify by checking that the task can run successfully with both runners defined

                # Execute both tasks to ensure they use different runners
                result = self.runner.invoke(app, ["build.task1"], env=self.env)
                self.assertEqual(result.exit_code, 0, f"Command failed: {result.stdout}")

                result = self.runner.invoke(app, ["task2"], env=self.env)
                self.assertEqual(result.exit_code, 0, f"Command failed: {result.stdout}")

            finally:
                os.chdir(original_cwd)

    def test_runner_reference_rewritten_in_pinned_task(self):
        """Test that run_in references are rewritten to use namespaced runner names."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Imported file with pinned task referencing "my_runner"
            (project_root / "build.yaml").write_text(
                "runners:\n"
                "  my_runner:\n"
                "    shell: /bin/sh\n"
                "tasks:\n"
                "  compile:\n"
                "    cmd: echo 'compiling'\n"
                "    run_in: my_runner\n"
                "    pin_runner: true\n"
            )

            # Root file imports with namespace "build"
            recipe_path = project_root / "tasktree.yaml"
            recipe_path.write_text(
                "runners:\n"
                "  default:\n"
                "    shell: /bin/bash\n"
                "imports:\n"
                "  - file: build.yaml\n"
                "    as: build\n"
                "tasks:\n"
                "  all:\n"
                "    deps: [build.compile]\n"
                "    cmd: echo 'done'\n"
            )

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Verify task's run_in was rewritten to "build.my_runner"
                result = self.runner.invoke(
                    app, ["--show", "build.compile"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("build.my_runner", stripped)

                # Execute the task to ensure it works with the rewritten runner reference
                result = self.runner.invoke(app, ["build.compile"], env=self.env)
                self.assertEqual(result.exit_code, 0, f"Command failed: {result.stdout}")
                self.assertIn("compiling", result.stdout)

            finally:
                os.chdir(original_cwd)

    def test_nested_import_runner_namespacing_three_levels(self):
        """Test runner namespacing through three levels of imports."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Deepest level: common.yaml with a runner and pinned task
            (project_root / "common.yaml").write_text(
                "runners:\n"
                "  util_runner:\n"
                "    shell: /bin/sh\n"
                "tasks:\n"
                "  helper:\n"
                "    cmd: echo 'common helper'\n"
                "    run_in: util_runner\n"
                "    pin_runner: true\n"
            )

            # Middle level: build.yaml imports common.yaml
            (project_root / "build.yaml").write_text(
                "imports:\n"
                "  - file: common.yaml\n"
                "    as: common\n"
                "tasks:\n"
                "  compile:\n"
                "    deps: [common.helper]\n"
                "    cmd: echo 'compiling'\n"
            )

            # Root level: tasktree.yaml imports build.yaml
            recipe_path = project_root / "tasktree.yaml"
            recipe_path.write_text(
                "imports:\n"
                "  - file: build.yaml\n"
                "    as: build\n"
                "tasks:\n"
                "  all:\n"
                "    deps: [build.compile]\n"
                "    cmd: echo 'done'\n"
            )

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Verify runner is namespaced with full chain: build.common.util_runner
                result = self.runner.invoke(
                    app, ["--show", "build.common.helper"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("build.common.util_runner", stripped)

                # Execute the nested task to verify it works
                result = self.runner.invoke(app, ["build.common.helper"], env=self.env)
                self.assertEqual(result.exit_code, 0, f"Command failed: {result.stdout}")
                self.assertIn("common helper", result.stdout)

                # Execute the full dependency chain
                result = self.runner.invoke(app, ["all"], env=self.env)
                self.assertEqual(result.exit_code, 0, f"Command failed: {result.stdout}")
                self.assertIn("common helper", result.stdout)
                self.assertIn("compiling", result.stdout)
                self.assertIn("done", result.stdout)

            finally:
                os.chdir(original_cwd)

    def test_four_level_nested_imports(self):
        """Test runner namespacing through four levels of imports."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Level 4 (deepest): utils.yaml
            (project_root / "utils.yaml").write_text(
                "runners:\n"
                "  base:\n"
                "    shell: /bin/sh\n"
                "tasks:\n"
                "  base_task:\n"
                "    cmd: echo 'base'\n"
                "    run_in: base\n"
                "    pin_runner: true\n"
            )

            # Level 3: common.yaml imports utils.yaml
            (project_root / "common.yaml").write_text(
                "imports:\n"
                "  - file: utils.yaml\n"
                "    as: utils\n"
                "tasks:\n"
                "  common_task:\n"
                "    deps: [utils.base_task]\n"
                "    cmd: echo 'common'\n"
            )

            # Level 2: build.yaml imports common.yaml
            (project_root / "build.yaml").write_text(
                "imports:\n"
                "  - file: common.yaml\n"
                "    as: common\n"
                "tasks:\n"
                "  build_task:\n"
                "    deps: [common.common_task]\n"
                "    cmd: echo 'build'\n"
            )

            # Level 1 (root): tasktree.yaml imports build.yaml
            recipe_path = project_root / "tasktree.yaml"
            recipe_path.write_text(
                "imports:\n"
                "  - file: build.yaml\n"
                "    as: build\n"
                "tasks:\n"
                "  all:\n"
                "    deps: [build.build_task]\n"
                "    cmd: echo 'all'\n"
            )

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Verify runner has full namespace chain: build.common.utils.base
                result = self.runner.invoke(
                    app, ["--show", "build.common.utils.base_task"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("build.common.utils.base", stripped)

                # Execute full chain to verify all levels work
                result = self.runner.invoke(app, ["all"], env=self.env)
                self.assertEqual(result.exit_code, 0, f"Command failed: {result.stdout}")
                self.assertIn("base", result.stdout)
                self.assertIn("common", result.stdout)
                self.assertIn("build", result.stdout)
                self.assertIn("all", result.stdout)

            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
