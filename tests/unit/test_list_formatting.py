"""Unit tests for --list output formatting."""

import unittest
from unittest.mock import MagicMock, patch

from rich.console import Console
from rich.table import Table

from tasktree.cli import _format_task_arguments, _list_tasks
from tasktree.parser import Recipe, Task


class TestFormatTaskArguments(unittest.TestCase):
    """
    Tests for _format_task_arguments() function.
    @athena: d2e35c632a2c
    """

    def test_format_no_arguments(self):
        """
        Test formatting task with no arguments.
        @athena: 976c9633815c
        """
        result = _format_task_arguments([])
        self.assertEqual(result, "")

    def test_format_single_required_argument(self):
        """
        Test formatting task with single required argument.
        @athena: 82a42067a1f3
        """
        result = _format_task_arguments(["environment"])
        self.assertEqual(result, "environment[dim]:str[/dim]")

    def test_format_single_optional_argument(self):
        """
        Test formatting task with single optional argument.
        @athena: 2934230714e6
        """
        result = _format_task_arguments([{"environment": {"default": "production"}}])
        self.assertIn("environment[dim]:str[/dim]", result)
        self.assertIn("[dim]\\[=production][/dim]", result)

    def test_format_multiple_required_arguments(self):
        """
        Test formatting task with multiple required arguments.
        @athena: ce582aa5884f
        """
        result = _format_task_arguments(["mode", "target"])
        self.assertIn("mode[dim]:str[/dim]", result)
        self.assertIn("target[dim]:str[/dim]", result)
        # Verify order is preserved
        self.assertTrue(result.index("mode") < result.index("target"))

    def test_format_multiple_optional_arguments(self):
        """
        Test formatting task with multiple optional arguments.
        @athena: 33f24ae9ed6d
        """
        result = _format_task_arguments(
            [{"mode": {"default": "debug"}}, {"target": {"default": "x86_64"}}]
        )
        self.assertIn("mode[dim]:str[/dim]", result)
        self.assertIn("[dim]\\[=debug][/dim]", result)
        self.assertIn("target[dim]:str[/dim]", result)
        self.assertIn("[dim]\\[=x86_64][/dim]", result)

    def test_format_mixed_required_and_optional_arguments(self):
        """
        Test formatting task with mixed required and optional arguments.
        @athena: 81f9df8121ff
        """
        result = _format_task_arguments(
            ["environment", {"region": {"default": "us-west-1"}}]
        )
        self.assertIn("environment[dim]:str[/dim]", result)
        self.assertIn("region[dim]:str[/dim]", result)
        self.assertIn("[dim]\\[=us-west-1][/dim]", result)
        # Verify order is preserved
        self.assertTrue(result.index("environment") < result.index("region"))

    def test_format_arguments_in_definition_order(self):
        """
        Test formatting preserves argument definition order.
        @athena: c90900d9653b
        """
        result = _format_task_arguments(["first", "second", "third"])
        # Verify order by checking indices
        self.assertTrue(result.index("first") < result.index("second"))
        self.assertTrue(result.index("second") < result.index("third"))
        self.assertIn("first[dim]:str[/dim]", result)
        self.assertIn("second[dim]:str[/dim]", result)
        self.assertIn("third[dim]:str[/dim]", result)

    def test_format_default_values_with_equals_sign(self):
        """
        Test formatting shows default values with equals sign.
        @athena: d971a8bd392b
        """
        result = _format_task_arguments([{"port": {"default": "8080"}}])
        self.assertIn("[dim]\\[=8080][/dim]", result)

    def test_format_shows_str_type_explicitly(self):
        """
        Test formatting shows str type explicitly.
        @athena: c48f7a58a715
        """
        result = _format_task_arguments(["name"])
        self.assertIn("name[dim]:str[/dim]", result)

    def test_format_shows_int_type(self):
        """
        Test formatting shows int type.
        @athena: b33bcaa4b5d1
        """
        result = _format_task_arguments([{"port": {"type": "int"}}])
        self.assertIn("port[dim]:int[/dim]", result)

    def test_format_shows_float_type(self):
        """
        Test formatting shows float type.
        @athena: fafaf1018a94
        """
        result = _format_task_arguments([{"timeout": {"type": "float"}}])
        self.assertIn("timeout[dim]:float[/dim]", result)

    def test_format_shows_bool_type(self):
        """
        Test formatting shows bool type.
        @athena: 95e5489bf476
        """
        result = _format_task_arguments([{"verbose": {"type": "bool"}}])
        self.assertIn("verbose[dim]:bool[/dim]", result)

    def test_format_shows_path_type(self):
        """
        Test formatting shows path type.
        @athena: 8b476f5f92de
        """
        result = _format_task_arguments([{"output": {"type": "path"}}])
        self.assertIn("output[dim]:path[/dim]", result)

    def test_format_shows_datetime_type(self):
        """
        Test formatting shows datetime type.
        @athena: f13b8606f744
        """
        # Using dict format for datetime
        result = _format_task_arguments([{"timestamp": {"type": "datetime"}}])
        self.assertIn("timestamp[dim]:datetime[/dim]", result)

    def test_format_shows_ip_types(self):
        """
        Test formatting shows ip, ipv4, ipv6 types.
        @athena: 78d4a1a4d56b
        """
        result_ip = _format_task_arguments([{"addr": {"type": "ip"}}])
        self.assertIn("addr[dim]:ip[/dim]", result_ip)

        result_ipv4 = _format_task_arguments([{"addr": {"type": "ipv4"}}])
        self.assertIn("addr[dim]:ipv4[/dim]", result_ipv4)

        result_ipv6 = _format_task_arguments([{"addr": {"type": "ipv6"}}])
        self.assertIn("addr[dim]:ipv6[/dim]", result_ipv6)

    def test_format_shows_email_type(self):
        """
        Test formatting shows email type.
        @athena: 5e60f6e0d9d0
        """
        result = _format_task_arguments([{"contact": {"type": "email"}}])
        self.assertIn("contact[dim]:email[/dim]", result)

    def test_format_shows_hostname_type(self):
        """
        Test formatting shows hostname type.
        @athena: a0d913a92337
        """
        result = _format_task_arguments([{"server": {"type": "hostname"}}])
        self.assertIn("server[dim]:hostname[/dim]", result)

    def test_format_shows_all_argument_types_explicitly(self):
        """
        Test formatting shows all argument types explicitly.
        @athena: 26b0fcbbca48
        """
        # Even default str type should be shown
        result = _format_task_arguments(["name"])
        self.assertIn("[dim]:str[/dim]", result)

    def test_format_handles_task_with_many_arguments(self):
        """
        Test formatting handles task with many arguments.
        @athena: 959bb999ff96
        """
        many_args = [f"arg{i}" for i in range(10)]
        result = _format_task_arguments(many_args)
        # All arguments should be present
        for i in range(10):
            self.assertIn(f"arg{i}[dim]:str[/dim]", result)

    def test_format_dict_argument_with_default(self):
        """
        Test formatting dict-style argument with default.
        @athena: a0d1e7340cdd
        """
        result = _format_task_arguments([{"port": {"type": "int", "default": 8080}}])
        self.assertIn("port[dim]:int[/dim]", result)
        self.assertIn("[dim]\\[=8080][/dim]", result)

    def test_format_dict_argument_without_default(self):
        """
        Test formatting dict-style argument without default.
        @athena: 3bfa4239df9c
        """
        result = _format_task_arguments([{"port": {"type": "int"}}])
        self.assertIn("port[dim]:int[/dim]", result)
        self.assertNotIn("=", result)

    def test_format_escapes_rich_markup_in_defaults(self):
        """
        Test formatting properly escapes Rich markup in default values.
        @athena: 2ff131a26a9b
        """
        # Test with brackets in default value
        result = _format_task_arguments([{"pattern": {"default": "[a-z]+"}}])
        # The brackets in the default should be escaped
        self.assertIn("[dim]\\[=[a-z]+][/dim]", result)

        # Test with dict-style argument containing special characters
        result2 = _format_task_arguments(
            [{"regex": {"type": "str", "default": "[0-9]+"}}]
        )
        self.assertIn("regex[dim]:str[/dim]", result2)
        self.assertIn("[dim]\\[=[0-9]+][/dim]", result2)


class TestListFormatting(unittest.TestCase):
    """
    Tests for _list_tasks() output formatting.
    @athena: 7db6f9cebc23
    """

    def setUp(self):
        """
        Set up test fixtures.
        @athena: d852c203b9f3
        """
        self.console_patch = patch("tasktree.cli.console")
        self.mock_console = self.console_patch.start()

    def tearDown(self):
        """
        Clean up patches.
        @athena: e7ba60bdc9bc
        """
        self.console_patch.stop()

    def _create_mock_recipe(self, tasks_dict):
        """
        Create a mock Recipe with given tasks.

        Args:
        tasks_dict: Dict of task_name -> Task object
        @athena: 6f27ea19f157
        """
        recipe = MagicMock(spec=Recipe)
        recipe.task_names.return_value = list(tasks_dict.keys())
        recipe.get_task.side_effect = lambda name: tasks_dict.get(name)
        return recipe

    @patch("tasktree.cli._get_recipe")
    def test_list_uses_borderless_table_format(self, mock_get_recipe):
        """
        Test list uses borderless table format.
        @athena: f60d9db65551
        """
        tasks = {"build": Task(name="build", cmd="echo build", desc="Build task")}
        mock_get_recipe.return_value = self._create_mock_recipe(tasks)

        _list_tasks()

        # Verify console.print was called
        self.mock_console.print.assert_called_once()
        # Get the table that was printed
        table = self.mock_console.print.call_args[0][0]
        self.assertIsInstance(table, Table)
        # Check borderless configuration
        self.assertFalse(table.show_edge)
        self.assertFalse(table.show_header)
        self.assertIsNone(table.box)

    @patch("tasktree.cli._get_recipe")
    def test_list_applies_correct_column_padding(self, mock_get_recipe):
        """
        Test list applies correct column padding.
        @athena: 4400c3e87f5f
        """
        tasks = {"build": Task(name="build", cmd="echo build", desc="Build task")}
        mock_get_recipe.return_value = self._create_mock_recipe(tasks)

        _list_tasks()

        table = self.mock_console.print.call_args[0][0]
        # Rich Table padding can be a tuple of (top, right, bottom, left) or (vertical, horizontal)
        # Check that horizontal padding is 2
        self.assertIn(table.padding, [(0, 2), (0, 2, 0, 2)])

    @patch("tasktree.cli._get_recipe")
    def test_list_calculates_command_column_width_from_longest_task_name(
        self, mock_get_recipe
    ):
        """
        Test list calculates command column width from longest task name.
        @athena: a8d8f216cd14
        """
        tasks = {
            "short": Task(name="short", cmd="echo", desc="Short"),
            "very-long-task-name": Task(
                name="very-long-task-name", cmd="echo", desc="Long"
            ),
            "mid": Task(name="mid", cmd="echo", desc="Mid"),
        }
        mock_get_recipe.return_value = self._create_mock_recipe(tasks)

        _list_tasks()

        table = self.mock_console.print.call_args[0][0]
        # Command column should have width equal to longest name
        self.assertEqual(table.columns[0].width, len("very-long-task-name"))

    @patch("tasktree.cli._get_recipe")
    def test_list_command_column_never_wraps(self, mock_get_recipe):
        """
        Test list command column never wraps.
        @athena: 5d87d3b1edd4
        """
        tasks = {"task": Task(name="task", cmd="echo", desc="Task")}
        mock_get_recipe.return_value = self._create_mock_recipe(tasks)

        _list_tasks()

        table = self.mock_console.print.call_args[0][0]
        # Command column should have no_wrap=True
        self.assertTrue(table.columns[0].no_wrap)

    @patch("tasktree.cli._get_recipe")
    def test_list_shows_namespaced_tasks(self, mock_get_recipe):
        """
        Test list shows namespaced tasks.
        @athena: 843f958d660f
        """
        tasks = {
            "build": Task(name="build", cmd="echo", desc="Build"),
            "docker.build": Task(name="docker.build", cmd="echo", desc="Docker build"),
        }
        mock_get_recipe.return_value = self._create_mock_recipe(tasks)

        _list_tasks()

        # Verify both tasks are shown
        table = self.mock_console.print.call_args[0][0]
        # Table should have 2 rows (one for each task)
        self.assertEqual(len(table.rows), 2)

    @patch("tasktree.cli._get_recipe")
    def test_list_formats_tasks_from_multiple_namespaces(self, mock_get_recipe):
        """
        Test list formats tasks from multiple namespaces.
        @athena: 761fecea895d
        """
        tasks = {
            "build": Task(name="build", cmd="echo", desc="Build"),
            "docker.build": Task(name="docker.build", cmd="echo", desc="Docker build"),
            "docker.test": Task(name="docker.test", cmd="echo", desc="Docker test"),
            "common.setup": Task(name="common.setup", cmd="echo", desc="Common setup"),
        }
        mock_get_recipe.return_value = self._create_mock_recipe(tasks)

        _list_tasks()

        table = self.mock_console.print.call_args[0][0]
        self.assertEqual(len(table.rows), 4)

    @patch("tasktree.cli._get_recipe")
    def test_list_handles_empty_task_list(self, mock_get_recipe):
        """
        Test list handles empty task list.
        @athena: 8eba30f066c9
        """
        tasks = {}
        mock_get_recipe.return_value = self._create_mock_recipe(tasks)

        _list_tasks()

        # Should still print a table (just empty)
        self.mock_console.print.assert_called_once()
        table = self.mock_console.print.call_args[0][0]
        self.assertEqual(len(table.rows), 0)

    @patch("tasktree.cli._get_recipe")
    def test_list_handles_tasks_with_long_descriptions(self, mock_get_recipe):
        """
        Test list handles tasks with long descriptions.
        @athena: 28fab971dc2f
        """
        long_desc = (
            "This is a very long description that should wrap in the description column "
            * 5
        )
        tasks = {"task": Task(name="task", cmd="echo", desc=long_desc)}
        mock_get_recipe.return_value = self._create_mock_recipe(tasks)

        _list_tasks()

        # Should not raise any errors
        self.mock_console.print.assert_called_once()

    @patch("tasktree.cli._get_recipe")
    def test_list_applies_bold_style_to_task_names(self, mock_get_recipe):
        """
        Test list applies bold style to task names.
        @athena: 5e15db396a23
        """
        tasks = {"build": Task(name="build", cmd="echo", desc="Build")}
        mock_get_recipe.return_value = self._create_mock_recipe(tasks)

        _list_tasks()

        table = self.mock_console.print.call_args[0][0]
        # Command column should have bold cyan style
        self.assertIn("bold", table.columns[0].style)
        self.assertIn("cyan", table.columns[0].style)

    @patch("tasktree.cli._get_recipe")
    def test_list_separates_columns_visually(self, mock_get_recipe):
        """
        Test list separates columns visually.
        @athena: 81ae146961ac
        """
        tasks = {"build": Task(name="build", cmd="echo", desc="Build", args=["env"])}
        mock_get_recipe.return_value = self._create_mock_recipe(tasks)

        _list_tasks()

        table = self.mock_console.print.call_args[0][0]
        # Padding should provide visual separation
        # Rich Table padding can be a tuple of (top, right, bottom, left) or (vertical, horizontal)
        self.assertIn(table.padding, [(0, 2), (0, 2, 0, 2)])

    @patch("tasktree.cli._get_recipe")
    def test_list_excludes_private_tasks(self, mock_get_recipe):
        """
        Test that private tasks are excluded from list output.
        @athena: 2e376baf6ab4
        """
        tasks = {
            "public": Task(
                name="public", cmd="echo public", desc="Public task", private=False
            ),
            "private": Task(
                name="private", cmd="echo private", desc="Private task", private=True
            ),
        }
        mock_get_recipe.return_value = self._create_mock_recipe(tasks)

        _list_tasks()

        table = self.mock_console.print.call_args[0][0]
        # Should only have 1 row (the public task)
        self.assertEqual(len(table.rows), 1)

    @patch("tasktree.cli._get_recipe")
    def test_list_includes_tasks_without_private_field(self, mock_get_recipe):
        """
        Test that tasks without private field (default False) are included.
        @athena: 90c9c3c42970
        """
        tasks = {
            "default": Task(name="default", cmd="echo default", desc="Default task"),
        }
        mock_get_recipe.return_value = self._create_mock_recipe(tasks)

        _list_tasks()

        table = self.mock_console.print.call_args[0][0]
        # Should have 1 row
        self.assertEqual(len(table.rows), 1)

    @patch("tasktree.cli._get_recipe")
    def test_list_with_mixed_private_and_public_tasks(self, mock_get_recipe):
        """
        Test list with mixed private and public tasks.
        @athena: 43ae91ae6522
        """
        tasks = {
            "public1": Task(
                name="public1", cmd="echo 1", desc="Public 1", private=False
            ),
            "private1": Task(
                name="private1", cmd="echo 2", desc="Private 1", private=True
            ),
            "public2": Task(name="public2", cmd="echo 3", desc="Public 2"),
            "private2": Task(
                name="private2", cmd="echo 4", desc="Private 2", private=True
            ),
        }
        mock_get_recipe.return_value = self._create_mock_recipe(tasks)

        _list_tasks()

        table = self.mock_console.print.call_args[0][0]
        # Should only have 2 rows (public1 and public2)
        self.assertEqual(len(table.rows), 2)

    @patch("tasktree.cli._get_recipe")
    def test_list_with_only_private_tasks(self, mock_get_recipe):
        """
        Test list with only private tasks shows empty table.
        @athena: 11ecb613c582
        """
        tasks = {
            "private1": Task(
                name="private1", cmd="echo 1", desc="Private 1", private=True
            ),
            "private2": Task(
                name="private2", cmd="echo 2", desc="Private 2", private=True
            ),
        }
        mock_get_recipe.return_value = self._create_mock_recipe(tasks)

        _list_tasks()

        table = self.mock_console.print.call_args[0][0]
        # Should have 0 rows
        self.assertEqual(len(table.rows), 0)


if __name__ == "__main__":
    unittest.main()
