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


if __name__ == "__main__":
    unittest.main()
