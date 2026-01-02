"""Integration tests for argument choices validation."""

import os
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from tasktree.cli import app


def strip_ansi_codes(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
    return ansi_escape.sub('', text)


class TestArgChoices(unittest.TestCase):
    """Test choices constraints on arguments in end-to-end workflows."""

    def setUp(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_valid_choice_succeeds(self):
        """Test that a valid choice value succeeds."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  deploy:
    args:
      - environment: { type: str, choices: ["dev", "staging", "prod"] }
    outputs: [deploy.log]
    cmd: echo "environment={{ arg.environment }}" > deploy.log
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Test valid choice
                result = self.runner.invoke(app, ["deploy", "dev"], env=self.env)
                self.assertEqual(result.exit_code, 0, f"Failed with output: {result.stdout}")

                log_content = (project_root / "deploy.log").read_text().strip()
                self.assertIn("environment=dev", log_content)

            finally:
                os.chdir(original_cwd)

    def test_invalid_choice_fails(self):
        """Test that an invalid choice value fails with clear error."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  deploy:
    args:
      - environment: { type: str, choices: ["dev", "staging", "prod"] }
    cmd: echo "environment={{ arg.environment }}"
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Test invalid choice
                result = self.runner.invoke(app, ["deploy", "testing"], env=self.env)
                self.assertNotEqual(result.exit_code, 0)
                output = strip_ansi_codes(result.stdout)
                self.assertIn("Invalid value for environment", output)
                self.assertIn("Valid choices", output)

            finally:
                os.chdir(original_cwd)

    def test_int_choices(self):
        """Test integer choices work correctly."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  scale:
    args:
      - replicas: { type: int, choices: [1, 3, 5] }
    outputs: [scale.log]
    cmd: echo "replicas={{ arg.replicas }}" > scale.log
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Test valid int choice
                result = self.runner.invoke(app, ["scale", "3"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                log_content = (project_root / "scale.log").read_text().strip()
                self.assertIn("replicas=3", log_content)

                # Clean up
                (project_root / "scale.log").unlink()

                # Test invalid int choice
                result = self.runner.invoke(app, ["scale", "2"], env=self.env)
                self.assertNotEqual(result.exit_code, 0)
                output = strip_ansi_codes(result.stdout)
                self.assertIn("Invalid value for replicas", output)

            finally:
                os.chdir(original_cwd)

    def test_type_inferred_from_choices(self):
        """Test that type is correctly inferred from choices."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  configure:
    args:
      - region: { choices: ["us-east-1", "eu-west-1"] }
    outputs: [config.log]
    cmd: echo "region={{ arg.region }}" > config.log
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Test valid choice
                result = self.runner.invoke(app, ["configure", "us-east-1"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                log_content = (project_root / "config.log").read_text().strip()
                self.assertIn("region=us-east-1", log_content)

            finally:
                os.chdir(original_cwd)

    def test_default_value_in_choices(self):
        """Test that default value works with choices."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  deploy:
    args:
      - environment: { choices: ["dev", "staging", "prod"], default: "dev" }
    outputs: [deploy.log]
    cmd: echo "environment={{ arg.environment }}" > deploy.log
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Test using default value
                result = self.runner.invoke(app, ["deploy"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                log_content = (project_root / "deploy.log").read_text().strip()
                self.assertIn("environment=dev", log_content)

            finally:
                os.chdir(original_cwd)

    def test_named_argument_with_choices(self):
        """Test named argument invocation respects choices."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  deploy:
    args:
      - app_name: { type: str }
      - environment: { choices: ["dev", "staging", "prod"] }
    outputs: [deploy.log]
    cmd: echo "{{ arg.app_name }} to {{ arg.environment }}" > deploy.log
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Test named argument with valid choice
                result = self.runner.invoke(app, ["deploy", "myapp", "environment=staging"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                log_content = (project_root / "deploy.log").read_text().strip()
                self.assertIn("myapp to staging", log_content)

            finally:
                os.chdir(original_cwd)

    def test_error_message_shows_valid_choices(self):
        """Test that error message includes list of valid choices."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  deploy:
    args:
      - environment: { choices: ["dev", "staging", "prod"] }
    cmd: echo "environment={{ arg.environment }}"
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Test that error message shows all valid choices
                result = self.runner.invoke(app, ["deploy", "invalid"], env=self.env)
                self.assertNotEqual(result.exit_code, 0)
                output = strip_ansi_codes(result.stdout)
                self.assertIn("'dev'", output)
                self.assertIn("'staging'", output)
                self.assertIn("'prod'", output)

            finally:
                os.chdir(original_cwd)

    def test_multiple_args_with_choices(self):
        """Test multiple arguments with choices validate independently."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  deploy:
    args:
      - environment: { choices: ["dev", "staging", "prod"] }
      - region: { choices: ["us-east-1", "eu-west-1"] }
    outputs: [deploy.log]
    cmd: echo "{{ arg.environment }} in {{ arg.region }}" > deploy.log
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Test both valid
                result = self.runner.invoke(app, ["deploy", "prod", "us-east-1"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                log_content = (project_root / "deploy.log").read_text().strip()
                self.assertIn("prod in us-east-1", log_content)

                # Clean up
                (project_root / "deploy.log").unlink()

                # Test first invalid
                result = self.runner.invoke(app, ["deploy", "test", "us-east-1"], env=self.env)
                self.assertNotEqual(result.exit_code, 0)

                # Test second invalid
                result = self.runner.invoke(app, ["deploy", "prod", "ap-south-1"], env=self.env)
                self.assertNotEqual(result.exit_code, 0)

            finally:
                os.chdir(original_cwd)

    def test_string_choices_with_special_characters(self):
        """Test string choices containing spaces and special characters."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  notify:
    args:
      - message: { choices: ["hello world", "foo-bar", "test_123"] }
    outputs: [notify.log]
    cmd: echo "{{ arg.message }}" > notify.log
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Test choice with space
                result = self.runner.invoke(app, ["notify", "hello world"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                log_content = (project_root / "notify.log").read_text().strip()
                self.assertIn("hello world", log_content)

            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
