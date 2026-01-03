import unittest
from pathlib import Path
from tasktree.parser import (
    Recipe,
    Task,
    parse_dependency_spec,
    DependencyInvocation,
    _parse_positional_dependency_args,
    _parse_named_dependency_args,
)


class TestDependencyParsing(unittest.TestCase):
    """Test parsing of parameterized dependencies."""

    def setUp(self):
        """Create a test recipe with parameterized tasks."""
        self.task_with_args = Task(
            name="process",
            cmd="echo mode={{arg.mode}} verbose={{arg.verbose}}",
            args=["mode", {"verbose": {"default": "false"}}],
        )
        self.task_no_args = Task(
            name="build",
            cmd="make build",
            args=[],
        )
        self.tasks = {
            "process": self.task_with_args,
            "build": self.task_no_args,
        }
        self.recipe = Recipe(
            tasks=self.tasks,
            project_root=Path("/test"),
            recipe_path=Path("/test/tasktree.yaml"),
        )

    def test_parse_simple_string_dependency(self):
        """Test parsing simple string dependency."""
        dep_inv = parse_dependency_spec("build", self.recipe)
        self.assertEqual(dep_inv.task_name, "build")
        self.assertIsNone(dep_inv.args)

    def test_parse_positional_args(self):
        """Test parsing positional args dependency."""
        dep_spec = {"process": ["debug", True]}
        dep_inv = parse_dependency_spec(dep_spec, self.recipe)
        self.assertEqual(dep_inv.task_name, "process")
        self.assertEqual(dep_inv.args, {"mode": "debug", "verbose": True})

    def test_parse_positional_args_with_defaults(self):
        """Test parsing positional args with defaults filled."""
        dep_spec = {"process": ["release"]}
        dep_inv = parse_dependency_spec(dep_spec, self.recipe)
        self.assertEqual(dep_inv.task_name, "process")
        self.assertEqual(dep_inv.args, {"mode": "release", "verbose": "false"})

    def test_parse_named_args(self):
        """Test parsing named args dependency."""
        dep_spec = {"process": {"mode": "debug", "verbose": True}}
        dep_inv = parse_dependency_spec(dep_spec, self.recipe)
        self.assertEqual(dep_inv.task_name, "process")
        self.assertEqual(dep_inv.args, {"mode": "debug", "verbose": True})

    def test_parse_named_args_with_defaults(self):
        """Test parsing named args with defaults filled."""
        dep_spec = {"process": {"mode": "production"}}
        dep_inv = parse_dependency_spec(dep_spec, self.recipe)
        self.assertEqual(dep_inv.task_name, "process")
        self.assertEqual(dep_inv.args, {"mode": "production", "verbose": "false"})

    def test_reject_empty_arg_list(self):
        """Test that empty argument list is rejected."""
        dep_spec = {"process": []}
        with self.assertRaises(ValueError) as cm:
            parse_dependency_spec(dep_spec, self.recipe)
        self.assertIn("Empty argument list", str(cm.exception))

    def test_reject_multi_key_dict(self):
        """Test that multi-key dict is rejected."""
        dep_spec = {"process": ["debug"], "build": []}
        with self.assertRaises(ValueError) as cm:
            parse_dependency_spec(dep_spec, self.recipe)
        self.assertIn("exactly one key", str(cm.exception))

    def test_reject_too_many_positional_args(self):
        """Test that too many positional args is rejected."""
        dep_spec = {"process": ["debug", True, "extra"]}
        with self.assertRaises(ValueError) as cm:
            parse_dependency_spec(dep_spec, self.recipe)
        self.assertIn("takes 2 arguments, got 3", str(cm.exception))

    def test_reject_unknown_named_arg(self):
        """Test that unknown named arg is rejected."""
        dep_spec = {"process": {"mode": "debug", "unknown": "value"}}
        with self.assertRaises(ValueError) as cm:
            parse_dependency_spec(dep_spec, self.recipe)
        self.assertIn("no argument named 'unknown'", str(cm.exception))

    def test_reject_missing_required_arg(self):
        """Test that missing required arg is rejected."""
        dep_spec = {"process": {}}
        with self.assertRaises(ValueError) as cm:
            parse_dependency_spec(dep_spec, self.recipe)
        self.assertIn("requires argument 'mode'", str(cm.exception))

    def test_reject_task_not_found(self):
        """Test that nonexistent task is rejected."""
        dep_spec = {"nonexistent": ["arg"]}
        with self.assertRaises(ValueError) as cm:
            parse_dependency_spec(dep_spec, self.recipe)
        self.assertIn("not found: nonexistent", str(cm.exception))

    def test_task_with_no_args_rejects_args(self):
        """Test that task with no args rejects argument specifications."""
        dep_spec = {"build": ["arg"]}
        with self.assertRaises(ValueError) as cm:
            parse_dependency_spec(dep_spec, self.recipe)
        self.assertIn("takes no arguments", str(cm.exception))


class TestDependencyInvocationEquality(unittest.TestCase):
    """Test DependencyInvocation equality and hashing."""

    def test_equality_same_task_no_args(self):
        """Test equality for same task without args."""
        dep1 = DependencyInvocation("build", None)
        dep2 = DependencyInvocation("build", None)
        self.assertEqual(dep1.task_name, dep2.task_name)
        self.assertEqual(dep1.args, dep2.args)

    def test_equality_same_task_same_args(self):
        """Test equality for same task with same args."""
        dep1 = DependencyInvocation("process", {"mode": "debug"})
        dep2 = DependencyInvocation("process", {"mode": "debug"})
        self.assertEqual(dep1.task_name, dep2.task_name)
        self.assertEqual(dep1.args, dep2.args)

    def test_inequality_different_tasks(self):
        """Test inequality for different tasks."""
        dep1 = DependencyInvocation("build", None)
        dep2 = DependencyInvocation("process", None)
        self.assertNotEqual(dep1.task_name, dep2.task_name)

    def test_inequality_same_task_different_args(self):
        """Test inequality for same task with different args."""
        dep1 = DependencyInvocation("process", {"mode": "debug"})
        dep2 = DependencyInvocation("process", {"mode": "release"})
        self.assertEqual(dep1.task_name, dep2.task_name)
        self.assertNotEqual(dep1.args, dep2.args)


if __name__ == "__main__":
    unittest.main()
