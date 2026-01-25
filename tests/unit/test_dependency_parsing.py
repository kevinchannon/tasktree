import unittest
from pathlib import Path
from tasktree.parser import (
    Recipe,
    Task,
    parse_dependency_spec,
    DependencyInvocation,
)


class TestDependencyParsing(unittest.TestCase):
    """
    Test parsing of parameterized dependencies.
    @athena: 377f0674ccea
    """

    def setUp(self):
        """
        Create a test recipe with parameterized tasks.
        @athena: 2a6b10e1592a
        """
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
        """
        Test parsing simple string dependency.
        @athena: 2d7aac1d464a
        """
        dep_inv = parse_dependency_spec("build", self.recipe)
        self.assertEqual(dep_inv.task_name, "build")
        self.assertIsNone(dep_inv.args)

    def test_parse_positional_args(self):
        """
        Test parsing positional args dependency.
        @athena: 5fce31a4656d
        """
        dep_spec = {"process": ["debug", True]}
        dep_inv = parse_dependency_spec(dep_spec, self.recipe)
        self.assertEqual(dep_inv.task_name, "process")
        self.assertEqual(dep_inv.args, {"mode": "debug", "verbose": True})

    def test_parse_positional_args_with_defaults(self):
        """
        Test parsing positional args with defaults filled.
        @athena: f641cd245bc3
        """
        dep_spec = {"process": ["release"]}
        dep_inv = parse_dependency_spec(dep_spec, self.recipe)
        self.assertEqual(dep_inv.task_name, "process")
        self.assertEqual(dep_inv.args, {"mode": "release", "verbose": "false"})

    def test_parse_named_args(self):
        """
        Test parsing named args dependency.
        @athena: d680271f00bb
        """
        dep_spec = {"process": {"mode": "debug", "verbose": True}}
        dep_inv = parse_dependency_spec(dep_spec, self.recipe)
        self.assertEqual(dep_inv.task_name, "process")
        self.assertEqual(dep_inv.args, {"mode": "debug", "verbose": True})

    def test_parse_named_args_with_defaults(self):
        """
        Test parsing named args with defaults filled.
        @athena: 83fd7dde5afb
        """
        dep_spec = {"process": {"mode": "production"}}
        dep_inv = parse_dependency_spec(dep_spec, self.recipe)
        self.assertEqual(dep_inv.task_name, "process")
        self.assertEqual(dep_inv.args, {"mode": "production", "verbose": "false"})

    def test_reject_empty_arg_list(self):
        """
        Test that empty argument list is rejected.
        @athena: 1c5d13ccb9e1
        """
        dep_spec = {"process": []}
        with self.assertRaises(ValueError) as cm:
            parse_dependency_spec(dep_spec, self.recipe)
        self.assertIn("Empty argument list", str(cm.exception))

    def test_reject_multi_key_dict(self):
        """
        Test that multi-key dict is rejected.
        @athena: 64d5cf0d614a
        """
        dep_spec = {"process": ["debug"], "build": []}
        with self.assertRaises(ValueError) as cm:
            parse_dependency_spec(dep_spec, self.recipe)
        self.assertIn("exactly one key", str(cm.exception))

    def test_reject_too_many_positional_args(self):
        """
        Test that too many positional args is rejected.
        @athena: e875defa134c
        """
        dep_spec = {"process": ["debug", True, "extra"]}
        with self.assertRaises(ValueError) as cm:
            parse_dependency_spec(dep_spec, self.recipe)
        self.assertIn("takes 2 arguments, got 3", str(cm.exception))

    def test_reject_unknown_named_arg(self):
        """
        Test that unknown named arg is rejected.
        @athena: 216b1bf4fb08
        """
        dep_spec = {"process": {"mode": "debug", "unknown": "value"}}
        with self.assertRaises(ValueError) as cm:
            parse_dependency_spec(dep_spec, self.recipe)
        self.assertIn("no argument named 'unknown'", str(cm.exception))

    def test_reject_missing_required_arg(self):
        """
        Test that missing required arg is rejected.
        @athena: cd66e54cdbc8
        """
        dep_spec = {"process": {}}
        with self.assertRaises(ValueError) as cm:
            parse_dependency_spec(dep_spec, self.recipe)
        self.assertIn("requires argument 'mode'", str(cm.exception))

    def test_reject_task_not_found(self):
        """
        Test that nonexistent task is rejected.
        @athena: a48138ad90ee
        """
        dep_spec = {"nonexistent": ["arg"]}
        with self.assertRaises(ValueError) as cm:
            parse_dependency_spec(dep_spec, self.recipe)
        self.assertIn("not found: nonexistent", str(cm.exception))

    def test_task_with_no_args_rejects_args(self):
        """
        Test that task with no args rejects argument specifications.
        @athena: 0c3198d9492d
        """
        dep_spec = {"build": ["arg"]}
        with self.assertRaises(ValueError) as cm:
            parse_dependency_spec(dep_spec, self.recipe)
        self.assertIn("takes no arguments", str(cm.exception))


class TestDependencyInvocationEquality(unittest.TestCase):
    """
    Test DependencyInvocation equality and hashing.
    @athena: 564597bb32ea
    """

    def test_equality_same_task_no_args(self):
        """
        Test equality for same task without args.
        @athena: a5f08df9f8a1
        """
        dep1 = DependencyInvocation("build", None)
        dep2 = DependencyInvocation("build", None)
        self.assertEqual(dep1.task_name, dep2.task_name)
        self.assertEqual(dep1.args, dep2.args)

    def test_equality_same_task_same_args(self):
        """
        Test equality for same task with same args.
        @athena: 39f8306ae4d1
        """
        dep1 = DependencyInvocation("process", {"mode": "debug"})
        dep2 = DependencyInvocation("process", {"mode": "debug"})
        self.assertEqual(dep1.task_name, dep2.task_name)
        self.assertEqual(dep1.args, dep2.args)

    def test_inequality_different_tasks(self):
        """
        Test inequality for different tasks.
        @athena: e0094ebb87b8
        """
        dep1 = DependencyInvocation("build", None)
        dep2 = DependencyInvocation("process", None)
        self.assertNotEqual(dep1.task_name, dep2.task_name)

    def test_inequality_same_task_different_args(self):
        """
        Test inequality for same task with different args.
        @athena: 1f0a0b632e9b
        """
        dep1 = DependencyInvocation("process", {"mode": "debug"})
        dep2 = DependencyInvocation("process", {"mode": "release"})
        self.assertEqual(dep1.task_name, dep2.task_name)
        self.assertNotEqual(dep1.args, dep2.args)


if __name__ == "__main__":
    unittest.main()
