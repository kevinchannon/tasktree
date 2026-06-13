"""
Unit tests for the Jinja2-based rendering module.
"""

import unittest

from tasktree.rendering import render


class TestRenderNamespaces(unittest.TestCase):
    """Rendering of the variable namespaces against a context object."""

    def test_renders_var_namespace(self):
        result = render("Hello {{ var.name }}", {"var": {"name": "world"}})
        self.assertEqual(result, "Hello world")

    def test_renders_arg_namespace(self):
        result = render("mode={{ arg.mode }}", {"arg": {"mode": "debug"}})
        self.assertEqual(result, "mode=debug")

    def test_renders_env_namespace(self):
        result = render("user={{ env.USER }}", {"env": {"USER": "alice"}})
        self.assertEqual(result, "user=alice")

    def test_renders_tt_namespace(self):
        result = render(
            "root={{ tt.project_root }}", {"tt": {"project_root": "/proj"}}
        )
        self.assertEqual(result, "root=/proj")

    def test_renders_simple_dep_output(self):
        context = {"dep": {"build": {"outputs": {"bundle": "dist/app.js"}}}}
        result = render("deploy {{ dep.build.outputs.bundle }}", context)
        self.assertEqual(result, "deploy dist/app.js")

    def test_renders_multiple_namespaces_in_one_template(self):
        context = {"var": {"target": "prod"}, "arg": {"v": "1.2.3"}}
        result = render("{{ var.target }}-{{ arg.v }}", context)
        self.assertEqual(result, "prod-1.2.3")

    def test_text_without_placeholders_is_unchanged(self):
        self.assertEqual(render("echo hello", {}), "echo hello")


class TestRenderValueCoercion(unittest.TestCase):
    """Rendered values follow Tasktree's string conventions."""

    def test_booleans_render_lowercase(self):
        self.assertEqual(render("{{ arg.flag }}", {"arg": {"flag": True}}), "true")
        self.assertEqual(render("{{ arg.flag }}", {"arg": {"flag": False}}), "false")

    def test_integers_render_as_strings(self):
        self.assertEqual(render("{{ arg.n }}", {"arg": {"n": 42}}), "42")

    def test_numeric_index_into_list(self):
        context = {"this": {"inputs": ["a.txt", "b.txt"]}}
        self.assertEqual(render("{{ this.inputs.0 }}", context), "a.txt")

    def test_non_string_input_returned_unchanged(self):
        self.assertEqual(render(5, {}), 5)
        self.assertIsNone(render(None, {}))


class TestSelfReservedWordTranslation(unittest.TestCase):
    """`self` is reserved in Jinja2 and is transparently aliased."""

    def test_self_namespace_renders_despite_reserved_word(self):
        context = {"self": {"inputs": {"src": "main.c"}}}
        self.assertEqual(render("{{ self.inputs.src }}", context), "main.c")

    def test_self_positional_renders(self):
        context = {"self": {"inputs": ["a", "b"]}}
        self.assertEqual(render("{{ self.inputs.1 }}", context), "b")

    def test_literal_word_self_outside_template_is_untouched(self):
        # "self." appearing in plain command text must not be rewritten
        self.assertEqual(render("echo self.test", {}), "echo self.test")


class TestNamespacedDepTranslation(unittest.TestCase):
    """Dotted (namespaced) dependency names render via subscript rewrite."""

    def test_simple_dep_name_still_renders(self):
        context = {"dep": {"build": {"outputs": {"x": "1"}}}}
        self.assertEqual(render("{{ dep.build.outputs.x }}", context), "1")

    def test_namespaced_dep_name_renders(self):
        context = {"dep": {"build.compile": {"outputs": {"bundle": "app.js"}}}}
        self.assertEqual(
            render("{{ dep.build.compile.outputs.bundle }}", context), "app.js"
        )

    def test_deeply_namespaced_dep_name_renders(self):
        context = {"dep": {"a.b.c": {"outputs": {"out": "/p"}}}}
        self.assertEqual(render("{{ dep.a.b.c.outputs.out }}", context), "/p")

    def test_literal_dep_text_outside_template_untouched(self):
        self.assertEqual(
            render("echo dep.build.outputs.x", {}), "echo dep.build.outputs.x"
        )


class TestRenderErrorTranslation(unittest.TestCase):
    """Jinja2 errors are translated into actionable Tasktree messages."""

    def test_undefined_variable_raises_value_error(self):
        with self.assertRaises(ValueError) as ctx:
            render("{{ var.missing }}", {"var": {}})
        self.assertIn("Undefined variable", str(ctx.exception))

    def test_undefined_variable_includes_task_name(self):
        with self.assertRaises(ValueError) as ctx:
            render("{{ var.missing }}", {"var": {}}, task_name="build")
        self.assertIn("build", str(ctx.exception))

    def test_malformed_template_raises_value_error(self):
        with self.assertRaises(ValueError) as ctx:
            render("{{ var.x", {"var": {"x": "y"}})
        self.assertIn("Malformed template", str(ctx.exception))

    def test_error_does_not_leak_jinja_internals(self):
        with self.assertRaises(ValueError) as ctx:
            render("{{ var.missing }}", {"var": {}})
        self.assertNotIn("jinja2", str(ctx.exception).lower())
        self.assertNotIn("Traceback", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
