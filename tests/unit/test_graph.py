"""Tests for graph module."""

import unittest

from tasktree.graph import (
    CycleError,
    TaskNotFoundError,
    get_implicit_inputs,
    resolve_execution_order,
)
from tasktree.parser import Recipe, Task


class TestResolveExecutionOrder(unittest.TestCase):
    def test_single_task(self):
        """Test execution order for single task with no dependencies."""
        tasks = {"build": Task(name="build", cmd="cargo build")}
        recipe = Recipe(tasks=tasks, project_root=None)

        order = resolve_execution_order(recipe, "build")
        self.assertEqual(order, ["build"])

    def test_linear_dependencies(self):
        """Test execution order for linear dependency chain."""
        tasks = {
            "lint": Task(name="lint", cmd="cargo clippy"),
            "build": Task(name="build", cmd="cargo build", deps=["lint"]),
            "test": Task(name="test", cmd="cargo test", deps=["build"]),
        }
        recipe = Recipe(tasks=tasks, project_root=None)

        order = resolve_execution_order(recipe, "test")
        self.assertEqual(order, ["lint", "build", "test"])

    def test_diamond_dependencies(self):
        """Test execution order for diamond dependency pattern."""
        tasks = {
            "a": Task(name="a", cmd="echo a"),
            "b": Task(name="b", cmd="echo b", deps=["a"]),
            "c": Task(name="c", cmd="echo c", deps=["a"]),
            "d": Task(name="d", cmd="echo d", deps=["b", "c"]),
        }
        recipe = Recipe(tasks=tasks, project_root=None)

        order = resolve_execution_order(recipe, "d")
        # Should include all tasks
        self.assertEqual(set(order), {"a", "b", "c", "d"})
        # Should execute 'a' before 'b' and 'c'
        self.assertLess(order.index("a"), order.index("b"))
        self.assertLess(order.index("a"), order.index("c"))
        # Should execute 'b' and 'c' before 'd'
        self.assertLess(order.index("b"), order.index("d"))
        self.assertLess(order.index("c"), order.index("d"))

    def test_task_not_found(self):
        """Test error when task doesn't exist."""
        tasks = {"build": Task(name="build", cmd="cargo build")}
        recipe = Recipe(tasks=tasks, project_root=None)

        with self.assertRaises(TaskNotFoundError):
            resolve_execution_order(recipe, "nonexistent")


class TestGetImplicitInputs(unittest.TestCase):
    def test_no_dependencies(self):
        """Test implicit inputs for task with no dependencies."""
        tasks = {"build": Task(name="build", cmd="cargo build")}
        recipe = Recipe(tasks=tasks, project_root=None)

        implicit = get_implicit_inputs(recipe, tasks["build"])
        self.assertEqual(implicit, [])

    def test_inherit_from_dependency_with_outputs(self):
        """Test inheriting outputs from dependency."""
        tasks = {
            "build": Task(name="build", cmd="cargo build", outputs=["target/bin"]),
            "package": Task(
                name="package", cmd="tar czf package.tar.gz target/bin", deps=["build"]
            ),
        }
        recipe = Recipe(tasks=tasks, project_root=None)

        implicit = get_implicit_inputs(recipe, tasks["package"])
        self.assertEqual(implicit, ["target/bin"])

    def test_inherit_from_dependency_without_outputs(self):
        """Test inheriting inputs from dependency without outputs."""
        tasks = {
            "lint": Task(name="lint", cmd="cargo clippy", inputs=["src/**/*.rs"]),
            "build": Task(name="build", cmd="cargo build", deps=["lint"]),
        }
        recipe = Recipe(tasks=tasks, project_root=None)

        implicit = get_implicit_inputs(recipe, tasks["build"])
        self.assertEqual(implicit, ["src/**/*.rs"])


if __name__ == "__main__":
    unittest.main()
