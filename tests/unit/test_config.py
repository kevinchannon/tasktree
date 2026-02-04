"""Tests for config module."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tasktree.config import ConfigError, parse_config_file
from tasktree.parser import Runner


class TestParseConfigFile(unittest.TestCase):
    """
    Tests for parse_config_file function.
    @athena: to-be-generated
    """

    def test_missing_file_returns_none(self):
        """
        Test that parse_config_file returns None for missing files.
        @athena: to-be-generated
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "nonexistent.yml"
            result = parse_config_file(config_path)
            self.assertIsNone(result)

    def test_empty_file_returns_none(self):
        """
        Test that parse_config_file returns None for empty files.
        @athena: to-be-generated
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yml"
            config_path.write_text("")
            result = parse_config_file(config_path)
            self.assertIsNone(result)

    def test_whitespace_only_file_returns_none(self):
        """
        Test that parse_config_file returns None for whitespace-only files.
        @athena: to-be-generated
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yml"
            config_path.write_text("   \n  \t  \n")
            result = parse_config_file(config_path)
            self.assertIsNone(result)

    def test_file_without_runners_key_returns_none(self):
        """
        Test that parse_config_file returns None for files without 'runners' key.
        @athena: to-be-generated
        """
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yml"
            config_path.write_text("variables:\n  foo: bar\n")
            result = parse_config_file(config_path)
            self.assertIsNone(result)

    def test_valid_shell_runner(self):
        """
        Test that parse_config_file correctly parses a valid shell runner.
        @athena: to-be-generated
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
        @athena: to-be-generated
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
        @athena: to-be-generated
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
        @athena: to-be-generated
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
        @athena: to-be-generated
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
        @athena: to-be-generated
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
        @athena: to-be-generated
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
        @athena: to-be-generated
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
        @athena: to-be-generated
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
        @athena: to-be-generated
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
        @athena: to-be-generated
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


if __name__ == "__main__":
    unittest.main()
