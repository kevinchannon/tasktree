"""Tests for graph module."""

import unittest
from pathlib import Path

from tasktree.graph import (
    CycleError,
    TaskNotFoundError,
    build_dependency_tree,
    get_implicit_inputs,
    resolve_execution_order,
    resolve_self_references,
)
from tasktree.parser import Recipe, Task


class TestResolveExecutionOrder(unittest.TestCase):
    """
    @athena: bddf5f60de23
    """

    def test_single_task(self):
        """
        Test execution order for single task with no dependencies.
        @athena: 25b6e4458e0b
        """
        tasks = {"build": Task(name="build", cmd="cargo build")}
        recipe = Recipe(
            tasks=tasks, project_root=Path.cwd(), recipe_path=Path("tasktree.yaml")
        )

        order = resolve_execution_order(recipe, "build")
        self.assertEqual(order, [("build", None)])

    def test_linear_dependencies(self):
        """
        Test execution order for linear dependency chain.
        @athena: 36db80f88e0d
        """
        tasks = {
            "lint": Task(name="lint", cmd="cargo clippy"),
            "build": Task(name="build", cmd="cargo build", deps=["lint"]),
            "test": Task(name="test", cmd="cargo test", deps=["build"]),
        }
        recipe = Recipe(
            tasks=tasks, project_root=Path.cwd(), recipe_path=Path("tasktree.yaml")
        )

        order = resolve_execution_order(recipe, "test")
        self.assertEqual(order, [("lint", None), ("build", None), ("test", None)])

    def test_diamond_dependencies(self):
        """
        Test execution order for diamond dependency pattern.
        @athena: e6229248ac25
        """
        tasks = {
            "a": Task(name="a", cmd="echo a"),
            "b": Task(name="b", cmd="echo b", deps=["a"]),
            "c": Task(name="c", cmd="echo c", deps=["a"]),
            "d": Task(name="d", cmd="echo d", deps=["b", "c"]),
        }
        recipe = Recipe(
            tasks=tasks, project_root=Path.cwd(), recipe_path=Path("tasktree.yaml")
        )

        order = resolve_execution_order(recipe, "d")
        # Extract task names for easier comparison
        task_names = [name for name, args in order]
        # Should include all tasks
        self.assertEqual(set(task_names), {"a", "b", "c", "d"})
        # Should execute 'a' before 'b' and 'c'
        self.assertLess(task_names.index("a"), task_names.index("b"))
        self.assertLess(task_names.index("a"), task_names.index("c"))
        # Should execute 'b' and 'c' before 'd'
        self.assertLess(task_names.index("b"), task_names.index("d"))
        self.assertLess(task_names.index("c"), task_names.index("d"))

    def test_task_not_found(self):
        """
        Test error when task doesn't exist.
        @athena: 03d6846673d2
        """
        tasks = {"build": Task(name="build", cmd="cargo build")}
        recipe = Recipe(
            tasks=tasks, project_root=Path.cwd(), recipe_path=Path("tasktree.yaml")
        )

        with self.assertRaises(TaskNotFoundError):
            resolve_execution_order(recipe, "nonexistent")


class TestGetImplicitInputs(unittest.TestCase):
    """
    @athena: af2a76679f91
    """

    def test_no_dependencies(self):
        """
        Test implicit inputs for task with no dependencies.
        @athena: b85caf97f461
        """
        tasks = {"build": Task(name="build", cmd="cargo build")}
        recipe = Recipe(
            tasks=tasks, project_root=Path.cwd(), recipe_path=Path("tasktree.yaml")
        )

        implicit = get_implicit_inputs(recipe, tasks["build"])
        self.assertEqual(implicit, [])

    def test_inherit_from_dependency_with_outputs(self):
        """
        Test inheriting outputs from dependency.
        @athena: b1eda5964e2d
        """
        tasks = {
            "build": Task(name="build", cmd="cargo build", outputs=["target/bin"]),
            "package": Task(
                name="package", cmd="tar czf package.tar.gz target/bin", deps=["build"]
            ),
        }
        recipe = Recipe(
            tasks=tasks, project_root=Path.cwd(), recipe_path=Path("tasktree.yaml")
        )

        implicit = get_implicit_inputs(recipe, tasks["package"])
        self.assertEqual(implicit, ["target/bin"])

    def test_inherit_from_dependency_without_outputs(self):
        """
        Test inheriting inputs from dependency without outputs.
        @athena: 9b258fa6f4fc
        """
        tasks = {
            "lint": Task(name="lint", cmd="cargo clippy", inputs=["src/**/*.rs"]),
            "build": Task(name="build", cmd="cargo build", deps=["lint"]),
        }
        recipe = Recipe(
            tasks=tasks, project_root=Path.cwd(), recipe_path=Path("tasktree.yaml")
        )

        implicit = get_implicit_inputs(recipe, tasks["build"])
        self.assertEqual(implicit, ["src/**/*.rs"])


class TestGraphErrors(unittest.TestCase):
    """
    Tests for graph error conditions.
    @athena: 086247682401
    """

    def test_graph_cycle_error(self):
        """
        Test CycleError raised for circular dependencies.
        @athena: a3ad7fd26e99
        """
        # Create a circular dependency: A -> B -> C -> A
        tasks = {
            "a": Task(name="a", cmd="echo a", deps=["b"]),
            "b": Task(name="b", cmd="echo b", deps=["c"]),
            "c": Task(name="c", cmd="echo c", deps=["a"]),
        }
        recipe = Recipe(
            tasks=tasks, project_root=Path.cwd(), recipe_path=Path("tasktree.yaml")
        )

        with self.assertRaises(CycleError):
            resolve_execution_order(recipe, "a")

    def test_graph_build_tree_missing_task(self):
        """
        Test TaskNotFoundError in build_dependency_tree().
        @athena: 188311aaf016
        """
        tasks = {
            "build": Task(name="build", cmd="echo build"),
        }
        recipe = Recipe(
            tasks=tasks, project_root=Path.cwd(), recipe_path=Path("tasktree.yaml")
        )

        from tasktree.graph import TaskNotFoundError, build_dependency_tree

        with self.assertRaises(TaskNotFoundError):
            build_dependency_tree(recipe, "nonexistent")


class TestBuildDependencyTree(unittest.TestCase):
    """
    Tests for build_dependency_tree() function.
    @athena: d08a468e3300
    """

    def test_build_tree_single_task(self):
        """
        Test tree for task with no dependencies.
        @athena: 1244c78bcdf3
        """
        tasks = {"build": Task(name="build", cmd="cargo build")}
        recipe = Recipe(
            tasks=tasks, project_root=Path.cwd(), recipe_path=Path("tasktree.yaml")
        )

        tree = build_dependency_tree(recipe, "build")

        self.assertEqual(tree["name"], "build")
        self.assertEqual(tree["deps"], [])

    def test_build_tree_with_dependencies(self):
        """
        Test tree structure for task with deps.
        @athena: a310fef1d0af
        """
        tasks = {
            "lint": Task(name="lint", cmd="cargo clippy"),
            "build": Task(name="build", cmd="cargo build", deps=["lint"]),
            "test": Task(name="test", cmd="cargo test", deps=["build"]),
        }
        recipe = Recipe(
            tasks=tasks, project_root=Path.cwd(), recipe_path=Path("tasktree.yaml")
        )

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
        """
        Test raises TaskNotFoundError for nonexistent task.
        @athena: 70062ae2c66d
        """
        tasks = {"build": Task(name="build", cmd="echo build")}
        recipe = Recipe(
            tasks=tasks, project_root=Path.cwd(), recipe_path=Path("tasktree.yaml")
        )

        with self.assertRaises(TaskNotFoundError):
            build_dependency_tree(recipe, "nonexistent")

    def test_build_tree_includes_task_info(self):
        """
        Test tree includes task name and deps structure.
        @athena: aa72fa35fc90
        """
        tasks = {
            "a": Task(name="a", cmd="echo a"),
            "b": Task(name="b", cmd="echo b", deps=["a"]),
            "c": Task(name="c", cmd="echo c", deps=["a"]),
            "d": Task(name="d", cmd="echo d", deps=["b", "c"]),
        }
        recipe = Recipe(
            tasks=tasks, project_root=Path.cwd(), recipe_path=Path("tasktree.yaml")
        )

        tree = build_dependency_tree(recipe, "d")

        # Root should be "d"
        self.assertEqual(tree["name"], "d")
        # Should have two dependencies
        self.assertEqual(len(tree["deps"]), 2)
        # Both b and c should be in deps
        dep_names = {dep["name"] for dep in tree["deps"]}
        self.assertEqual(dep_names, {"b", "c"})


class TestResolveSelfReferences(unittest.TestCase):
    """
    Test resolve_self_references function.
    @athena: 616b3369d1f0
    """

    def test_resolve_self_references_in_command(self):
        """
        Test that self-references in cmd field are resolved.
        @athena: 95791267b955
        """
        task = Task(
            name="copy",
            cmd="cp {{ self.inputs.src }} {{ self.outputs.dest }}",
            inputs=[{"src": "input.txt"}],
            outputs=[{"dest": "output.txt"}],
        )
        tasks = {"copy": task}
        recipe = Recipe(
            tasks=tasks, project_root=Path.cwd(), recipe_path=Path("tasktree.yaml")
        )
        ordered_tasks = [("copy", None)]

        resolve_self_references(recipe, ordered_tasks)

        self.assertEqual(task.cmd, "cp input.txt output.txt")

    def test_resolve_self_references_in_working_dir(self):
        """
        Test that self-references in working_dir field are resolved.
        @athena: 13752a32f485
        """
        task = Task(
            name="build",
            cmd="make",
            inputs=[{"project": "myproject"}],
            working_dir="{{ self.inputs.project }}/build",
        )
        tasks = {"build": task}
        recipe = Recipe(
            tasks=tasks, project_root=Path.cwd(), recipe_path=Path("tasktree.yaml")
        )
        ordered_tasks = [("build", None)]

        resolve_self_references(recipe, ordered_tasks)

        self.assertEqual(task.working_dir, "myproject/build")

    def test_resolve_self_references_in_arg_defaults(self):
        """
        Test that self-references in argument defaults are resolved.
        @athena: 266f9b3c4467
        """
        task = Task(
            name="deploy",
            cmd="deploy",
            outputs=[{"artifact": "dist/app.js"}],
            args=[
                {"target": {"type": "str", "default": "{{ self.outputs.artifact }}"}}
            ],
        )
        tasks = {"deploy": task}
        recipe = Recipe(
            tasks=tasks, project_root=Path.cwd(), recipe_path=Path("tasktree.yaml")
        )
        ordered_tasks = [("deploy", None)]

        resolve_self_references(recipe, ordered_tasks)

        # Check that the default was resolved
        self.assertEqual(task.args[0]["target"]["default"], "dist/app.js")

    def test_resolve_self_references_multiple_tasks(self):
        """
        Test that self-references are resolved for multiple tasks.
        @athena: 1f6b57be8641
        """
        task1 = Task(
            name="task1",
            cmd="process {{ self.inputs.in1 }}",
            inputs=[{"in1": "file1.txt"}],
        )
        task2 = Task(
            name="task2",
            cmd="process {{ self.inputs.in2 }}",
            inputs=[{"in2": "file2.txt"}],
        )
        tasks = {"task1": task1, "task2": task2}
        recipe = Recipe(
            tasks=tasks, project_root=Path.cwd(), recipe_path=Path("tasktree.yaml")
        )
        ordered_tasks = [("task1", None), ("task2", None)]

        resolve_self_references(recipe, ordered_tasks)

        self.assertEqual(task1.cmd, "process file1.txt")
        self.assertEqual(task2.cmd, "process file2.txt")

    def test_resolve_self_references_no_refs(self):
        """
        Test that tasks without self-references are unchanged.
        @athena: d0c6812747a8
        """
        task = Task(
            name="build",
            cmd="make build",
            inputs=["src/**/*.c"],
            outputs=["bin/app"],
        )
        tasks = {"build": task}
        recipe = Recipe(
            tasks=tasks, project_root=Path.cwd(), recipe_path=Path("tasktree.yaml")
        )
        ordered_tasks = [("build", None)]

        resolve_self_references(recipe, ordered_tasks)

        # Command should be unchanged
        self.assertEqual(task.cmd, "make build")

    def test_resolve_self_references_error_propagates(self):
        """
        Test that validation errors from substitute_self_references propagate.
        @athena: 72fc599ff001
        """
        task = Task(
            name="build",
            cmd="cp {{ self.inputs.missing }}",  # Reference to non-existent input
            inputs=[{"src": "file.txt"}],  # Only has 'src', not 'missing'
        )
        tasks = {"build": task}
        recipe = Recipe(
            tasks=tasks, project_root=Path.cwd(), recipe_path=Path("tasktree.yaml")
        )
        ordered_tasks = [("build", None)]

        with self.assertRaises(ValueError) as cm:
            resolve_self_references(recipe, ordered_tasks)

        error_msg = str(cm.exception)
        self.assertIn("missing", error_msg)
        self.assertIn("src", error_msg)  # Available input should be mentioned


if __name__ == "__main__":
    unittest.main()
