"""Integration tests for variables feature."""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from tasktree.cli import app


class TestVariablesIntegration(unittest.TestCase):
    """Test end-to-end variables functionality through CLI."""

    def setUp(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_variables_in_command_execution(self):
        """Test task actually runs with variables substituted."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
variables:
  message: "Hello from variables"

tasks:
  test:
    outputs: [output.txt]
    cmd: echo "{{ var.message }}" > output.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["test"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify output contains substituted variable
                output_file = project_root / "output.txt"
                self.assertTrue(output_file.exists())
                content = output_file.read_text().strip()
                self.assertEqual(content, "Hello from variables")

            finally:
                os.chdir(original_cwd)

    def test_variables_with_args_combined(self):
        """Test both vars and args in same command execute correctly."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
variables:
  server: "prod.example.com"
  port: 8080

tasks:
  deploy:
    args: [app_name]
    outputs: ["deploy-{{ arg.app_name }}.log"]
    cmd: echo "Deploy {{ arg.app_name }} to {{ var.server }}:{{ var.port }}" > deploy-{{ arg.app_name }}.log
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task with argument
                result = self.runner.invoke(app, ["deploy", "myapp"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify output contains both substituted variable and argument
                output_file = project_root / "deploy-myapp.log"
                self.assertTrue(output_file.exists())
                content = output_file.read_text().strip()
                self.assertEqual(content, "Deploy myapp to prod.example.com:8080")

            finally:
                os.chdir(original_cwd)

    def test_variable_types_stringify(self):
        """Test int/bool/float become strings in output."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
variables:
  port: 8080
  debug: true
  timeout: 30.5

tasks:
  test:
    outputs: [config.txt]
    cmd: echo "port={{ var.port }} debug={{ var.debug }} timeout={{ var.timeout }}" > config.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["test"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify all types converted to strings
                output_file = project_root / "config.txt"
                content = output_file.read_text().strip()
                self.assertEqual(content, "port=8080 debug=True timeout=30.5")

            finally:
                os.chdir(original_cwd)

    def test_complex_variable_chain(self):
        """Test A uses B, B uses C, all resolve correctly."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
variables:
  protocol: "https"
  domain: "api.example.com"
  base_url: "{{ var.protocol }}://{{ var.domain }}"
  users_endpoint: "{{ var.base_url }}/users"
  posts_endpoint: "{{ var.base_url }}/posts"

tasks:
  test:
    outputs: [endpoints.txt]
    cmd: |
      echo "{{ var.users_endpoint }}" > endpoints.txt
      echo "{{ var.posts_endpoint }}" >> endpoints.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["test"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify variable chain resolved correctly
                output_file = project_root / "endpoints.txt"
                content = output_file.read_text().strip()
                lines = content.split("\n")
                self.assertEqual(lines[0], "https://api.example.com/users")
                self.assertEqual(lines[1], "https://api.example.com/posts")

            finally:
                os.chdir(original_cwd)

    def test_variables_in_working_dir_execution(self):
        """Test working_dir with variables actually changes execution directory."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create subdirectory
            subdir = project_root / "build"
            subdir.mkdir()

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
variables:
  build_dir: "build"

tasks:
  test:
    working_dir: "{{ var.build_dir }}"
    outputs: [build/result.txt]
    cmd: pwd > result.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["test"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify task ran in subdirectory
                output_file = subdir / "result.txt"
                self.assertTrue(output_file.exists())
                content = output_file.read_text().strip()
                # Content should be the absolute path to build directory
                self.assertTrue(content.endswith("build"))

            finally:
                os.chdir(original_cwd)

    def test_variables_in_multiple_tasks(self):
        """Test same variables used across multiple tasks."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
variables:
  version: "1.2.3"
  app_name: "myapp"

tasks:
  build:
    outputs: [build.log]
    cmd: echo "Building {{ var.app_name }} v{{ var.version }}" > build.log

  deploy:
    deps: [build]
    outputs: [deploy.log]
    cmd: echo "Deploying {{ var.app_name }} v{{ var.version }}" > deploy.log
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run deploy task (which depends on build)
                result = self.runner.invoke(app, ["deploy"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify both tasks used variables correctly
                build_output = (project_root / "build.log").read_text().strip()
                self.assertEqual(build_output, "Building myapp v1.2.3")

                deploy_output = (project_root / "deploy.log").read_text().strip()
                self.assertEqual(deploy_output, "Deploying myapp v1.2.3")

            finally:
                os.chdir(original_cwd)

    def test_error_undefined_variable_at_runtime(self):
        """Test clear error message when variable is undefined."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
variables:
  defined: "value"

tasks:
  test:
    cmd: echo "{{ var.undefined }}"
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run should fail with clear error
                result = self.runner.invoke(app, ["test"], env=self.env)
                self.assertNotEqual(result.exit_code, 0)

                # Error should mention the undefined variable
                output = result.stdout
                self.assertIn("undefined", output.lower())

            finally:
                os.chdir(original_cwd)

    def test_error_circular_reference_at_parse_time(self):
        """Test circular reference error is caught at parse time."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            # Test self-referential circular reference
            recipe_file.write_text("""
variables:
  recursive: "value {{ var.recursive }}"

tasks:
  test:
    cmd: 'echo test'
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Should fail at parse time with circular reference error
                result = self.runner.invoke(app, ["test"], env=self.env)
                self.assertNotEqual(result.exit_code, 0)

                # Error should mention circular reference
                output = result.stdout
                self.assertIn("circular", output.lower())

            finally:
                os.chdir(original_cwd)

    def test_variables_with_special_characters(self):
        """Test variables containing special shell characters."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text(r"""
variables:
  message: "Hello $USER from 'variables'"

tasks:
  test:
    outputs: [output.txt]
    cmd: echo "{{ var.message }}" > output.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["test"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify special characters preserved
                output_file = project_root / "output.txt"
                content = output_file.read_text().strip()
                # $USER will be expanded by shell, but quotes should be preserved
                self.assertIn("from 'variables'", content)

            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
