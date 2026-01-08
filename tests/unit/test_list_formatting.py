"""Unit tests for --list output formatting."""

import unittest
from unittest.mock import MagicMock, patch

from rich.console import Console
from rich.table import Table

from tasktree.cli import _format_task_arguments, _list_tasks
from tasktree.parser import Recipe, Task


class TestFormatTaskArguments(unittest.TestCase):
    """Tests for _format_task_arguments() function."""

    def test_format_no_arguments(self):
        """Test formatting task with no arguments."""
        result = _format_task_arguments([])
        self.assertEqual(result, "")

    def test_format_single_required_argument(self):
        """Test formatting task with single required argument."""
        result = _format_task_arguments(["environment"])
        self.assertEqual(result, "environment[dim]:str[/dim]")

    def test_format_single_optional_argument(self):
        """Test formatting task with single optional argument."""
        result = _format_task_arguments([{"environment": {"default": "production"}}])
        self.assertIn("environment[dim]:str[/dim]", result)
        self.assertIn("[dim]\\[=production][/dim]", result)

    def test_format_multiple_required_arguments(self):
        """Test formatting task with multiple required arguments."""
        result = _format_task_arguments(["mode", "target"])
        self.assertIn("mode[dim]:str[/dim]", result)
        self.assertIn("target[dim]:str[/dim]", result)
        # Verify order is preserved
        self.assertTrue(result.index("mode") < result.index("target"))

    def test_format_multiple_optional_arguments(self):
        """Test formatting task with multiple optional arguments."""
        result = _format_task_arguments([{"mode": {"default": "debug"}}, {"target": {"default": "x86_64"}}])
        self.assertIn("mode[dim]:str[/dim]", result)
        self.assertIn("[dim]\\[=debug][/dim]", result)
        self.assertIn("target[dim]:str[/dim]", result)
        self.assertIn("[dim]\\[=x86_64][/dim]", result)

    def test_format_mixed_required_and_optional_arguments(self):
        """Test formatting task with mixed required and optional arguments."""
        result = _format_task_arguments(["environment", {"region": {"default": "us-west-1"}}])
        self.assertIn("environment[dim]:str[/dim]", result)
        self.assertIn("region[dim]:str[/dim]", result)
        self.assertIn("[dim]\\[=us-west-1][/dim]", result)
        # Verify order is preserved
        self.assertTrue(result.index("environment") < result.index("region"))

    def test_format_arguments_in_definition_order(self):
        """Test formatting preserves argument definition order."""
        result = _format_task_arguments(["first", "second", "third"])
        # Verify order by checking indices
        self.assertTrue(result.index("first") < result.index("second"))
        self.assertTrue(result.index("second") < result.index("third"))
        self.assertIn("first[dim]:str[/dim]", result)
        self.assertIn("second[dim]:str[/dim]", result)
        self.assertIn("third[dim]:str[/dim]", result)

    def test_format_default_values_with_equals_sign(self):
        """Test formatting shows default values with equals sign."""
        result = _format_task_arguments([{"port": {"default": "8080"}}])
        self.assertIn("[dim]\\[=8080][/dim]", result)

    def test_format_shows_str_type_explicitly(self):
        """Test formatting shows str type explicitly."""
        result = _format_task_arguments(["name"])
        self.assertIn("name[dim]:str[/dim]", result)

    def test_format_shows_int_type(self):
        """Test formatting shows int type."""
        result = _format_task_arguments([{"port": {"type": "int"}}])
        self.assertIn("port[dim]:int[/dim]", result)

    def test_format_shows_float_type(self):
        """Test formatting shows float type."""
        result = _format_task_arguments([{"timeout": {"type": "float"}}])
        self.assertIn("timeout[dim]:float[/dim]", result)

    def test_format_shows_bool_type(self):
        """Test formatting shows bool type."""
        result = _format_task_arguments([{"verbose": {"type": "bool"}}])
        self.assertIn("verbose[dim]:bool[/dim]", result)

    def test_format_shows_path_type(self):
        """Test formatting shows path type."""
        result = _format_task_arguments([{"output": {"type": "path"}}])
        self.assertIn("output[dim]:path[/dim]", result)

    def test_format_shows_datetime_type(self):
        """Test formatting shows datetime type."""
        # Using dict format for datetime
        result = _format_task_arguments([{"timestamp": {"type": "datetime"}}])
        self.assertIn("timestamp[dim]:datetime[/dim]", result)

    def test_format_shows_ip_types(self):
        """Test formatting shows ip, ipv4, ipv6 types."""
        result_ip = _format_task_arguments([{"addr": {"type": "ip"}}])
        self.assertIn("addr[dim]:ip[/dim]", result_ip)

        result_ipv4 = _format_task_arguments([{"addr": {"type": "ipv4"}}])
        self.assertIn("addr[dim]:ipv4[/dim]", result_ipv4)

        result_ipv6 = _format_task_arguments([{"addr": {"type": "ipv6"}}])
        self.assertIn("addr[dim]:ipv6[/dim]", result_ipv6)

    def test_format_shows_email_type(self):
        """Test formatting shows email type."""
        result = _format_task_arguments([{"contact": {"type": "email"}}])
        self.assertIn("contact[dim]:email[/dim]", result)

    def test_format_shows_hostname_type(self):
        """Test formatting shows hostname type."""
        result = _format_task_arguments([{"server": {"type": "hostname"}}])
        self.assertIn("server[dim]:hostname[/dim]", result)

    def test_format_shows_all_argument_types_explicitly(self):
        """Test formatting shows all argument types explicitly."""
        # Even default str type should be shown
        result = _format_task_arguments(["name"])
        self.assertIn("[dim]:str[/dim]", result)

    def test_format_handles_task_with_many_arguments(self):
        """Test formatting handles task with many arguments."""
        many_args = [f"arg{i}" for i in range(10)]
        result = _format_task_arguments(many_args)
        # All arguments should be present
        for i in range(10):
            self.assertIn(f"arg{i}[dim]:str[/dim]", result)

    def test_format_dict_argument_with_default(self):
        """Test formatting dict-style argument with default."""
        result = _format_task_arguments([{"port": {"type": "int", "default": 8080}}])
        self.assertIn("port[dim]:int[/dim]", result)
        self.assertIn("[dim]\\[=8080][/dim]", result)

    def test_format_dict_argument_without_default(self):
        """Test formatting dict-style argument without default."""
        result = _format_task_arguments([{"port": {"type": "int"}}])
        self.assertIn("port[dim]:int[/dim]", result)
        self.assertNotIn("=", result)

    def test_format_escapes_rich_markup_in_defaults(self):
        """Test formatting properly escapes Rich markup in default values."""
        # Test with brackets in default value
        result = _format_task_arguments([{"pattern": {"default": "[a-z]+"}}])
        # The brackets in the default should be escaped
        self.assertIn("[dim]\\[=[a-z]+][/dim]", result)

        # Test with dict-style argument containing special characters
        result2 = _format_task_arguments([{"regex": {"type": "str", "default": "[0-9]+"}}])
        self.assertIn("regex[dim]:str[/dim]", result2)
        self.assertIn("[dim]\\[=[0-9]+][/dim]", result2)


class TestListFormatting(unittest.TestCase):
    """Tests for _list_tasks() output formatting."""

    def setUp(self):
        """Set up test fixtures."""
        self.console_patch = patch('tasktree.cli.console')
        self.mock_console = self.console_patch.start()

    def tearDown(self):
        """Clean up patches."""
        self.console_patch.stop()

    def _create_mock_recipe(self, tasks_dict):
        """Create a mock Recipe with given tasks.

        Args:
            tasks_dict: Dict of task_name -> Task object
        """
        recipe = MagicMock(spec=Recipe)
        recipe.task_names.return_value = list(tasks_dict.keys())
        recipe.get_task.side_effect = lambda name: tasks_dict.get(name)
        return recipe

    @patch('tasktree.cli._get_recipe')
    def test_list_uses_borderless_table_format(self, mock_get_recipe):
        """Test list uses borderless table format."""
        tasks = {
            "build": Task(name="build", cmd="echo build", desc="Build task")
        }
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

    @patch('tasktree.cli._get_recipe')
    def test_list_applies_correct_column_padding(self, mock_get_recipe):
        """Test list applies correct column padding."""
        tasks = {
            "build": Task(name="build", cmd="echo build", desc="Build task")
        }
        mock_get_recipe.return_value = self._create_mock_recipe(tasks)

        _list_tasks()

        table = self.mock_console.print.call_args[0][0]
        # Rich Table padding can be a tuple of (top, right, bottom, left) or (vertical, horizontal)
        # Check that horizontal padding is 2
        self.assertIn(table.padding, [(0, 2), (0, 2, 0, 2)])

    @patch('tasktree.cli._get_recipe')
    def test_list_calculates_command_column_width_from_longest_task_name(self, mock_get_recipe):
        """Test list calculates command column width from longest task name."""
        tasks = {
            "short": Task(name="short", cmd="echo", desc="Short"),
            "very-long-task-name": Task(name="very-long-task-name", cmd="echo", desc="Long"),
            "mid": Task(name="mid", cmd="echo", desc="Mid"),
        }
        mock_get_recipe.return_value = self._create_mock_recipe(tasks)

        _list_tasks()

        table = self.mock_console.print.call_args[0][0]
        # Command column should have width equal to longest name
        self.assertEqual(table.columns[0].width, len("very-long-task-name"))

    @patch('tasktree.cli._get_recipe')
    def test_list_command_column_never_wraps(self, mock_get_recipe):
        """Test list command column never wraps."""
        tasks = {
            "task": Task(name="task", cmd="echo", desc="Task")
        }
        mock_get_recipe.return_value = self._create_mock_recipe(tasks)

        _list_tasks()

        table = self.mock_console.print.call_args[0][0]
        # Command column should have no_wrap=True
        self.assertTrue(table.columns[0].no_wrap)

    @patch('tasktree.cli._get_recipe')
    def test_list_shows_namespaced_tasks(self, mock_get_recipe):
        """Test list shows namespaced tasks."""
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

    @patch('tasktree.cli._get_recipe')
    def test_list_formats_tasks_from_multiple_namespaces(self, mock_get_recipe):
        """Test list formats tasks from multiple namespaces."""
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

    @patch('tasktree.cli._get_recipe')
    def test_list_handles_empty_task_list(self, mock_get_recipe):
        """Test list handles empty task list."""
        tasks = {}
        mock_get_recipe.return_value = self._create_mock_recipe(tasks)

        _list_tasks()

        # Should still print a table (just empty)
        self.mock_console.print.assert_called_once()
        table = self.mock_console.print.call_args[0][0]
        self.assertEqual(len(table.rows), 0)

    @patch('tasktree.cli._get_recipe')
    def test_list_handles_tasks_with_long_descriptions(self, mock_get_recipe):
        """Test list handles tasks with long descriptions."""
        long_desc = "This is a very long description that should wrap in the description column " * 5
        tasks = {
            "task": Task(name="task", cmd="echo", desc=long_desc)
        }
        mock_get_recipe.return_value = self._create_mock_recipe(tasks)

        _list_tasks()

        # Should not raise any errors
        self.mock_console.print.assert_called_once()

    @patch('tasktree.cli._get_recipe')
    def test_list_applies_bold_style_to_task_names(self, mock_get_recipe):
        """Test list applies bold style to task names."""
        tasks = {
            "build": Task(name="build", cmd="echo", desc="Build")
        }
        mock_get_recipe.return_value = self._create_mock_recipe(tasks)

        _list_tasks()

        table = self.mock_console.print.call_args[0][0]
        # Command column should have bold cyan style
        self.assertIn("bold", table.columns[0].style)
        self.assertIn("cyan", table.columns[0].style)

    @patch('tasktree.cli._get_recipe')
    def test_list_separates_columns_visually(self, mock_get_recipe):
        """Test list separates columns visually."""
        tasks = {
            "build": Task(name="build", cmd="echo", desc="Build", args=["env"])
        }
        mock_get_recipe.return_value = self._create_mock_recipe(tasks)

        _list_tasks()

        table = self.mock_console.print.call_args[0][0]
        # Padding should provide visual separation
        # Rich Table padding can be a tuple of (top, right, bottom, left) or (vertical, horizontal)
        self.assertIn(table.padding, [(0, 2), (0, 2, 0, 2)])

    @patch('tasktree.cli._get_recipe')
    def test_list_excludes_private_tasks(self, mock_get_recipe):
        """Test that private tasks are excluded from list output."""
        tasks = {
            "public": Task(name="public", cmd="echo public", desc="Public task", private=False),
            "private": Task(name="private", cmd="echo private", desc="Private task", private=True),
        }
        mock_get_recipe.return_value = self._create_mock_recipe(tasks)

        _list_tasks()

        table = self.mock_console.print.call_args[0][0]
        # Should only have 1 row (the public task)
        self.assertEqual(len(table.rows), 1)

    @patch('tasktree.cli._get_recipe')
    def test_list_includes_tasks_without_private_field(self, mock_get_recipe):
        """Test that tasks without private field (default False) are included."""
        tasks = {
            "default": Task(name="default", cmd="echo default", desc="Default task"),
        }
        mock_get_recipe.return_value = self._create_mock_recipe(tasks)

        _list_tasks()

        table = self.mock_console.print.call_args[0][0]
        # Should have 1 row
        self.assertEqual(len(table.rows), 1)

    @patch('tasktree.cli._get_recipe')
    def test_list_with_mixed_private_and_public_tasks(self, mock_get_recipe):
        """Test list with mixed private and public tasks."""
        tasks = {
            "public1": Task(name="public1", cmd="echo 1", desc="Public 1", private=False),
            "private1": Task(name="private1", cmd="echo 2", desc="Private 1", private=True),
            "public2": Task(name="public2", cmd="echo 3", desc="Public 2"),
            "private2": Task(name="private2", cmd="echo 4", desc="Private 2", private=True),
        }
        mock_get_recipe.return_value = self._create_mock_recipe(tasks)

        _list_tasks()

        table = self.mock_console.print.call_args[0][0]
        # Should only have 2 rows (public1 and public2)
        self.assertEqual(len(table.rows), 2)

    @patch('tasktree.cli._get_recipe')
    def test_list_with_only_private_tasks(self, mock_get_recipe):
        """Test list with only private tasks shows empty table."""
        tasks = {
            "private1": Task(name="private1", cmd="echo 1", desc="Private 1", private=True),
            "private2": Task(name="private2", cmd="echo 2", desc="Private 2", private=True),
        }
        mock_get_recipe.return_value = self._create_mock_recipe(tasks)

        _list_tasks()

        table = self.mock_console.print.call_args[0][0]
        # Should have 0 rows
        self.assertEqual(len(table.rows), 0)


if __name__ == "__main__":
    unittest.main()
