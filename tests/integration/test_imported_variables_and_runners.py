"""Integration tests for importing variables and runners from imported files."""

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


class TestMultiLevelImportVariablesAndRunners(unittest.TestCase):
    """Integration tests for multi-level import of variables and runners."""

    def setUp(self):
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_three_level_import_resolves_variables_and_runners(self):
        """Test 3-level import chain: root -> l2 -> l3 with variables and runners."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Level 3: defines a variable and a runner, task uses both
            (project_root / "level3.yaml").write_text(
                "variables:\n"
                "  greeting: hello from level3\n"
                "runners:\n"
                "  shell:\n"
                "    shell: /bin/sh\n"
                "tasks:\n"
                "  greet:\n"
                "    run_in: shell\n"
                "    cmd: echo {{ var.greeting }}\n"
            )

            # Level 2: imports level3
            (project_root / "level2.yaml").write_text(
                "imports:\n"
                "  - file: level3.yaml\n"
                "    as: l3\n"
                "tasks:\n"
                "  wrapper:\n"
                "    deps: [l3.greet]\n"
                "    cmd: echo level2 done\n"
            )

            # Root: imports level2
            recipe_path = project_root / "tasktree.yaml"
            recipe_path.write_text(
                "imports:\n"
                "  - file: level2.yaml\n"
                "    as: l2\n"
                "tasks:\n"
                "  all:\n"
                "    deps: [l2.wrapper]\n"
                "    cmd: echo all done\n"
            )

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run the deeply nested task directly
                result = self.runner.invoke(app, ["l2.l3.greet"], env=self.env)
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Task failed: {stripped}")
                self.assertIn("hello from level3", stripped)

                # Clear state so tasks re-run
                state_file = project_root / ".tasktree-state"
                if state_file.exists():
                    state_file.unlink()

                # Run the root task which traverses the full chain
                result = self.runner.invoke(app, ["all"], env=self.env)
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Task failed: {stripped}")
                self.assertIn("hello from level3", stripped)
                self.assertIn("level2 done", stripped)
                self.assertIn("all done", stripped)

            finally:
                os.chdir(original_cwd)

    def test_imported_variable_used_in_root_task_via_namespace(self):
        """Test that root tasks can reference imported variables with full namespace."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            (project_root / "config.yaml").write_text(
                "variables:\n"
                "  version: 1.2.3\n"
                "tasks:\n"
                "  noop:\n"
                "    cmd: echo noop\n"
            )

            recipe_path = project_root / "tasktree.yaml"
            recipe_path.write_text(
                "imports:\n"
                "  - file: config.yaml\n"
                "    as: cfg\n"
                "tasks:\n"
                "  show_version:\n"
                "    cmd: echo version is {{ var.cfg.version }}\n"
            )

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                result = self.runner.invoke(
                    app, ["show_version"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Task failed: {stripped}")
                self.assertIn("version is 1.2.3", stripped)

            finally:
                os.chdir(original_cwd)

    def test_chained_variables_resolve_across_import(self):
        """Test that chained variable references within imported files resolve correctly."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            (project_root / "build.yaml").write_text(
                "variables:\n"
                "  base_dir: /opt\n"
                '  install_dir: "{{ var.base_dir }}/myapp"\n'
                "tasks:\n"
                "  install:\n"
                "    cmd: echo installing to {{ var.install_dir }}\n"
            )

            recipe_path = project_root / "tasktree.yaml"
            recipe_path.write_text(
                "imports:\n"
                "  - file: build.yaml\n"
                "    as: build\n"
                "tasks:\n"
                "  all:\n"
                "    deps: [build.install]\n"
                "    cmd: echo done\n"
            )

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                result = self.runner.invoke(
                    app, ["build.install"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Task failed: {stripped}")
                self.assertIn("installing to /opt/myapp", stripped)

            finally:
                os.chdir(original_cwd)

    def test_diamond_import_variables_and_runners(self):
        """Test diamond pattern: root -> {left, right} -> base with variables and runners."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Base: defines a variable and a runner
            (project_root / "base.yaml").write_text(
                "variables:\n"
                "  msg: from base\n"
                "runners:\n"
                "  shell:\n"
                "    shell: /bin/sh\n"
                "tasks:\n"
                "  hello:\n"
                "    run_in: shell\n"
                "    cmd: echo {{ var.msg }}\n"
            )

            # Left: imports base
            (project_root / "left.yaml").write_text(
                "imports:\n"
                "  - file: base.yaml\n"
                "    as: base\n"
                "tasks:\n"
                "  run:\n"
                "    deps: [base.hello]\n"
                "    cmd: echo left done\n"
            )

            # Right: imports base
            (project_root / "right.yaml").write_text(
                "imports:\n"
                "  - file: base.yaml\n"
                "    as: base\n"
                "tasks:\n"
                "  run:\n"
                "    deps: [base.hello]\n"
                "    cmd: echo right done\n"
            )

            # Root: imports both left and right
            recipe_path = project_root / "tasktree.yaml"
            recipe_path.write_text(
                "imports:\n"
                "  - file: left.yaml\n"
                "    as: left\n"
                "  - file: right.yaml\n"
                "    as: right\n"
                "tasks:\n"
                "  all:\n"
                "    deps: [left.run, right.run]\n"
                "    cmd: echo all done\n"
            )

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run left side of the diamond
                result = self.runner.invoke(
                    app, ["left.base.hello"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Task failed: {stripped}")
                self.assertIn("from base", stripped)

                # Clear state
                state_file = project_root / ".tasktree-state"
                if state_file.exists():
                    state_file.unlink()

                # Run right side of the diamond
                result = self.runner.invoke(
                    app, ["right.base.hello"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Task failed: {stripped}")
                self.assertIn("from base", stripped)

                # Clear state
                if state_file.exists():
                    state_file.unlink()

                # Run the root which depends on both sides
                result = self.runner.invoke(app, ["all"], env=self.env)
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Task failed: {stripped}")
                self.assertIn("left done", stripped)
                self.assertIn("right done", stripped)
                self.assertIn("all done", stripped)

            finally:
                os.chdir(original_cwd)

    def test_cyclic_variable_references_across_imports(self):
        """Test that cyclic variable references across imports are properly handled."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # imported.yaml: Variable that tries to reference root variable
            # (After namespacing, {{ var.root_var }} becomes {{ var.imp.root_var }})
            (project_root / "imported.yaml").write_text(
                "variables:\n"
                "  imported_var: '{{ var.root_var }}'\n"
                "tasks:\n"
                "  imported_task:\n"
                "    cmd: echo {{ var.imported_var }}\n"
            )

            # Root file: Variable that references imported variable
            (project_root / "tasktree.yaml").write_text(
                "imports:\n"
                "  - file: imported.yaml\n"
                "    as: imp\n"
                "variables:\n"
                "  root_var: '{{ var.imp.imported_var }}'\n"
                "tasks:\n"
                "  root_task:\n"
                "    deps: [imp.imported_task]\n"
                "    cmd: echo {{ var.root_var }}\n"
            )

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Should fail because imported file's reference to root_var gets rewritten
                # to imp.root_var, which doesn't exist
                result = self.runner.invoke(app, ["root_task"], env=self.env)
                self.assertNotEqual(result.exit_code, 0)
                # Check for error about undefined variable
                self.assertIn("not defined", result.stdout.lower())

            finally:
                os.chdir(original_cwd)

    def test_dockerfile_path_resolution_in_imported_files(self):
        """
        Test documenting current Dockerfile path resolution behavior in imported files.

        CURRENT BEHAVIOR: Dockerfile paths are resolved relative to project root,
        not relative to the imported file. This test documents this limitation.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create subdirectory for imported file
            subdir = project_root / "subdir"
            subdir.mkdir()

            # Create Dockerfile at ROOT (current behavior requires this)
            dockerfile = project_root / "Dockerfile"
            dockerfile.write_text(
                "FROM alpine:latest\n"
                "RUN echo 'Docker image built'\n"
            )

            # Create imported file with runner that references Dockerfile
            # Currently, this path is resolved from project root, not from subdir
            (subdir / "docker.yaml").write_text(
                "runners:\n"
                "  docker_runner:\n"
                "    dockerfile: Dockerfile\n"
                "    context: .\n"
                "tasks:\n"
                "  docker_task:\n"
                "    run_in: docker_runner\n"
                "    cmd: echo 'Running in Docker'\n"
            )

            # Root file imports the docker runner
            (project_root / "tasktree.yaml").write_text(
                "imports:\n"
                "  - file: subdir/docker.yaml\n"
                "    as: docker\n"
                "tasks:\n"
                "  main:\n"
                "    deps: [docker.docker_task]\n"
                "    cmd: echo 'Main task done'\n"
            )

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # With Dockerfile at root, this should work (or fail only due to Docker unavailability)
                result = self.runner.invoke(app, ["main"], env=self.env)

                # The test should either pass (if Docker is available) or fail with
                # a Docker-related error (not a file-not-found error)
                if result.exit_code != 0:
                    # If it fails, it should be due to Docker not being available,
                    # not due to Dockerfile path resolution issues
                    self.assertNotIn("no such file", result.stdout.lower())
                    self.assertNotIn("dockerfile not found", result.stdout.lower())
                else:
                    # If Docker is available, the task should succeed
                    self.assertIn("Main task done", result.stdout)

            finally:
                os.chdir(original_cwd)
