"""Tests for graph module."""

import unittest
from pathlib import Path

from tasktree.graph import (
    CycleError,
    TaskNotFoundError,
    build_dependency_tree,
    get_implicit_inputs,
    resolve_dependency_output_references,
    resolve_execution_order,
    resolve_self_references,
)
from tasktree.parser import DockerRunner, Recipe, Runner, Task


class TestResolveExecutionOrder(unittest.TestCase):
    """
    """

    def test_single_task(self):
        """
        Test execution order for single task with no dependencies.
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
        """
        tasks = {"build": Task(name="build", cmd="cargo build")}
        recipe = Recipe(
            tasks=tasks, project_root=Path.cwd(), recipe_path=Path("tasktree.yaml")
        )

        with self.assertRaises(TaskNotFoundError):
            resolve_execution_order(recipe, "nonexistent")


class TestGetImplicitInputs(unittest.TestCase):
    """
    """

    def test_no_dependencies(self):
        """
        Test implicit inputs for task with no dependencies.
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

    def test_inherit_named_inputs_as_paths_not_dicts(self):
        """
        A named input is a {name: path} dict. Inheriting it verbatim would
        put a dict into a list of glob patterns; only the path is inherited.
        """
        tasks = {
            "lint": Task(
                name="lint", cmd="cargo clippy", inputs=[{"sources": "src/**/*.rs"}]
            ),
            "build": Task(name="build", cmd="cargo build", deps=["lint"]),
        }
        recipe = Recipe(
            tasks=tasks, project_root=Path.cwd(), recipe_path=Path("tasktree.yaml")
        )

        implicit = get_implicit_inputs(recipe, tasks["build"])
        self.assertEqual(implicit, ["src/**/*.rs"])

    def test_inherited_patterns_go_through_the_injected_renderer(self):
        """
        The executor owns rendering and injects it; this function only says
        which pattern belongs to which dependency invocation. Asserting on
        the arguments it hands over is the contract that matters.
        """
        tasks = {
            "build": Task(
                name="build",
                cmd="build",
                args=[{"config": {"default": "debug"}}],
                outputs=["out/{{ arg.config }}/bin"],
            ),
            "package": Task(name="package", cmd="package", deps=["build"]),
        }
        recipe = Recipe(
            tasks=tasks, project_root=Path.cwd(), recipe_path=Path("tasktree.yaml")
        )
        seen = []

        def render(pattern, dep_task, dep_args):
            seen.append((pattern, dep_task.name, dict(dep_args)))
            return "rendered"

        implicit = get_implicit_inputs(
            recipe, tasks["package"], render_pattern=render
        )

        self.assertEqual(implicit, ["rendered"])
        self.assertEqual(
            seen, [("out/{{ arg.config }}/bin", "build", {"config": "debug"})]
        )

    def test_unresolvable_inherited_pattern_is_kept_as_it_stands(self):
        """
        A dependency path naming something the renderer cannot resolve must
        not fail the whole freshness check.
        """
        tasks = {
            "build": Task(name="build", cmd="build", outputs=["out/{{ arg.gone }}"]),
            "package": Task(name="package", cmd="package", deps=["build"]),
        }
        recipe = Recipe(
            tasks=tasks, project_root=Path.cwd(), recipe_path=Path("tasktree.yaml")
        )

        def render(pattern, dep_task, dep_args):
            raise ValueError("undefined")

        implicit = get_implicit_inputs(
            recipe, tasks["package"], render_pattern=render
        )

        self.assertEqual(implicit, ["out/{{ arg.gone }}"])

    def test_inherit_templated_outputs_from_parametrised_dependency(self):
        """
        Outputs that contain {{ arg.* }} templates must be rendered with the
        dependency's resolved args, not returned as raw template strings.

        This is the regression case: unit-test / integration-test depend on
        build which declares outputs like "out/build/{{ arg.config }}/binary".
        Without rendering, get_implicit_inputs returns the literal template
        string, which never matches any file, so the test tasks appear
        up-to-date even after a rebuild.
        """
        tasks = {
            "build": Task(
                name="build",
                cmd="cmake --build out/build/{{ arg.config }}",
                args=[{"config": {"choices": ["debug", "release"], "default": "debug"}}],
                outputs=["out/build/{{ arg.config }}/warpspeed-tests"],
            ),
            "unit-test": Task(
                name="unit-test",
                cmd="ctest --test-dir out/build/{{ arg.config }}",
                args=[{"config": {"choices": ["debug", "release"], "default": "debug"}}],
                deps=[{"build": ["{{ arg.config }}"]}],
                outputs=["out/evidence/unit_test_result.xml"],
            ),
        }
        recipe = Recipe(
            tasks=tasks, project_root=Path.cwd(), recipe_path=Path("tasktree.yaml")
        )

        implicit = get_implicit_inputs(recipe, tasks["unit-test"], {"config": "debug"})
        self.assertEqual(implicit, ["out/build/debug/warpspeed-tests"])

    def test_inherit_templated_outputs_uses_release_config(self):
        """
        The rendered path must reflect the actual arg value passed, not the
        default.  Running with config=release should yield the release path.
        """
        tasks = {
            "build": Task(
                name="build",
                cmd="cmake --build out/build/{{ arg.config }}",
                args=[{"config": {"choices": ["debug", "release"], "default": "debug"}}],
                outputs=["out/build/{{ arg.config }}/warpspeed-tests"],
            ),
            "unit-test": Task(
                name="unit-test",
                cmd="ctest --test-dir out/build/{{ arg.config }}",
                args=[{"config": {"choices": ["debug", "release"], "default": "debug"}}],
                deps=[{"build": ["{{ arg.config }}"]}],
                outputs=["out/evidence/unit_test_result.xml"],
            ),
        }
        recipe = Recipe(
            tasks=tasks, project_root=Path.cwd(), recipe_path=Path("tasktree.yaml")
        )

        implicit = get_implicit_inputs(recipe, tasks["unit-test"], {"config": "release"})
        self.assertEqual(implicit, ["out/build/release/warpspeed-tests"])

    def test_docker_runner_task_inherits_dependency_outputs(self):
        """
        Test that a Docker-runner task inherits dependency outputs as implicit inputs.
        """
        runner = DockerRunner(name="docker", dockerfile="Dockerfile", context=".")
        tasks = {
            "build": Task(name="build", cmd="make", outputs=["build/output.txt"]),
            "package": Task(
                name="package", cmd="zip package.zip build/output.txt",
                deps=["build"], runner="docker"
            ),
        }
        recipe = Recipe(
            tasks=tasks,
            project_root=Path("/tmp"),
            recipe_path=Path("/tmp/tasktree.yaml"),
            runners={"docker": runner},
        )

        implicit = get_implicit_inputs(recipe, tasks["package"])
        self.assertIn("build/output.txt", implicit)
        # Docker build artifacts are no longer implicit inputs; environment changes
        # are detected via the built image's content fingerprint instead.
        self.assertNotIn("Dockerfile", implicit)


class TestGraphErrors(unittest.TestCase):
    """
    Tests for graph error conditions.
    """

    def test_graph_cycle_error(self):
        """
        Test CycleError raised for circular dependencies.
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
    """

    def test_build_tree_single_task(self):
        """
        Test tree for task with no dependencies.
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
    """

    def test_leaves_the_command_for_the_renderer(self):
        """
        cmd is rendered by the executor with the self namespace in scope,
        against paths that are already rendered. Substituting it here would
        inject an unrendered path into text about to be rendered, so a
        value containing a template would be executed as one.
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

        resolve_self_references(recipe, [("copy", None)])

        self.assertEqual(
            task.cmd, "cp {{ self.inputs.src }} {{ self.outputs.dest }}"
        )

    def test_leaves_the_working_dir_for_the_renderer(self):
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

        resolve_self_references(recipe, [("build", None)])

        self.assertEqual(task.working_dir, "{{ self.inputs.project }}/build")

    def test_does_not_validate_a_command_it_no_longer_resolves(self):
        """
        A bad self-reference in cmd is reported when the task renders, not
        when the order is resolved, so this pass must not raise on it.
        """
        task = Task(
            name="build",
            cmd="cp {{ self.inputs.missing }}",
            inputs=[{"src": "file.txt"}],
        )
        tasks = {"build": task}
        recipe = Recipe(
            tasks=tasks, project_root=Path.cwd(), recipe_path=Path("tasktree.yaml")
        )

        resolve_self_references(recipe, [("build", None)])

        self.assertEqual(task.cmd, "cp {{ self.inputs.missing }}")

    def test_resolve_self_references_in_arg_defaults(self):
        """
        Test that self-references in argument defaults are resolved.
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

    def test_resolves_every_task_in_the_order(self):
        """
        Argument defaults are what this pass still resolves, so they are
        what shows that it visits each task rather than only the first.
        """
        task1 = Task(
            name="task1",
            cmd="process",
            inputs=[{"in1": "file1.txt"}],
            args=[{"target": {"default": "{{ self.inputs.in1 }}"}}],
        )
        task2 = Task(
            name="task2",
            cmd="process",
            inputs=[{"in2": "file2.txt"}],
            args=[{"target": {"default": "{{ self.inputs.in2 }}"}}],
        )
        tasks = {"task1": task1, "task2": task2}
        recipe = Recipe(
            tasks=tasks, project_root=Path.cwd(), recipe_path=Path("tasktree.yaml")
        )

        resolve_self_references(recipe, [("task1", None), ("task2", None)])

        self.assertEqual(task1.args[0]["target"]["default"], "file1.txt")
        self.assertEqual(task2.args[0]["target"]["default"], "file2.txt")

    def test_an_error_in_an_argument_default_still_propagates(self):
        """
        Argument defaults are converted to their declared types before any
        render, so this pass still owns them -- and still owns reporting a
        bad reference in one.
        """
        task = Task(
            name="build",
            cmd="build",
            inputs=[{"src": "file.txt"}],
            args=[{"target": {"default": "{{ self.inputs.missing }}"}}],
        )
        tasks = {"build": task}
        recipe = Recipe(
            tasks=tasks, project_root=Path.cwd(), recipe_path=Path("tasktree.yaml")
        )

        with self.assertRaises(ValueError) as cm:
            resolve_self_references(recipe, [("build", None)])

        error_msg = str(cm.exception)
        self.assertIn("missing", error_msg)
        self.assertIn("src", error_msg)  # Available input should be mentioned


if __name__ == "__main__":
    unittest.main()


class TestDependencyOutputsAreRendered(unittest.TestCase):
    """
    A dependency's output path is data by the time it lands in another
    task's text, and that text is itself about to be rendered -- so the
    path has to go in rendered, or it is rendered a second time (schema
    pipeline slice 10d).
    """

    def _recipe(self, producer_outputs, consumer_cmd, producer_args=None):
        tasks = {
            "build": Task(
                name="build",
                cmd="build",
                args=producer_args or [],
                outputs=producer_outputs,
            ),
            "package": Task(name="package", cmd=consumer_cmd, deps=["build"]),
        }
        return Recipe(
            tasks=tasks, project_root=Path.cwd(), recipe_path=Path("tasktree.yaml")
        ), tasks

    def test_the_injected_path_goes_in_rendered(self):
        recipe, tasks = self._recipe(
            [{"bundle": "out/{{ var.dir }}/app"}],
            "ship {{ dep.build.outputs.bundle }}",
        )
        seen = []

        def render(pattern, task, args):
            seen.append((pattern, task.name))
            return "out/rendered/app"

        resolve_dependency_output_references(
            recipe, [("build", None), ("package", None)], render_pattern=render
        )

        self.assertEqual(tasks["package"].cmd, "ship out/rendered/app")
        self.assertEqual(seen, [("out/{{ var.dir }}/app", "build")])

    def test_it_renders_against_the_dependencys_own_arguments(self):
        """
        The producer's output names the arguments *it* was invoked with, not
        the consumer's.
        """
        recipe, tasks = self._recipe(
            [{"bundle": "out/{{ arg.config }}/app"}],
            "ship {{ dep.build.outputs.bundle }}",
            producer_args=[{"config": {"default": "debug"}}],
        )
        seen = []

        def render(pattern, task, args):
            seen.append(dict(args or {}))
            return "out/release/app"

        resolve_dependency_output_references(
            recipe,
            [("build", {"config": "release"}), ("package", None)],
            render_pattern=render,
        )

        self.assertEqual(seen, [{"config": "release"}])

    def test_an_unrenderable_path_is_used_as_it_stands(self):
        """
        One bad path must not fail the whole execution order; the field
        that uses it reports it instead.
        """
        recipe, tasks = self._recipe(
            [{"bundle": "out/{{ arg.gone }}/app"}],
            "ship {{ dep.build.outputs.bundle }}",
        )

        def render(pattern, task, args):
            raise ValueError("undefined")

        resolve_dependency_output_references(
            recipe, [("build", None), ("package", None)], render_pattern=render
        )

        self.assertEqual(tasks["package"].cmd, "ship out/{{ arg.gone }}/app")
