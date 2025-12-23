"""Tests for graph module."""

import unittest

from tasktree.graph import (
    CycleError,
    TaskNotFoundError,
    build_dependency_tree,
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


class TestGraphErrors(unittest.TestCase):
    """Tests for graph error conditions."""

    def test_graph_cycle_error(self):
        """Test CycleError raised for circular dependencies."""
        # Create a circular dependency: A -> B -> C -> A
        tasks = {
            "a": Task(name="a", cmd="echo a", deps=["b"]),
            "b": Task(name="b", cmd="echo b", deps=["c"]),
            "c": Task(name="c", cmd="echo c", deps=["a"]),
        }
        recipe = Recipe(tasks=tasks, project_root=None)

        from tasktree.graph import CycleError

        with self.assertRaises(CycleError):
            resolve_execution_order(recipe, "a")

    def test_graph_build_tree_missing_task(self):
        """Test TaskNotFoundError in build_dependency_tree()."""
        tasks = {
            "build": Task(name="build", cmd="echo build"),
        }
        recipe = Recipe(tasks=tasks, project_root=None)

        from tasktree.graph import TaskNotFoundError, build_dependency_tree

        with self.assertRaises(TaskNotFoundError):
            build_dependency_tree(recipe, "nonexistent")


class TestBuildDependencyTree(unittest.TestCase):
    """Tests for build_dependency_tree() function."""

    def test_build_tree_single_task(self):
        """Test tree for task with no dependencies."""
        tasks = {"build": Task(name="build", cmd="cargo build")}
        recipe = Recipe(tasks=tasks, project_root=None)

        tree = build_dependency_tree(recipe, "build")

        self.assertEqual(tree["name"], "build")
        self.assertEqual(tree["deps"], [])

    def test_build_tree_with_dependencies(self):
        """Test tree structure for task with deps."""
        tasks = {
            "lint": Task(name="lint", cmd="cargo clippy"),
            "build": Task(name="build", cmd="cargo build", deps=["lint"]),
            "test": Task(name="test", cmd="cargo test", deps=["build"]),
        }
        recipe = Recipe(tasks=tasks, project_root=None)

        tree = build_dependency_tree(recipe, "test")

        # Root should be "test"
        self.assertEqual(tree["name"], "test")
        # Should have one dependency (build)
        self.assertEqual(len(tree["deps"]), 1)
        self.assertEqual(tree["deps"][0]["name"], "build")
        # build should have one dependency (lint)
        self.assertEqual(len(tree["deps"][0]["deps"]), 1)
        self.assertEqual(tree["deps"][0]["deps"][0]["name"], "lint")
        # lint should have no dependencies
        self.assertEqual(tree["deps"][0]["deps"][0]["deps"], [])

    def test_build_tree_missing_task(self):
        """Test raises TaskNotFoundError for nonexistent task."""
        tasks = {"build": Task(name="build", cmd="echo build")}
        recipe = Recipe(tasks=tasks, project_root=None)

        with self.assertRaises(TaskNotFoundError):
            build_dependency_tree(recipe, "nonexistent")

    def test_build_tree_includes_task_info(self):
        """Test tree includes task name and deps structure."""
        tasks = {
            "a": Task(name="a", cmd="echo a"),
            "b": Task(name="b", cmd="echo b", deps=["a"]),
            "c": Task(name="c", cmd="echo c", deps=["a"]),
            "d": Task(name="d", cmd="echo d", deps=["b", "c"]),
        }
        recipe = Recipe(tasks=tasks, project_root=None)

        tree = build_dependency_tree(recipe, "d")

        # Root should be "d"
        self.assertEqual(tree["name"], "d")
        # Should have two dependencies
        self.assertEqual(len(tree["deps"]), 2)
        # Both b and c should be in deps
        dep_names = {dep["name"] for dep in tree["deps"]}
        self.assertEqual(dep_names, {"b", "c"})


if __name__ == "__main__":
    unittest.main()
