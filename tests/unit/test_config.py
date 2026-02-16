"""Tests for config module."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tasktree.config import (
    ConfigError,
    find_project_config,
    get_machine_config_path,
    get_user_config_path,
    parse_config_file,
)
from tasktree.parser import Runner


class TestGetUserConfigPath(unittest.TestCase):
    """
    Tests for get_user_config_path function.
    """

    @patch("platformdirs.user_config_dir")
    def test_returns_path_from_platformdirs(self, mock_user_config_dir):
        """
        Test that get_user_config_path uses platformdirs.user_config_dir.
        """
        mock_user_config_dir.return_value = "/home/user/.config/tasktree"
        result = get_user_config_path()
        mock_user_config_dir.assert_called_once_with("tasktree")
        self.assertEqual(result, Path("/home/user/.config/tasktree/config.yml"))

    @patch("platformdirs.user_config_dir")
    def test_returns_correct_path_on_linux(self, mock_user_config_dir):
        """
        Test that get_user_config_path returns correct path on Linux.
        """
        mock_user_config_dir.return_value = "/home/testuser/.config/tasktree"
        result = get_user_config_path()
        self.assertEqual(result, Path("/home/testuser/.config/tasktree/config.yml"))

    @patch("platformdirs.user_config_dir")
    def test_returns_correct_path_on_macos(self, mock_user_config_dir):
        """
        Test that get_user_config_path returns correct path on macOS.
        """
        mock_user_config_dir.return_value = (
            "/Users/testuser/Library/Application Support/tasktree"
        )
        result = get_user_config_path()
        self.assertEqual(
            result,
            Path("/Users/testuser/Library/Application Support/tasktree/config.yml"),
        )

    @patch("platformdirs.user_config_dir")
    def test_returns_correct_path_on_windows(self, mock_user_config_dir):
        """
        Test that get_user_config_path returns correct path on Windows.
        """
        # Use forward slashes for mock return value to avoid path separator issues
        mock_user_config_dir.return_value = "C:/Users/testuser/AppData/Local/tasktree"
        result = get_user_config_path()
        expected = Path("C:/Users/testuser/AppData/Local/tasktree/config.yml")
        self.assertEqual(result, expected)


class TestGetMachineConfigPath(unittest.TestCase):
    """
    Tests for get_machine_config_path function.
    """

    @patch("platformdirs.site_config_dir")
    def test_returns_path_from_platformdirs(self, mock_site_config_dir):
        """
        Test that get_machine_config_path uses platformdirs.site_config_dir.
        """
        mock_site_config_dir.return_value = "/etc/tasktree"
        result = get_machine_config_path()
        mock_site_config_dir.assert_called_once_with("tasktree")
        self.assertEqual(result, Path("/etc/tasktree/config.yml"))

    @patch("platformdirs.site_config_dir")
    def test_returns_correct_path_on_linux(self, mock_site_config_dir):
        """
        Test that get_machine_config_path returns correct path on Linux.
        """
        mock_site_config_dir.return_value = "/etc/xdg/tasktree"
        result = get_machine_config_path()
        self.assertEqual(result, Path("/etc/xdg/tasktree/config.yml"))

    @patch("platformdirs.site_config_dir")
    def test_returns_correct_path_on_macos(self, mock_site_config_dir):
        """
        Test that get_machine_config_path returns correct path on macOS.
        """
        mock_site_config_dir.return_value = "/Library/Application Support/tasktree"
        result = get_machine_config_path()
        self.assertEqual(
            result, Path("/Library/Application Support/tasktree/config.yml")
        )

    @patch("platformdirs.site_config_dir")
    def test_returns_correct_path_on_windows(self, mock_site_config_dir):
        """
        Test that get_machine_config_path returns correct path on Windows.
        """
        # Use forward slashes for mock return value to avoid path separator issues
        mock_site_config_dir.return_value = "C:/ProgramData/tasktree"
        result = get_machine_config_path()
        expected = Path("C:/ProgramData/tasktree/config.yml")
        self.assertEqual(result, expected)


class TestParseConfigFile(unittest.TestCase):
    """
    Tests for parse_config_file function.
    """

    def test_missing_file_returns_none(self):
        """
        Test that parse_config_file returns None for missing files.
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "nonexistent.yml"
            result = parse_config_file(config_path)
            self.assertIsNone(result)

    def test_empty_file_returns_none(self):
        """
        Test that parse_config_file returns None for empty files.
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yml"
            config_path.write_text("")
            result = parse_config_file(config_path)
            self.assertIsNone(result)

    def test_whitespace_only_file_returns_none(self):
        """
        Test that parse_config_file returns None for whitespace-only files.
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yml"
            config_path.write_text("   \n  \t  \n")
            result = parse_config_file(config_path)
            self.assertIsNone(result)

    def test_file_without_runners_key_returns_none(self):
        """
        Test that parse_config_file returns None for files without 'runners' key.
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yml"
            config_path.write_text("variables:\n  foo: bar\n")
            result = parse_config_file(config_path)
            self.assertIsNone(result)

    def test_valid_shell_runner(self):
        """
        Test that parse_config_file correctly parses a valid shell runner.
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yml"
            config_path.write_text(
                """runners:
  default:
    shell: bash
    preamble: set -euo pipefail
"""
            )
            result = parse_config_file(config_path)
            self.assertIsNotNone(result)
            self.assertIsInstance(result, Runner)
            self.assertEqual(result.name, "default")
            self.assertEqual(result.shell, "bash")
            self.assertEqual(result.preamble, "set -euo pipefail")
            self.assertEqual(result.dockerfile, "")

    def test_valid_dockerfile_runner(self):
        """
        Test that parse_config_file correctly parses a valid dockerfile runner.
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yml"
            config_path.write_text(
                """runners:
  default:
    dockerfile: docker/Dockerfile
    context: docker
"""
            )
            result = parse_config_file(config_path)
            self.assertIsNotNone(result)
            self.assertIsInstance(result, Runner)
            self.assertEqual(result.name, "default")
            self.assertEqual(result.dockerfile, "docker/Dockerfile")
            self.assertEqual(result.context, "docker")
            self.assertEqual(result.shell, "")

    def test_runner_with_all_fields(self):
        """
        Test that parse_config_file correctly parses a runner with all fields.
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yml"
            config_path.write_text(
                """runners:
  default:
    shell: zsh
    args: ["-c"]
    preamble: export FOO=bar
    working_dir: /workspace
    dockerfile: Dockerfile
    context: .
    volumes:
      - /host:/container:ro
    ports:
      - "8080:80"
    env_vars:
      VAR1: value1
    extra_args:
      - --network=host
    run_as_root: true
"""
            )
            result = parse_config_file(config_path)
            self.assertIsNotNone(result)
            self.assertEqual(result.shell, "zsh")
            self.assertEqual(result.args, ["-c"])
            self.assertEqual(result.preamble, "export FOO=bar")
            self.assertEqual(result.working_dir, "/workspace")
            self.assertEqual(result.dockerfile, "Dockerfile")
            self.assertEqual(result.context, ".")
            self.assertEqual(result.volumes, ["/host:/container:ro"])
            self.assertEqual(result.ports, ["8080:80"])
            self.assertEqual(result.env_vars, {"VAR1": "value1"})
            self.assertEqual(result.extra_args, ["--network=host"])
            self.assertTrue(result.run_as_root)

    def test_malformed_yaml_raises_error(self):
        """
        Test that parse_config_file raises ConfigError for malformed YAML.
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yml"
            config_path.write_text("runners:\n  default:\n    shell: bash\n  invalid yaml [")
            with self.assertRaises(ConfigError) as ctx:
                parse_config_file(config_path)
            self.assertIn("Error parsing YAML", str(ctx.exception))
            self.assertIn(str(config_path), str(ctx.exception))

    def test_runners_not_dict_raises_error(self):
        """
        Test that parse_config_file raises ConfigError when 'runners' is not a dict.
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yml"
            config_path.write_text("runners: [list, of, things]")
            with self.assertRaises(ConfigError) as ctx:
                parse_config_file(config_path)
            self.assertIn("'runners' must be a dictionary", str(ctx.exception))
            self.assertIn(str(config_path), str(ctx.exception))

    def test_missing_default_runner_raises_error(self):
        """
        Test that parse_config_file raises ConfigError when 'default' runner is missing.
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yml"
            config_path.write_text(
                """runners:
  some-other-runner:
    shell: bash
"""
            )
            with self.assertRaises(ConfigError) as ctx:
                parse_config_file(config_path)
            self.assertIn("must contain exactly one runner named 'default'", str(ctx.exception))
            self.assertIn(str(config_path), str(ctx.exception))

    def test_multiple_runners_raises_error(self):
        """
        Test that parse_config_file raises ConfigError when multiple runners are defined.
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yml"
            config_path.write_text(
                """runners:
  default:
    shell: bash
  extra-runner:
    shell: zsh
"""
            )
            with self.assertRaises(ConfigError) as ctx:
                parse_config_file(config_path)
            self.assertIn("may only contain a runner named 'default'", str(ctx.exception))
            self.assertIn("extra-runner", str(ctx.exception))
            self.assertIn(str(config_path), str(ctx.exception))

    def test_runner_config_not_dict_raises_error(self):
        """
        Test that parse_config_file raises ConfigError when runner config is not a dict.
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yml"
            config_path.write_text("runners:\n  default: bash")
            with self.assertRaises(ConfigError) as ctx:
                parse_config_file(config_path)
            self.assertIn("Runner 'default' must be a dictionary", str(ctx.exception))
            self.assertIn(str(config_path), str(ctx.exception))

    def test_missing_shell_and_dockerfile_raises_error(self):
        """
        Test that parse_config_file raises ConfigError when neither shell nor dockerfile is specified.
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yml"
            config_path.write_text(
                """runners:
  default:
    preamble: echo hello
"""
            )
            with self.assertRaises(ConfigError) as ctx:
                parse_config_file(config_path)
            self.assertIn("must specify either 'shell'", str(ctx.exception))
            self.assertIn("or 'dockerfile'", str(ctx.exception))
            self.assertIn(str(config_path), str(ctx.exception))

    def test_shell_runner_with_minimal_config(self):
        """
        Test that parse_config_file handles a shell runner with only required fields.
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yml"
            config_path.write_text(
                """runners:
  default:
    shell: bash
"""
            )
            result = parse_config_file(config_path)
            self.assertIsNotNone(result)
            self.assertEqual(result.shell, "bash")
            self.assertEqual(result.preamble, "")
            self.assertEqual(result.args, [])

    def test_dockerfile_runner_with_minimal_config(self):
        """
        Test that parse_config_file handles a dockerfile runner with only required fields.
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yml"
            config_path.write_text(
                """runners:
  default:
    dockerfile: Dockerfile
    context: .
"""
            )
            result = parse_config_file(config_path)
            self.assertIsNotNone(result)
            self.assertEqual(result.dockerfile, "Dockerfile")
            self.assertEqual(result.context, ".")
            self.assertEqual(result.volumes, [])
            self.assertEqual(result.ports, [])

    def test_relative_paths_stored_as_is(self):
        """
        Test that relative paths in config files are stored as-is without validation.
        Path validation is deferred to execution time as per spec.
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yml"
            config_path.write_text(
                """runners:
  default:
    dockerfile: ../nonexistent/Dockerfile
    context: ./build
    working_dir: relative/path
"""
            )
            result = parse_config_file(config_path)
            self.assertIsNotNone(result)
            # Verify relative paths are stored without validation
            self.assertEqual(result.dockerfile, "../nonexistent/Dockerfile")
            self.assertEqual(result.context, "./build")
            self.assertEqual(result.working_dir, "relative/path")

    def test_relative_paths_accepted_with_project_root(self):
        """
        Test that relative paths are accepted even when project_root is provided.
        Path validation happens at execution time, not parse time.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            config_path = project_root / "config.yml"
            config_path.write_text(
                """runners:
  default:
    dockerfile: docker/Dockerfile
    context: build
"""
            )
            # Parse config - should succeed even though paths don't exist
            # (validation happens at execution time)
            result = parse_config_file(config_path)
            self.assertIsNotNone(result)
            self.assertEqual(result.dockerfile, "docker/Dockerfile")
            self.assertEqual(result.context, "build")

    def test_relative_paths_stored_as_is(self):
        """
        Test that relative paths in config files are stored as-is.
        Path resolution happens at execution time, not parse time.
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yml"
            config_path.write_text(
                """runners:
  default:
    dockerfile: docker/Dockerfile
    context: .
"""
            )
            result = parse_config_file(config_path)
            self.assertIsNotNone(result)
            # Paths should be stored as-is (resolution happens at execution time)
            self.assertEqual(result.dockerfile, "docker/Dockerfile")
            self.assertEqual(result.context, ".")


class TestConfigFieldValidation(unittest.TestCase):
    """
    Tests for field type validation in config files.
    """

    def test_shell_must_be_string(self):
        """
        Test that parse_config_file raises ConfigError when 'shell' is not a string.
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yml"
            config_path.write_text(
                """runners:
  default:
    shell: 123
"""
            )
            with self.assertRaises(ConfigError) as ctx:
                parse_config_file(config_path)
            self.assertIn("'shell' must be a string", str(ctx.exception))
            self.assertIn(str(config_path), str(ctx.exception))

    def test_args_must_be_list(self):
        """
        Test that parse_config_file raises ConfigError when 'args' is not a list.
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yml"
            config_path.write_text(
                """runners:
  default:
    shell: bash
    args: "-c"
"""
            )
            with self.assertRaises(ConfigError) as ctx:
                parse_config_file(config_path)
            self.assertIn("'args' must be a list", str(ctx.exception))
            self.assertIn(str(config_path), str(ctx.exception))

    def test_preamble_must_be_string(self):
        """
        Test that parse_config_file raises ConfigError when 'preamble' is not a string.
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yml"
            config_path.write_text(
                """runners:
  default:
    shell: bash
    preamble: [set, -e]
"""
            )
            with self.assertRaises(ConfigError) as ctx:
                parse_config_file(config_path)
            self.assertIn("'preamble' must be a string", str(ctx.exception))
            self.assertIn(str(config_path), str(ctx.exception))

    def test_working_dir_must_be_string(self):
        """
        Test that parse_config_file raises ConfigError when 'working_dir' is not a string.
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yml"
            config_path.write_text(
                """runners:
  default:
    shell: bash
    working_dir: 123
"""
            )
            with self.assertRaises(ConfigError) as ctx:
                parse_config_file(config_path)
            self.assertIn("'working_dir' must be a string", str(ctx.exception))
            self.assertIn(str(config_path), str(ctx.exception))

    def test_dockerfile_must_be_string(self):
        """
        Test that parse_config_file raises ConfigError when 'dockerfile' is not a string.
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yml"
            config_path.write_text(
                """runners:
  default:
    dockerfile: 123
    context: .
"""
            )
            with self.assertRaises(ConfigError) as ctx:
                parse_config_file(config_path)
            self.assertIn("'dockerfile' must be a string", str(ctx.exception))
            self.assertIn(str(config_path), str(ctx.exception))

    def test_context_must_be_string(self):
        """
        Test that parse_config_file raises ConfigError when 'context' is not a string.
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yml"
            config_path.write_text(
                """runners:
  default:
    dockerfile: Dockerfile
    context: [path, to, context]
"""
            )
            with self.assertRaises(ConfigError) as ctx:
                parse_config_file(config_path)
            self.assertIn("'context' must be a string", str(ctx.exception))
            self.assertIn(str(config_path), str(ctx.exception))

    def test_volumes_must_be_list(self):
        """
        Test that parse_config_file raises ConfigError when 'volumes' is not a list.
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yml"
            config_path.write_text(
                """runners:
  default:
    dockerfile: Dockerfile
    context: .
    volumes: "/host:/container"
"""
            )
            with self.assertRaises(ConfigError) as ctx:
                parse_config_file(config_path)
            self.assertIn("'volumes' must be a list", str(ctx.exception))
            self.assertIn(str(config_path), str(ctx.exception))

    def test_ports_must_be_list(self):
        """
        Test that parse_config_file raises ConfigError when 'ports' is not a list.
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yml"
            config_path.write_text(
                """runners:
  default:
    dockerfile: Dockerfile
    context: .
    ports: "8080:80"
"""
            )
            with self.assertRaises(ConfigError) as ctx:
                parse_config_file(config_path)
            self.assertIn("'ports' must be a list", str(ctx.exception))
            self.assertIn(str(config_path), str(ctx.exception))

    def test_env_vars_must_be_dict(self):
        """
        Test that parse_config_file raises ConfigError when 'env_vars' is not a dict.
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yml"
            config_path.write_text(
                """runners:
  default:
    dockerfile: Dockerfile
    context: .
    env_vars: ["VAR1=value1", "VAR2=value2"]
"""
            )
            with self.assertRaises(ConfigError) as ctx:
                parse_config_file(config_path)
            self.assertIn("'env_vars' must be a dictionary", str(ctx.exception))
            self.assertIn(str(config_path), str(ctx.exception))

    def test_extra_args_must_be_list(self):
        """
        Test that parse_config_file raises ConfigError when 'extra_args' is not a list.
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yml"
            config_path.write_text(
                """runners:
  default:
    dockerfile: Dockerfile
    context: .
    extra_args: "--network=host"
"""
            )
            with self.assertRaises(ConfigError) as ctx:
                parse_config_file(config_path)
            self.assertIn("'extra_args' must be a list", str(ctx.exception))
            self.assertIn(str(config_path), str(ctx.exception))

    def test_run_as_root_must_be_bool(self):
        """
        Test that parse_config_file raises ConfigError when 'run_as_root' is not a boolean.
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yml"
            config_path.write_text(
                """runners:
  default:
    dockerfile: Dockerfile
    context: .
    run_as_root: "yes"
"""
            )
            with self.assertRaises(ConfigError) as ctx:
                parse_config_file(config_path)
            self.assertIn("'run_as_root' must be a boolean", str(ctx.exception))
            self.assertIn(str(config_path), str(ctx.exception))


class TestErrorMessageContext(unittest.TestCase):
    """
    Tests to verify all error messages include config file path for debugging.
    """

    def test_all_config_errors_include_file_path(self):
        """
        Test that all ConfigError exceptions include the config file path in the error message.

        This is a meta-test that verifies our error message requirements are met:
        - All errors must include the config file path
        - Error messages must be clear and actionable
        - Users should be able to quickly identify which file has the problem

        """
        test_cases = [
            # (yaml_content, expected_error_substring)
            ("runners: [not, a, dict]", "'runners' must be a dictionary"),
            (
                "runners:\n  other:\n    shell: bash",
                "must contain exactly one runner named 'default'",
            ),
            (
                "runners:\n  default:\n    shell: bash\n  extra:\n    shell: zsh",
                "may only contain a runner named 'default'",
            ),
            ("runners:\n  default: not-a-dict", "Runner 'default' must be a dictionary"),
            ("runners:\n  default:\n    preamble: test", "must specify either 'shell'"),
            ("runners:\n  default:\n    shell: 123", "'shell' must be a string"),
            ("runners:\n  default:\n    shell: bash\n    args: not-a-list", "'args' must be a list"),
            (
                "runners:\n  default:\n    shell: bash\n    preamble: [list]",
                "'preamble' must be a string",
            ),
            (
                "runners:\n  default:\n    dockerfile: Dockerfile\n    context: .\n    volumes: not-a-list",
                "'volumes' must be a list",
            ),
            (
                "runners:\n  default:\n    dockerfile: Dockerfile\n    context: .\n    env_vars: [list]",
                "'env_vars' must be a dictionary",
            ),
        ]

        with TemporaryDirectory() as tmpdir:
            for i, (yaml_content, error_substring) in enumerate(test_cases):
                with self.subTest(case=i, error=error_substring):
                    config_path = Path(tmpdir) / f"config_{i}.yml"
                    config_path.write_text(yaml_content)

                    with self.assertRaises(ConfigError) as ctx:
                        parse_config_file(config_path)

                    error_msg = str(ctx.exception)
                    # Verify the error message includes the config file path
                    self.assertIn(
                        str(config_path),
                        error_msg,
                        f"Error message does not include config file path: {error_msg}",
                    )
                    # Verify the error message includes the specific error
                    self.assertIn(
                        error_substring,
                        error_msg,
                        f"Error message does not include expected text: {error_msg}",
                    )


class TestFindProjectConfig(unittest.TestCase):
    """
    Tests for find_project_config function.
    """

    def test_find_config_in_current_directory(self):
        """
        Test that find_project_config finds config in the current directory.
        """
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir).resolve()
            config_path = tmppath / ".tasktree-config.yml"
            config_path.write_text("# test config")

            result = find_project_config(tmppath)
            self.assertIsNotNone(result)
            self.assertEqual(result, config_path)

    def test_find_config_in_parent_directory(self):
        """
        Test that find_project_config finds config in parent directory.
        """
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir).resolve()
            config_path = tmppath / ".tasktree-config.yml"
            config_path.write_text("# test config")

            # Start from a subdirectory
            subdir = tmppath / "subdir"
            subdir.mkdir()

            result = find_project_config(subdir)
            self.assertIsNotNone(result)
            self.assertEqual(result, config_path)

    def test_find_config_in_grandparent_directory(self):
        """
        Test that find_project_config finds config in grandparent directory.
        """
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir).resolve()
            config_path = tmppath / ".tasktree-config.yml"
            config_path.write_text("# test config")

            # Start from a nested subdirectory
            nested = tmppath / "level1" / "level2"
            nested.mkdir(parents=True)

            result = find_project_config(nested)
            self.assertIsNotNone(result)
            self.assertEqual(result, config_path)

    def test_find_config_returns_none_when_not_found(self):
        """
        Test that find_project_config returns None when no config is found.
        """
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir).resolve()
            # Don't create any config file

            result = find_project_config(tmppath)
            self.assertIsNone(result)

    def test_find_config_stops_at_first_match(self):
        """
        Test that find_project_config returns the first config found (closest to start_dir).
        """
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir).resolve()

            # Create config at root level
            root_config = tmppath / ".tasktree-config.yml"
            root_config.write_text("# root config")

            # Create config in subdirectory
            subdir = tmppath / "subdir"
            subdir.mkdir()
            subdir_config = subdir / ".tasktree-config.yml"
            subdir_config.write_text("# subdir config")

            # Start from subdirectory - should find the closer one
            result = find_project_config(subdir)
            self.assertIsNotNone(result)
            self.assertEqual(result, subdir_config)

    def test_find_config_with_nested_directories(self):
        """
        Test that find_project_config works with deeply nested directory structures.
        """
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir).resolve()

            # Create a deep directory structure
            deep_path = tmppath / "a" / "b" / "c" / "d" / "e"
            deep_path.mkdir(parents=True)

            # Create config at intermediate level
            config_path = tmppath / "a" / "b" / ".tasktree-config.yml"
            config_path.write_text("# config at level b")

            # Start from deep directory
            result = find_project_config(deep_path)
            self.assertIsNotNone(result)
            self.assertEqual(result, config_path)

    def test_find_config_with_nonexistent_start_dir(self):
        """
        Test that find_project_config returns None for non-existent start directory.
        """
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir).resolve()
            nonexistent = tmppath / "does-not-exist"

            result = find_project_config(nonexistent)
            self.assertIsNone(result)

    def test_find_config_with_file_as_start_dir(self):
        """
        Test that find_project_config handles a file path as start_dir.
        """
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir).resolve()

            # Create a config file in the directory
            config_path = tmppath / ".tasktree-config.yml"
            config_path.write_text("# test config")

            # Create a regular file
            file_path = tmppath / "somefile.txt"
            file_path.write_text("some content")

            # Start from the file - should search from its parent and find the config
            result = find_project_config(file_path)
            self.assertIsNotNone(result)
            self.assertEqual(result, config_path)

    def test_find_config_with_symlinked_directory(self):
        """
        Test that find_project_config correctly handles symlinked directories.
        """
        import sys

        # Skip test on Windows where symlinks require special privileges
        if sys.platform == "win32":
            self.skipTest("Symlink test skipped on Windows")

        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir).resolve()

            # Create a real directory with config
            real_dir = tmppath / "real"
            real_dir.mkdir()
            config_path = real_dir / ".tasktree-config.yml"
            config_path.write_text("# test config")

            # Create a subdirectory in the real directory
            subdir = real_dir / "subdir"
            subdir.mkdir()

            # Create a symlink to the subdirectory
            symlink = tmppath / "link-to-subdir"
            try:
                symlink.symlink_to(subdir)
            except OSError:
                # If symlink creation fails (permissions, etc.), skip the test
                self.skipTest("Unable to create symlink")

            # Start from the symlink - should resolve it and find config in parent
            result = find_project_config(symlink)
            self.assertIsNotNone(result)
            self.assertEqual(result, config_path)


if __name__ == "__main__":
    unittest.main()
