"""Integration tests for built-in variables feature."""

import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from tasktree.executor import Executor
from tasktree.parser import parse_recipe
from tasktree.state import StateManager


class TestBuiltinVariables(unittest.TestCase):
    """Test built-in variable substitution in task execution."""

    def setUp(self):
        """Create temporary directory for test recipes."""
        self.test_dir = tempfile.mkdtemp()
        self.recipe_file = Path(self.test_dir) / "tasktree.yaml"

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_all_builtin_variables_in_command(self):
        """Test that all 8 built-in variables work in task commands."""
        # Create output file path
        output_file = Path(self.test_dir) / "output.txt"

        # Create recipe that uses all built-in variables
        recipe_content = f"""
tasks:
  test-vars:
    cmd: |
      echo "project_root={{{{ tt.project_root }}}}" > {output_file}
      echo "recipe_dir={{{{ tt.recipe_dir }}}}" >> {output_file}
      echo "task_name={{{{ tt.task_name }}}}" >> {output_file}
      echo "working_dir={{{{ tt.working_dir }}}}" >> {output_file}
      echo "timestamp={{{{ tt.timestamp }}}}" >> {output_file}
      echo "timestamp_unix={{{{ tt.timestamp_unix }}}}" >> {output_file}
      echo "user_home={{{{ tt.user_home }}}}" >> {output_file}
      echo "user_name={{{{ tt.user_name }}}}" >> {output_file}
"""
        self.recipe_file.write_text(recipe_content)

        # Parse recipe and execute task
        recipe = parse_recipe(self.recipe_file)
        state = StateManager(recipe.project_root)
        state.load()
        executor = Executor(recipe, state)
        executor.execute_task("test-vars")

        # Read output and verify
        output = output_file.read_text()
        lines = {line.split("=", 1)[0]: line.split("=", 1)[1] for line in output.strip().split("\n")}

        # Verify all variables were substituted
        self.assertIn("project_root", lines)
        self.assertEqual(lines["project_root"], str(recipe.project_root))

        self.assertIn("recipe_dir", lines)
        self.assertEqual(lines["recipe_dir"], str(self.recipe_file.parent))

        self.assertIn("task_name", lines)
        self.assertEqual(lines["task_name"], "test-vars")

        self.assertIn("working_dir", lines)
        self.assertEqual(lines["working_dir"], str(recipe.project_root))

        self.assertIn("timestamp", lines)
        # Verify ISO8601 format
        self.assertRegex(lines["timestamp"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

        self.assertIn("timestamp_unix", lines)
        # Verify Unix timestamp is numeric
        self.assertTrue(lines["timestamp_unix"].isdigit())

        self.assertIn("user_home", lines)
        # Verify it's a valid directory path
        self.assertTrue(Path(lines["user_home"]).is_absolute())

        self.assertIn("user_name", lines)
        # Verify we got some username (could be from os.getlogin() or env var)
        self.assertTrue(len(lines["user_name"]) > 0)

    def test_timestamp_consistency_within_task(self):
        """Test that timestamp is consistent throughout a single task execution."""
        output_file = Path(self.test_dir) / "timestamps.txt"

        recipe_content = f"""
tasks:
  test-timestamp:
    cmd: |
      echo "{{{{ tt.timestamp }}}}" > {output_file}
      sleep 0.1
      echo "{{{{ tt.timestamp }}}}" >> {output_file}
      echo "{{{{ tt.timestamp_unix }}}}" >> {output_file}
      sleep 0.1
      echo "{{{{ tt.timestamp_unix }}}}" >> {output_file}
"""
        self.recipe_file.write_text(recipe_content)

        recipe = parse_recipe(self.recipe_file)
        state = StateManager(recipe.project_root)
        state.load()
        executor = Executor(recipe, state)
        executor.execute_task("test-timestamp")

        output = output_file.read_text()
        lines = output.strip().split("\n")

        # All timestamps should be identical
        self.assertEqual(lines[0], lines[1], "ISO timestamps should be consistent")
        self.assertEqual(lines[2], lines[3], "Unix timestamps should be consistent")

    def test_builtin_vars_with_working_dir(self):
        """Test that tt.working_dir reflects the task's working_dir setting."""
        # Create subdirectory
        subdir = Path(self.test_dir) / "subdir"
        subdir.mkdir()
        output_file = Path(self.test_dir) / "working_dir.txt"

        recipe_content = f"""
tasks:
  test-workdir:
    working_dir: subdir
    cmd: echo "{{{{ tt.working_dir }}}}" > {output_file}
"""
        self.recipe_file.write_text(recipe_content)

        recipe = parse_recipe(self.recipe_file)
        state = StateManager(recipe.project_root)
        state.load()
        executor = Executor(recipe, state)
        executor.execute_task("test-workdir")

        output = output_file.read_text().strip()
        # Should show the absolute path to subdir
        self.assertEqual(output, str(subdir.resolve()))

    def test_builtin_vars_in_multiline_command(self):
        """Test that built-in variables work in multi-line commands."""
        output_file = Path(self.test_dir) / "multiline.txt"

        recipe_content = f"""
tasks:
  test-multiline:
    cmd: |
      PROJECT={{{{ tt.project_root }}}}
      TASK={{{{ tt.task_name }}}}
      echo "$PROJECT/$TASK" > {output_file}
"""
        self.recipe_file.write_text(recipe_content)

        recipe = parse_recipe(self.recipe_file)
        state = StateManager(recipe.project_root)
        state.load()
        executor = Executor(recipe, state)
        executor.execute_task("test-multiline")

        output = output_file.read_text().strip()
        expected = f"{recipe.project_root}/test-multiline"
        self.assertEqual(output, expected)

    def test_recipe_dir_differs_from_project_root_when_recipe_in_subdir(self):
        """Test that recipe_dir points to recipe file location, not project root."""
        # Create recipe in a subdirectory
        recipe_subdir = Path(self.test_dir) / "config"
        recipe_subdir.mkdir()
        recipe_path = recipe_subdir / "tasks.yaml"
        output_file = Path(self.test_dir) / "recipe_dir.txt"

        recipe_content = f"""
tasks:
  test-recipe-dir:
    cmd: |
      echo "project={{{{ tt.project_root }}}}" > {output_file}
      echo "recipe={{{{ tt.recipe_dir }}}}" >> {output_file}
"""
        recipe_path.write_text(recipe_content)

        # Parse with explicit project_root (current directory)
        recipe = parse_recipe(recipe_path, project_root=Path(self.test_dir))
        state = StateManager(recipe.project_root)
        state.load()
        executor = Executor(recipe, state)
        executor.execute_task("test-recipe-dir")

        output = output_file.read_text()
        lines = {line.split("=", 1)[0]: line.split("=", 1)[1] for line in output.strip().split("\n")}

        # project_root should be test_dir
        self.assertEqual(lines["project"], str(Path(self.test_dir)))
        # recipe_dir should be the subdirectory
        self.assertEqual(lines["recipe"], str(recipe_subdir))

    def test_builtin_vars_mixed_with_other_vars(self):
        """Test built-in variables work alongside regular variables and arguments."""
        output_file = Path(self.test_dir) / "mixed.txt"

        recipe_content = f"""
variables:
  server: prod.example.com

tasks:
  deploy:
    args: [region]
    cmd: |
      echo "Deploying from {{{{ tt.project_root }}}}" > {output_file}
      echo "Task: {{{{ tt.task_name }}}}" >> {output_file}
      echo "Server: {{{{ var.server }}}}" >> {output_file}
      echo "Region: {{{{ arg.region }}}}" >> {output_file}
      echo "User: {{{{ tt.user_name }}}}" >> {output_file}
"""
        self.recipe_file.write_text(recipe_content)

        recipe = parse_recipe(self.recipe_file)
        state = StateManager(recipe.project_root)
        state.load()
        executor = Executor(recipe, state)
        executor.execute_task("deploy", args_dict={"region": "us-west-1"})

        output = output_file.read_text()
        lines = [line for line in output.strip().split("\n")]

        self.assertIn(f"Deploying from {recipe.project_root}", lines[0])
        self.assertIn("Task: deploy", lines[1])
        self.assertIn("Server: prod.example.com", lines[2])
        self.assertIn("Region: us-west-1", lines[3])
        # User should be present (from tt.user_name)
        self.assertTrue(lines[4].startswith("User: "))


if __name__ == "__main__":
    unittest.main()
