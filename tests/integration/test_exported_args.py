"""Integration tests for exported task arguments."""

import os
import platform
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from helpers.logging import logger_stub
from tasktree.executor import Executor
from tasktree.parser import parse_recipe, parse_task_args
from tasktree.process_runner import TaskOutputTypes, make_process_runner
from tasktree.state import StateManager
from tests.fixture_utils import copy_fixture_files


class TestExportedArgs(unittest.TestCase):
    """
    Test exported arguments feature end-to-end.
    """

    def test_exported_args_in_environment(self):
        """
        Test that exported args are set as environment variables.
        """
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            copy_fixture_files("exported_args_basic", Path(tmpdir))

            recipe = parse_recipe(recipe_path)
            state = StateManager(recipe.project_root)
            state.load()
            executor = Executor(recipe, state, logger_stub, make_process_runner)

            # Execute with exported args
            args_dict = {"server": "prod-server", "user": "admin"}
            statuses = executor.execute_task("test", TaskOutputTypes.ALL, args_dict)

            # Should execute successfully (no exception = success)
            self.assertIn("test", statuses)

    def test_exported_args_with_defaults(self):
        """
        Test that exported args with defaults work correctly.
        """
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            copy_fixture_files("exported_args_with_defaults", Path(tmpdir))

            recipe = parse_recipe(recipe_path)
            state = StateManager(recipe.project_root)
            state.load()
            executor = Executor(recipe, state, logger_stub, make_process_runner)

            # Execute with only server arg (port uses default)
            args_dict = {"server": "prod-server", "port": "8080"}
            statuses = executor.execute_task("test", TaskOutputTypes.ALL, args_dict)

            self.assertIn("test", statuses)

    def test_exported_args_default_not_provided(self):
        """
        Test that exported args with defaults work when default is not explicitly provided.

        This is a regression test for the bug where exported args with defaults
        would not be set as environment variables if the value wasn't provided
        by the user (relying on CLI to apply the default).
        """
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            copy_fixture_files("exported_args_with_defaults", Path(tmpdir))

            # Use CLI to parse and execute (simulating real usage)

            recipe = parse_recipe(recipe_path)
            task = recipe.get_task("test")

            # Parse args with CLI (which applies defaults)
            # Only provide server, not port (port should use default)
            args_dict = parse_task_args(logger_stub, task.args, ["prod-server"])

            # Verify CLI applied the default
            # Exported args are always strings (environment variables)
            self.assertEqual(args_dict["server"], "prod-server")
            self.assertEqual(args_dict["port"], "8080")

            # Execute with args_dict from CLI
            state = StateManager(recipe.project_root)
            state.load()
            executor = Executor(recipe, state, logger_stub, make_process_runner)
            statuses = executor.execute_task("test", TaskOutputTypes.ALL, args_dict)

            self.assertIn("test", statuses)

    def test_exported_args_not_substitutable(self):
        """
        Test that exported args cannot be used in template substitution.
        """
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            copy_fixture_files("exported_args_not_substitutable", Path(tmpdir))

            recipe = parse_recipe(recipe_path)
            state = StateManager(recipe.project_root)
            state.load()
            executor = Executor(recipe, state, logger_stub, make_process_runner)

            # Should raise error when trying to use exported arg in template
            args_dict = {"server": "prod-server"}
            with self.assertRaises(ValueError) as cm:
                executor.execute_task("test", TaskOutputTypes.ALL, args_dict)

            self.assertIn("server", str(cm.exception))
            self.assertIn("exported", str(cm.exception))
            self.assertIn("$server", str(cm.exception))

    def test_mixed_exported_and_regular_args(self):
        """
        Test mixing exported and regular arguments.
        """
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            copy_fixture_files("exported_args_mixed", Path(tmpdir))

            recipe = parse_recipe(recipe_path)
            state = StateManager(recipe.project_root)
            state.load()
            executor = Executor(recipe, state, logger_stub, make_process_runner)

            args_dict = {"server": "prod-server", "port": 9000}
            statuses = executor.execute_task("deploy", TaskOutputTypes.ALL, args_dict)

            self.assertIn("deploy", statuses)

    def test_case_preserved_in_env_vars(self):
        """
        Test that environment variable names preserve case exactly.
        """
        is_windows = platform.system() == "Windows"
        if is_windows:
            # Windows env vars are case-insensitive
            self.skipTest("Windows environment variables are case-insensitive")

        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            copy_fixture_files("exported_args_case_preserved", Path(tmpdir))

            recipe = parse_recipe(recipe_path)
            state = StateManager(recipe.project_root)
            state.load()
            executor = Executor(recipe, state, logger_stub, make_process_runner)

            args_dict = {"Server": "UPPERCASE", "server": "lowercase"}
            statuses = executor.execute_task("test", TaskOutputTypes.ALL, args_dict)

            self.assertIn("test", statuses)

    def test_values_with_spaces(self):
        """
        Test that exported args with spaces are preserved correctly.
        """
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            copy_fixture_files("exported_args_with_spaces", Path(tmpdir))

            recipe = parse_recipe(recipe_path)
            state = StateManager(recipe.project_root)
            state.load()
            executor = Executor(recipe, state, logger_stub, make_process_runner)

            args_dict = {"message": "hello world with spaces"}
            statuses = executor.execute_task("test", TaskOutputTypes.ALL, args_dict)

            self.assertIn("test", statuses)

    def test_exported_arg_with_type_annotation_fails_cli_parsing(self):
        """
        Test that exported arguments with type annotations fail during arg parsing.
        """

        from tasktree.parser import parse_arg_spec

        # Test that parse_arg_spec raises error for exported args with types (old colon syntax)
        with self.assertRaises(ValueError) as cm:
            parse_arg_spec("$server:str")

        self.assertIn("Invalid argument syntax", str(cm.exception))

    def test_exported_arg_yaml_dict_with_type_fails(self):
        """
        Test that exported arguments with type field in YAML dict format fails.
        """

        from tasktree.parser import parse_arg_spec

        # Test that parse_arg_spec raises error for exported args with type in dict format
        with self.assertRaises(ValueError) as cm:
            parse_arg_spec({"$server": {"type": "str"}})

        self.assertIn("Type annotations not allowed", str(cm.exception))
        self.assertIn("$server", str(cm.exception))

    def test_multiline_command_with_exported_args(self):
        """
        Test exported args work with multi-line commands.
        """
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            copy_fixture_files("exported_args_multiline", Path(tmpdir))

            recipe = parse_recipe(recipe_path)
            state = StateManager(recipe.project_root)
            state.load()
            executor = Executor(recipe, state, logger_stub, make_process_runner)

            args_dict = {"app": "myapp", "server": "prod-server"}
            statuses = executor.execute_task("deploy", TaskOutputTypes.ALL, args_dict)

            self.assertIn("deploy", statuses)

    def test_exported_args_override_existing_env_vars(self):
        """
        Test that exported args override existing environment variables.
        """
        # Set an environment variable
        original_value = os.environ.get("MY_VAR")
        os.environ["MY_VAR"] = "original"

        try:
            with TemporaryDirectory() as tmpdir:
                recipe_path = Path(tmpdir) / "tasktree.yaml"
                copy_fixture_files("exported_args_override_env", Path(tmpdir))

                recipe = parse_recipe(recipe_path)
                state = StateManager(recipe.project_root)
                state.load()
                executor = Executor(recipe, state, logger_stub, make_process_runner)

                # Exported arg should override the env var
                args_dict = {"MY_VAR": "overridden"}
                statuses = executor.execute_task("test", TaskOutputTypes.ALL, args_dict)

                self.assertIn("test", statuses)
        finally:
            # Restore original value
            if original_value is None:
                os.environ.pop("MY_VAR", None)
            else:
                os.environ["MY_VAR"] = original_value

    def test_protected_env_var_override_fails(self):
        """
        Test that attempting to override protected environment variables fails.
        """
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            copy_fixture_files("exported_args_protected_var", Path(tmpdir))

            recipe = parse_recipe(recipe_path)
            state = StateManager(recipe.project_root)
            state.load()
            executor = Executor(recipe, state, logger_stub, make_process_runner)

            # Should raise ValueError when trying to override PATH
            args_dict = {"PATH": "/malicious/path"}
            with self.assertRaises(ValueError) as cm:
                executor.execute_task("test", TaskOutputTypes.ALL, args_dict)

            self.assertIn("protected", str(cm.exception).lower())
            self.assertIn("PATH", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
