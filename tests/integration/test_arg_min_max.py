"""Integration tests for min/max argument validation."""

import os
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from tasktree.cli import app


def strip_ansi_codes(text: str) -> str:
    """
    Remove ANSI escape sequences from text.
    @athena: 90023a269128
    """
    ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
    return ansi_escape.sub('', text)


class TestArgMinMax(unittest.TestCase):
    """
    Test min/max constraints on arguments in end-to-end workflows.
    @athena: 9d206bda611a
    """

    def setUp(self):
        """
        Set up test fixtures.
        @athena: 36a706d60319
        """
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_int_arg_within_range(self):
        """
        Test integer argument value within min/max range succeeds.
        @athena: 714f9c7d4bbd
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  deploy:
    args:
      - replicas: { type: int, min: 1, max: 10 }
    outputs: [deploy.log]
    cmd: echo "replicas={{ arg.replicas }}" > deploy.log
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Test valid value within range
                result = self.runner.invoke(app, ["deploy", "5"], env=self.env)
                self.assertEqual(result.exit_code, 0, f"Failed with output: {result.stdout}")

                log_content = (project_root / "deploy.log").read_text().strip()
                self.assertIn("replicas=5", log_content)

            finally:
                os.chdir(original_cwd)

    def test_int_arg_below_min_fails(self):
        """
        Test integer argument value below min fails with clear error.
        @athena: 8368e5a86f20
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  deploy:
    args:
      - replicas: { type: int, min: 1, max: 10 }
    cmd: echo "replicas={{ arg.replicas }}"
""")

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
        @athena: 11799273f525
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  deploy:
    args:
      - replicas: { type: int, min: 1, max: 10 }
    cmd: echo "replicas={{ arg.replicas }}"
""")

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
        @athena: df3109d98f42
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  deploy:
    args:
      - count: { type: int, min: 1, max: 100 }
    outputs: [result.txt]
    cmd: echo "count={{ arg.count }}" > result.txt
""")

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
        @athena: a639bfb41ad1
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  configure:
    args:
      - timeout: { type: float, min: 0.5, max: 30.0 }
    outputs: [config.txt]
    cmd: echo "timeout={{ arg.timeout }}" > config.txt
""")

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
        @athena: e2722db6f2bf
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  configure:
    args:
      - timeout: { type: float, min: 0.5, max: 30.0 }
    cmd: echo "timeout={{ arg.timeout }}"
""")

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
        @athena: a58bbd3d8f9f
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  start:
    args:
      - port: { type: int, min: 1024 }
    outputs: [port.txt]
    cmd: echo "port={{ arg.port }}" > port.txt
""")

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
        @athena: b28dc290b403
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  set:
    args:
      - percentage: { type: float, max: 100.0 }
    outputs: [value.txt]
    cmd: echo "percentage={{ arg.percentage }}" > value.txt
""")

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
        @athena: 697bd561c88a
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  start:
    args:
      - workers: { type: int, min: 1, max: 16, default: 4 }
    outputs: [workers.txt]
    cmd: echo "workers={{ arg.workers }}" > workers.txt
""")

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
        @athena: fe1c928b2bf2
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  set_temp:
    args:
      - temperature: { type: int, min: -100, max: 100 }
    outputs: [temp.txt]
    cmd: echo "temperature={{ arg.temperature }}" > temp.txt
""")

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
        @athena: 1a382b4f0c24
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  bad:
    args:
      - value: { type: int, min: 100, max: 1 }
    cmd: echo "value={{ arg.value }}"
""")

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
        @athena: e702c9892686
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  bad:
    args:
      - name: { type: str, min: 1, max: 10 }
    cmd: echo "name={{ arg.name }}"
""")

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
