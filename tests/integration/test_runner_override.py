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

            # Imported file with task that has explicit run_in
            (project_root / "build.yaml").write_text(
                "runners:\n"
                "  local:\n"
                "    shell: /bin/sh\n"
                "tasks:\n"
                "  compile:\n"
                "    cmd: echo 'compiling'\n"
                "    run_in: local\n"
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


if __name__ == "__main__":
    unittest.main()
