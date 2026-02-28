"""Integration tests for min/max argument validation."""

import os
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from tasktree.cli import app
from tests.fixture_utils import copy_fixture_files


def strip_ansi_codes(text: str) -> str:
    """
    Remove ANSI escape sequences from text.
    """
    ansi_escape = re.compile(r"\x1b\[[0-9;]*m")
    return ansi_escape.sub("", text)


class TestArgMinMax(unittest.TestCase):
    """
    Test min/max constraints on arguments in end-to-end workflows.
    """

    def setUp(self):
        """
        Set up test fixtures.
        """
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_int_arg_within_range(self):
        """
        Test integer argument value within min/max range succeeds.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("arg_min_max_int_with_output", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Test valid value within range
                result = self.runner.invoke(app, ["deploy", "5"], env=self.env)
                self.assertEqual(
                    result.exit_code, 0, f"Failed with output: {result.stdout}"
                )

                log_content = (project_root / "deploy.log").read_text().strip()
                self.assertIn("replicas=5", log_content)

            finally:
                os.chdir(original_cwd)

    def test_int_arg_below_min_fails(self):
        """
        Test integer argument value below min fails with clear error.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("arg_min_max_int_no_output", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Test value below min
                result = self.runner.invoke(app, ["deploy", "0"], env=self.env)
                self.assertNotEqual(result.exit_code, 0)
                output = strip_ansi_codes(result.stdout)
                self.assertIn("Invalid value for replicas", output)

            finally:
                os.chdir(original_cwd)

    def test_int_arg_above_max_fails(self):
        """
        Test integer argument value above max fails with clear error.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("arg_min_max_int_no_output", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Test value above max
                result = self.runner.invoke(app, ["deploy", "15"], env=self.env)
                self.assertNotEqual(result.exit_code, 0)
                output = strip_ansi_codes(result.stdout)
                self.assertIn("Invalid value for replicas", output)

            finally:
                os.chdir(original_cwd)

    def test_int_arg_at_boundaries(self):
        """
        Test integer argument at exact min and max boundaries.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("arg_min_max_int_boundaries", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Test at min boundary
                result = self.runner.invoke(app, ["deploy", "1"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                log_content = (project_root / "result.txt").read_text().strip()
                self.assertIn("count=1", log_content)

                # Clean up
                (project_root / "result.txt").unlink()

                # Test at max boundary
                result = self.runner.invoke(app, ["deploy", "100"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                log_content = (project_root / "result.txt").read_text().strip()
                self.assertIn("count=100", log_content)

            finally:
                os.chdir(original_cwd)

    def test_float_arg_within_range(self):
        """
        Test float argument value within min/max range succeeds.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("arg_min_max_float_with_output", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Test valid float value
                result = self.runner.invoke(app, ["configure", "15.5"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                log_content = (project_root / "config.txt").read_text().strip()
                self.assertIn("timeout=15.5", log_content)

            finally:
                os.chdir(original_cwd)

    def test_float_arg_below_min_fails(self):
        """
        Test float argument value below min fails.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("arg_min_max_float_no_output", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Test value below min
                result = self.runner.invoke(app, ["configure", "0.1"], env=self.env)
                self.assertNotEqual(result.exit_code, 0)
                output = strip_ansi_codes(result.stdout)
                self.assertIn("Invalid value for timeout", output)

            finally:
                os.chdir(original_cwd)

    def test_int_arg_with_min_only(self):
        """
        Test integer argument with only min constraint.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("arg_min_max_min_only", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Test valid port (above min, no max)
                result = self.runner.invoke(app, ["start", "8080"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                log_content = (project_root / "port.txt").read_text().strip()
                self.assertIn("port=8080", log_content)

                # Clean up
                (project_root / "port.txt").unlink()

                # Test invalid port (below min)
                result = self.runner.invoke(app, ["start", "80"], env=self.env)
                self.assertNotEqual(result.exit_code, 0)

            finally:
                os.chdir(original_cwd)

    def test_float_arg_with_max_only(self):
        """
        Test float argument with only max constraint.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("arg_min_max_max_only", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Test valid percentage (below max, no min)
                result = self.runner.invoke(app, ["set", "75.5"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                log_content = (project_root / "value.txt").read_text().strip()
                self.assertIn("percentage=75.5", log_content)

                # Clean up
                (project_root / "value.txt").unlink()

                # Test invalid percentage (above max)
                result = self.runner.invoke(app, ["set", "150.0"], env=self.env)
                self.assertNotEqual(result.exit_code, 0)

            finally:
                os.chdir(original_cwd)

    def test_default_within_range(self):
        """
        Test that default value within range is accepted and used.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("arg_min_max_with_default", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Test with default value (not providing argument)
                result = self.runner.invoke(app, ["start"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                log_content = (project_root / "workers.txt").read_text().strip()
                self.assertIn("workers=4", log_content)

            finally:
                os.chdir(original_cwd)

    def test_negative_int_range(self):
        """
        Test integer range with negative values.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("arg_min_max_negative", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Test negative value within range
                result = self.runner.invoke(app, ["set_temp", "-50"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                log_content = (project_root / "temp.txt").read_text().strip()
                self.assertIn("temperature=-50", log_content)

            finally:
                os.chdir(original_cwd)

    def test_parse_error_on_invalid_min_max_config(self):
        """
        Test that min > max in recipe file causes parse error.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("arg_min_max_invalid_config", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # This should fail during recipe parsing
                result = self.runner.invoke(app, ["bad", "50"], env=self.env)
                self.assertNotEqual(result.exit_code, 0)
                output = strip_ansi_codes(result.stdout)
                # Should mention min/max constraint error
                self.assertTrue("min" in output.lower() or "max" in output.lower())

            finally:
                os.chdir(original_cwd)

    def test_parse_error_on_non_numeric_type_with_min_max(self):
        """
        Test that min/max on non-numeric type causes parse error.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("arg_min_max_non_numeric", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # This should fail during recipe parsing
                result = self.runner.invoke(app, ["bad", "test"], env=self.env)
                self.assertNotEqual(result.exit_code, 0)
                output = strip_ansi_codes(result.stdout)
                # Should mention that min/max only work with int/float
                self.assertIn("min/max constraints are only supported", output)

            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
