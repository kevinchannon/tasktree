"""Tests for private task field parsing."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tasktree.parser import parse_recipe


class TestPrivateTaskParsing(unittest.TestCase):
    """Test parsing of private field in task definitions."""

    def test_parse_task_with_private_true(self):
        """Test parsing task with private: true."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
tasks:
  hidden-task:
    private: true
    cmd: echo secret
""")
            recipe = parse_recipe(recipe_path)
            task = recipe.get_task("hidden-task")
            self.assertIsNotNone(task)
            self.assertTrue(task.private)

    def test_parse_task_with_private_false(self):
        """Test parsing task with explicit private: false."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
tasks:
  public-task:
    private: false
    cmd: echo public
""")
            recipe = parse_recipe(recipe_path)
            task = recipe.get_task("public-task")
            self.assertIsNotNone(task)
            self.assertFalse(task.private)

    def test_parse_task_without_private_field(self):
        """Test parsing task without private field (defaults to false)."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
tasks:
  default-task:
    cmd: echo default
""")
            recipe = parse_recipe(recipe_path)
            task = recipe.get_task("default-task")
            self.assertIsNotNone(task)
            self.assertFalse(task.private)

    def test_parse_multiple_tasks_with_mixed_privacy(self):
        """Test parsing multiple tasks with different privacy settings."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
tasks:
  public1:
    cmd: echo public1

  private1:
    private: true
    cmd: echo private1

  public2:
    private: false
    cmd: echo public2

  private2:
    private: true
    cmd: echo private2
""")
            recipe = parse_recipe(recipe_path)

            # Check public tasks
            self.assertFalse(recipe.get_task("public1").private)
            self.assertFalse(recipe.get_task("public2").private)

            # Check private tasks
            self.assertTrue(recipe.get_task("private1").private)
            self.assertTrue(recipe.get_task("private2").private)

    def test_private_task_with_dependencies(self):
        """Test that private tasks can have dependencies."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
tasks:
  helper:
    private: true
    cmd: echo helper

  main:
    deps: [helper]
    cmd: echo main
""")
            recipe = parse_recipe(recipe_path)

            helper = recipe.get_task("helper")
            main = recipe.get_task("main")

            self.assertTrue(helper.private)
            self.assertFalse(main.private)
            self.assertEqual(main.deps, ["helper"])

    def test_private_task_with_all_fields(self):
        """Test that private field works with all other task fields."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
tasks:
  complex-private:
    desc: A complex private task
    private: true
    deps: []
    inputs: ["src/**/*.py"]
    outputs: ["build/output.txt"]
    working_dir: ./build
    args:
      - mode
    cmd: echo {{ arg.mode }}
""")
            recipe = parse_recipe(recipe_path)
            task = recipe.get_task("complex-private")

            self.assertIsNotNone(task)
            self.assertTrue(task.private)
            self.assertEqual(task.desc, "A complex private task")
            self.assertEqual(task.inputs, ["src/**/*.py"])
            self.assertEqual(task.outputs, ["build/output.txt"])
            self.assertEqual(task.working_dir, "./build")
            self.assertEqual(task.args, ["mode"])


if __name__ == "__main__":
    unittest.main()
