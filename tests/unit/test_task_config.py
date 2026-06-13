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
