"""
Unit tests for the per-task config object builder.
"""

import unittest

from tasktree.rendering import render
from tasktree.task_config import build_task_config


class TestBuildTaskConfigNamespaces(unittest.TestCase):
    """The config object exposes each namespace under its key."""

    def test_var_namespace(self):
        config = build_task_config(variables={"target": "prod"})
        self.assertEqual(config["var"]["target"], "prod")

    def test_arg_namespace(self):
        config = build_task_config(args={"mode": "debug"})
        self.assertEqual(config["arg"]["mode"], "debug")

    def test_tt_namespace(self):
        config = build_task_config(builtins={"project_root": "/proj"})
        self.assertEqual(config["tt"]["project_root"], "/proj")

    def test_env_namespace_from_explicit_mapping(self):
        config = build_task_config(env={"USER": "alice"})
        self.assertEqual(config["env"]["USER"], "alice")

    def test_env_defaults_to_os_environ_snapshot(self):
        config = build_task_config()
        # PATH is reliably present in the test environment
        self.assertIn("PATH", config["env"])

    def test_all_namespaces_present_even_when_empty(self):
        config = build_task_config()
        for key in ("var", "arg", "env", "tt"):
            self.assertIn(key, config)


class TestBuildTaskConfigRendersEndToEnd(unittest.TestCase):
    """The assembled config renders correctly via the renderer."""

    def test_renders_across_namespaces(self):
        config = build_task_config(
            variables={"name": "app"},
            args={"v": "1.0"},
            builtins={"task_name": "build"},
            env={"USER": "alice"},
        )
        result = render(
            "{{ tt.task_name }}:{{ var.name }}:{{ arg.v }}:{{ env.USER }}", config
        )
        self.assertEqual(result, "build:app:1.0:alice")


class TestDepNamespace(unittest.TestCase):
    """The dep namespace exposes dependency outputs and errors helpfully."""

    def test_dep_namespace_present_when_empty(self):
        config = build_task_config()
        self.assertIn("dep", config)

    def test_renders_dependency_output(self):
        config = build_task_config(
            dep_outputs={"build": {"bundle": "dist/app.js"}}
        )
        result = render("deploy {{ dep.build.outputs.bundle }}", config)
        self.assertEqual(result, "deploy dist/app.js")

    def test_unknown_dependency_raises_actionable_error(self):
        config = build_task_config(dep_outputs={"build": {"bundle": "x"}})
        with self.assertRaises(ValueError) as ctx:
            render("{{ dep.missing.outputs.bundle }}", config)
        message = str(ctx.exception)
        self.assertIn("missing", message)
        self.assertIn("not a dependency", message)

    def test_unknown_output_raises_actionable_error(self):
        config = build_task_config(dep_outputs={"build": {"bundle": "x"}})
        with self.assertRaises(ValueError) as ctx:
            render("{{ dep.build.outputs.nope }}", config)
        message = str(ctx.exception)
        self.assertIn("nope", message)
        self.assertIn("bundle", message)  # lists available outputs

    def test_multiple_dependencies(self):
        config = build_task_config(
            dep_outputs={
                "build": {"bundle": "dist/app.js"},
                "assets": {"css": "dist/app.css"},
            }
        )
        result = render(
            "{{ dep.build.outputs.bundle }} {{ dep.assets.outputs.css }}", config
        )
        self.assertEqual(result, "dist/app.js dist/app.css")


class TestSelfNamespace(unittest.TestCase):
    """The self namespace exposes the task's own inputs/outputs."""

    def test_self_namespace_present_when_empty(self):
        config = build_task_config()
        self.assertIn("self", config)
        self.assertIn("inputs", config["self"])
        self.assertIn("outputs", config["self"])

    def test_named_input_renders(self):
        config = build_task_config(inputs_named={"src": "main.c"})
        self.assertEqual(render("{{ self.inputs.src }}", config), "main.c")

    def test_named_output_renders(self):
        config = build_task_config(outputs_named={"bin": "out/app"})
        self.assertEqual(render("{{ self.outputs.bin }}", config), "out/app")

    def test_positional_input_renders(self):
        config = build_task_config(inputs_indexed=["a.txt", "b.txt"])
        self.assertEqual(render("{{ self.inputs.0 }}", config), "a.txt")
        self.assertEqual(render("{{ self.inputs.1 }}", config), "b.txt")

    def test_named_and_positional_in_one_template(self):
        config = build_task_config(
            task_name="copy",
            inputs_named={"src": "*.txt"},
            inputs_indexed=["*.txt"],
            outputs_indexed=["out/result.txt"],
        )
        result = render(
            "cp {{ self.inputs.src }} {{ self.outputs.0 }}", config
        )
        self.assertEqual(result, "cp *.txt out/result.txt")

    def test_missing_named_input_raises_actionable_error(self):
        config = build_task_config(
            task_name="build", inputs_named={"src": "main.c"}
        )
        with self.assertRaises(ValueError) as ctx:
            render("{{ self.inputs.nope }}", config)
        message = str(ctx.exception)
        self.assertIn("build", message)
        self.assertIn("nope", message)
        self.assertIn("src", message)  # lists available

    def test_positional_index_out_of_bounds_raises_error(self):
        config = build_task_config(task_name="build", inputs_indexed=["a.txt"])
        with self.assertRaises(ValueError) as ctx:
            render("{{ self.inputs.5 }}", config)
        self.assertIn("indices 0-0", str(ctx.exception))

    def test_positional_index_with_no_inputs_raises_error(self):
        config = build_task_config(task_name="build")
        with self.assertRaises(ValueError) as ctx:
            render("{{ self.inputs.0 }}", config)
        self.assertIn("no inputs defined", str(ctx.exception))


class TestExportedArgs(unittest.TestCase):
    """Exported arguments are not available for template substitution."""

    def test_regular_arg_still_renders(self):
        config = build_task_config(args={"mode": "debug"}, exported_args={"token"})
        self.assertEqual(render("{{ arg.mode }}", config), "debug")

    def test_referencing_exported_arg_raises_actionable_error(self):
        config = build_task_config(args={}, exported_args={"token"})
        with self.assertRaises(ValueError) as ctx:
            render("{{ arg.token }}", config)
        message = str(ctx.exception)
        self.assertIn("token", message)
        self.assertIn("exported", message)

    def test_missing_arg_is_undefined_not_exported_error(self):
        config = build_task_config(args={}, exported_args={"token"})
        with self.assertRaises(ValueError) as ctx:
            render("{{ arg.nope }}", config)
        self.assertIn("Undefined variable", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
