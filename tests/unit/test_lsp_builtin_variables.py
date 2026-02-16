"""Tests for LSP built-in variables."""

import unittest
from tasktree.lsp.builtin_variables import BUILTIN_VARIABLES


class TestBuiltinVariables(unittest.TestCase):
    """Tests for BUILTIN_VARIABLES constant."""

    def test_builtin_variables_is_list(self):
        """Test that BUILTIN_VARIABLES is a list."""
        self.assertIsInstance(BUILTIN_VARIABLES, list)

    def test_builtin_variables_contains_all_expected(self):
        """Test that BUILTIN_VARIABLES contains all expected variables."""
        expected = [
            "project_root",
            "recipe_dir",
            "task_name",
            "working_dir",
            "timestamp",
            "timestamp_unix",
            "user_home",
            "user_name",
        ]
        self.assertEqual(set(BUILTIN_VARIABLES), set(expected))

    def test_builtin_variables_count(self):
        """Test that we have exactly 8 built-in variables."""
        self.assertEqual(len(BUILTIN_VARIABLES), 8)

    def test_builtin_variables_are_strings(self):
        """Test that all built-in variables are strings."""
        for var in BUILTIN_VARIABLES:
            self.assertIsInstance(var, str)

    def test_builtin_variables_no_duplicates(self):
        """Test that there are no duplicate variable names."""
        self.assertEqual(len(BUILTIN_VARIABLES), len(set(BUILTIN_VARIABLES)))


if __name__ == "__main__":
    unittest.main()
