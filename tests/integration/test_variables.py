"""Integration tests for variables feature."""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from tasktree.cli import app
from fixture_utils import copy_fixture_files


class TestVariablesIntegration(unittest.TestCase):
    """
    Test end-to-end variables functionality through CLI.
    """

    def setUp(self):
        """
        Set up test fixtures.
        """
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_variables_in_command_execution(self):
        """
        Test task actually runs with variables substituted.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            copy_fixture_files("variables_in_command_execution", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["test"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify output contains substituted variable
                output_file = project_root / "output.txt"
                self.assertTrue(output_file.exists())
                content = output_file.read_text().strip()
                self.assertEqual(content, "Hello from variables")

            finally:
                os.chdir(original_cwd)

    def test_variables_with_args_combined(self):
        """
        Test both vars and args in same command execute correctly.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            copy_fixture_files("variables_with_args_combined", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task with argument
                result = self.runner.invoke(app, ["deploy", "myapp"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify output contains both substituted variable and argument
                output_file = project_root / "deploy-myapp.log"
                self.assertTrue(output_file.exists())
                content = output_file.read_text().strip()
                self.assertEqual(content, "Deploy myapp to prod.example.com:8080")

            finally:
                os.chdir(original_cwd)

    def test_variable_types_stringify(self):
        """
        Test int/bool/float become strings in output.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            copy_fixture_files("variable_types_stringify", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["test"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify all types converted to strings
                output_file = project_root / "config.txt"
                content = output_file.read_text().strip()
                self.assertEqual(content, "port=8080 debug=true timeout=30.5")

            finally:
                os.chdir(original_cwd)

    def test_complex_variable_chain(self):
        """
        Test A uses B, B uses C, all resolve correctly.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            copy_fixture_files("complex_variable_chain", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["test"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify variable chain resolved correctly
                output_file = project_root / "endpoints.txt"
                content = output_file.read_text().strip()
                lines = content.split("\n")
                self.assertEqual(lines[0], "https://api.example.com/users")
                self.assertEqual(lines[1], "https://api.example.com/posts")

            finally:
                os.chdir(original_cwd)

    def test_variables_in_working_dir_execution(self):
        """
        Test working_dir with variables actually changes execution directory.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create subdirectory
            subdir = project_root / "build"
            subdir.mkdir()

            copy_fixture_files("variables_in_working_dir", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["test"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify task ran in subdirectory
                output_file = subdir / "result.txt"
                self.assertTrue(output_file.exists())
                content = output_file.read_text().strip()
                # Content should be the absolute path to build directory
                self.assertTrue(content.endswith("build"))

            finally:
                os.chdir(original_cwd)

    def test_variables_in_multiple_tasks(self):
        """
        Test same variables used across multiple tasks.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            copy_fixture_files("variables_in_multiple_tasks", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run deploy task (which depends on build)
                result = self.runner.invoke(app, ["deploy"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify both tasks used variables correctly
                build_output = (project_root / "build.log").read_text().strip()
                self.assertEqual(build_output, "Building myapp v1.2.3")

                deploy_output = (project_root / "deploy.log").read_text().strip()
                self.assertEqual(deploy_output, "Deploying myapp v1.2.3")

            finally:
                os.chdir(original_cwd)

    def test_error_undefined_variable_at_runtime(self):
        """
        Test clear error message when variable is undefined.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            copy_fixture_files("error_undefined_variable", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run should fail with clear error
                result = self.runner.invoke(app, ["test"], env=self.env)
                self.assertNotEqual(result.exit_code, 0)

                # Error should mention the undefined variable
                output = result.stdout
                self.assertIn("undefined", output.lower())

            finally:
                os.chdir(original_cwd)

    def test_error_circular_reference_at_parse_time(self):
        """
        Test circular reference error is caught at parse time.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            copy_fixture_files("error_circular_reference", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Should fail at parse time with circular reference error
                result = self.runner.invoke(app, ["test"], env=self.env)
                self.assertNotEqual(result.exit_code, 0)

                # Error should mention circular reference
                output = result.stdout
                self.assertIn("circular", output.lower())

            finally:
                os.chdir(original_cwd)

    def test_variables_with_special_characters(self):
        """
        Test variables containing special shell characters.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            copy_fixture_files("variables_with_special_characters", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["test"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify special characters preserved
                output_file = project_root / "output.txt"
                content = output_file.read_text().strip()
                # $USER will be expanded by shell, but quotes should be preserved
                self.assertIn("from 'variables'", content)

            finally:
                os.chdir(original_cwd)

    def test_env_variable_in_command_execution(self):
        """
        Test task runs with environment variable substituted.
        """
        # Set environment variable for test
        os.environ["TEST_API_KEY"] = "secret123"
        os.environ["TEST_DB_HOST"] = "localhost"

        try:
            with TemporaryDirectory() as tmpdir:
                project_root = Path(tmpdir)
                copy_fixture_files("env_variable_in_command", project_root)

                original_cwd = os.getcwd()
                try:
                    os.chdir(project_root)

                    # Run task
                    result = self.runner.invoke(app, ["test"], env=self.env)
                    self.assertEqual(result.exit_code, 0)

                    # Verify env vars were substituted correctly
                    output_file = project_root / "config.txt"
                    self.assertTrue(output_file.exists())
                    content = output_file.read_text().strip()
                    self.assertEqual(content, "API=secret123 DB=localhost:5432")

                finally:
                    os.chdir(original_cwd)

        finally:
            # Clean up environment variables
            del os.environ["TEST_API_KEY"]
            del os.environ["TEST_DB_HOST"]

    def test_env_variable_undefined_at_runtime(self):
        """
        Test clear error when environment variable not set.
        """
        # Ensure env var is NOT set
        if "TEST_UNDEFINED_VAR" in os.environ:
            del os.environ["TEST_UNDEFINED_VAR"]

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            copy_fixture_files("env_variable_undefined", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Should fail at parse time with clear error
                result = self.runner.invoke(app, ["test"], env=self.env)
                self.assertNotEqual(result.exit_code, 0)

                # Error should mention the undefined env variable
                output = result.stdout
                self.assertIn("TEST_UNDEFINED_VAR", output)
                self.assertIn("not set", output.lower())

            finally:
                os.chdir(original_cwd)

    def test_environment_variable_substitution_in_command(self):
        """
        Test {{ env.VAR }} substitution works in actual execution.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            copy_fixture_files("env_substitution_in_command", project_root)

            # Set test env var
            test_env = {"NO_COLOR": "1", "USER": "testuser"}

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["test"], env=test_env)
                self.assertEqual(result.exit_code, 0)

                # Verify output contains substituted env var
                output_file = project_root / "output.txt"
                self.assertTrue(output_file.exists())
                content = output_file.read_text().strip()
                self.assertEqual(content, "User is testuser")

            finally:
                os.chdir(original_cwd)

    def test_mixed_substitution_var_arg_env(self):
        """
        Test all three substitution types work together.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            copy_fixture_files("mixed_substitution_var_arg_env", project_root)

            test_env = {"NO_COLOR": "1", "USER": "admin"}

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                result = self.runner.invoke(app, ["deploy", "myapp"], env=test_env)
                self.assertEqual(result.exit_code, 0)

                output_file = project_root / "deploy.log"
                self.assertTrue(output_file.exists())
                content = output_file.read_text().strip()
                self.assertEqual(content, "Deploy myapp to prod.example.com as admin")

            finally:
                os.chdir(original_cwd)

    def test_undefined_env_var_error(self):
        """
        Test clear error when environment variable is not set.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            copy_fixture_files("undefined_env_var_error", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                result = self.runner.invoke(app, ["test"], env=self.env)
                self.assertNotEqual(result.exit_code, 0)
                self.assertIn("UNDEFINED_VAR_XYZ", result.output)
                self.assertIn("not set", " ".join(result.output.split()))

            finally:
                os.chdir(original_cwd)

    def test_env_substitution_in_working_dir(self):
        """
        Test environment variable substitution works in working_dir.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create subdirectory with env-based name
            subdir = project_root / "testdir"
            subdir.mkdir()

            copy_fixture_files("env_substitution_in_working_dir", project_root)

            test_env = {"NO_COLOR": "1", "TEST_DIR": "testdir"}

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                result = self.runner.invoke(app, ["test"], env=test_env)
                self.assertEqual(result.exit_code, 0)

                # Verify file was created in subdirectory
                output_file = subdir / "output.txt"
                self.assertTrue(output_file.exists())

            finally:
                os.chdir(original_cwd)

    def test_file_read_in_command_execution(self):
        """
        Test file content is actually used in task execution.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create secret file
            secret_file = project_root / "api-key.txt"
            secret_file.write_text("secret-api-key-123\n")

            copy_fixture_files("file_read_in_command", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["test"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify file content was used (newline stripped)
                output_file = project_root / "result.txt"
                self.assertTrue(output_file.exists())
                content = output_file.read_text().strip()
                self.assertEqual(content, "Key: secret-api-key-123")

            finally:
                os.chdir(original_cwd)

    def test_file_read_with_variable_expansion(self):
        """
        Test file contains variable references.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create file with variable reference
            config_file = project_root / "config.txt"
            config_file.write_text("server-{{ var.environment }}")

            copy_fixture_files("file_read_with_variable_expansion", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["test"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify variable expansion happened
                output_file = project_root / "result.txt"
                content = output_file.read_text().strip()
                self.assertEqual(content, "server-prod")

            finally:
                os.chdir(original_cwd)

    def test_file_read_and_env_combined(self):
        """
        Test mix of file read and env variables in same recipe.
        """
        # Set environment variable for test
        os.environ["TEST_DEPLOY_USER"] = "admin"

        try:
            with TemporaryDirectory() as tmpdir:
                project_root = Path(tmpdir)

                # Create API key file
                api_key_file = project_root / "api-key.txt"
                api_key_file.write_text("secret-123")

                copy_fixture_files("file_read_and_env_combined", project_root)

                original_cwd = os.getcwd()
                try:
                    os.chdir(project_root)

                    # Run task
                    result = self.runner.invoke(app, ["test"], env=self.env)
                    self.assertEqual(result.exit_code, 0)

                    # Verify all three variable types work
                    output_file = project_root / "result.txt"
                    content = output_file.read_text().strip()
                    self.assertEqual(content, "myapp secret-123 admin")

                finally:
                    os.chdir(original_cwd)

        finally:
            del os.environ["TEST_DEPLOY_USER"]

    def test_file_read_error_not_found(self):
        """
        Test missing file produces clear error.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            copy_fixture_files("file_read_error_not_found", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Should fail with clear error
                result = self.runner.invoke(app, ["test"], env=self.env)
                self.assertNotEqual(result.exit_code, 0)

                # Check error message
                output = result.stdout
                self.assertIn("Failed to read file", output)
                self.assertIn("nonexistent.txt", output)
                self.assertIn("File not found", output)

            finally:
                os.chdir(original_cwd)

    def test_env_variable_with_default_when_not_set(self):
        """
        Test default value is used when environment variable is not set.
        """
        # Ensure env var is NOT set
        if "TEST_PORT_DEFAULT" in os.environ:
            del os.environ["TEST_PORT_DEFAULT"]

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            copy_fixture_files("env_variable_with_default_not_set", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["test"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify default value was used
                output_file = project_root / "config.txt"
                self.assertTrue(output_file.exists())
                content = output_file.read_text().strip()
                self.assertEqual(content, "Port=8080")

            finally:
                os.chdir(original_cwd)

    def test_env_variable_with_default_when_set(self):
        """
        Test environment variable value is used when set, ignoring default.
        """
        # Set environment variable
        os.environ["TEST_PORT_OVERRIDE"] = "9000"

        try:
            with TemporaryDirectory() as tmpdir:
                project_root = Path(tmpdir)
                copy_fixture_files("env_variable_with_default_set", project_root)

                original_cwd = os.getcwd()
                try:
                    os.chdir(project_root)

                    # Run task
                    result = self.runner.invoke(app, ["test"], env=self.env)
                    self.assertEqual(result.exit_code, 0)

                    # Verify env var value was used, not default
                    output_file = project_root / "config.txt"
                    self.assertTrue(output_file.exists())
                    content = output_file.read_text().strip()
                    self.assertEqual(content, "Port=9000")

                finally:
                    os.chdir(original_cwd)

        finally:
            del os.environ["TEST_PORT_OVERRIDE"]

    def test_env_variable_empty_string_vs_default(self):
        """
        Test that empty string env var is used, not the default.
        """
        # Set environment variable to empty string
        os.environ["TEST_EMPTY_VAR"] = ""

        try:
            with TemporaryDirectory() as tmpdir:
                project_root = Path(tmpdir)
                copy_fixture_files("env_variable_empty_string_vs_default", project_root)

                original_cwd = os.getcwd()
                try:
                    os.chdir(project_root)

                    # Run task
                    result = self.runner.invoke(app, ["test"], env=self.env)
                    self.assertEqual(result.exit_code, 0)

                    # Verify empty string was used (not default)
                    output_file = project_root / "output.txt"
                    self.assertTrue(output_file.exists())
                    content = output_file.read_text().strip()
                    self.assertEqual(content, "Value=[]")

                finally:
                    os.chdir(original_cwd)

        finally:
            del os.environ["TEST_EMPTY_VAR"]

    def test_env_variable_default_must_be_string(self):
        """
        Test that non-string defaults are rejected.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            copy_fixture_files("env_variable_default_must_be_string", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Should fail at parse time with clear error
                result = self.runner.invoke(app, ["test"], env=self.env)
                self.assertNotEqual(result.exit_code, 0)

                # Error should mention that default must be string
                output = result.stdout
                self.assertIn("default", output.lower())
                self.assertIn("string", output.lower())

            finally:
                os.chdir(original_cwd)

    def test_env_variable_multiple_with_defaults(self):
        """
        Test multiple env variables with defaults work together.
        """
        # Set only one env var
        os.environ["TEST_HOST"] = "prod.example.com"

        try:
            # Ensure other env var is NOT set
            if "TEST_PORT" in os.environ:
                del os.environ["TEST_PORT"]

            with TemporaryDirectory() as tmpdir:
                project_root = Path(tmpdir)
                copy_fixture_files("env_variable_multiple_with_defaults", project_root)

                original_cwd = os.getcwd()
                try:
                    os.chdir(project_root)

                    # Run task
                    result = self.runner.invoke(app, ["test"], env=self.env)
                    self.assertEqual(result.exit_code, 0)

                    # Verify one used env var, one used default
                    output_file = project_root / "config.txt"
                    self.assertTrue(output_file.exists())
                    content = output_file.read_text().strip()
                    self.assertEqual(content, "URL=prod.example.com:8080")

                finally:
                    os.chdir(original_cwd)

        finally:
            del os.environ["TEST_HOST"]

    def test_env_variable_default_with_variable_substitution(self):
        """
        Test default value can contain variable references.
        """
        # Ensure env var is NOT set
        if "TEST_OVERRIDE" in os.environ:
            del os.environ["TEST_OVERRIDE"]

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            copy_fixture_files("env_variable_default_with_var_substitution", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["test"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify default with variable substitution worked
                output_file = project_root / "config.txt"
                self.assertTrue(output_file.exists())
                content = output_file.read_text().strip()
                self.assertEqual(content, "Endpoint=https://api.example.com/users")

            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
