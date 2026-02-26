"""Unit tests for DockerArgs dataclass and parse_docker_args function."""

import unittest

from tasktree.parser import DockerArgs, parse_docker_args


class TestDockerArgs(unittest.TestCase):
    """Tests for the DockerArgs dataclass."""

    def test_docker_args_defaults_to_empty_lists(self):
        """Test that DockerArgs defaults to empty build and run lists."""
        args = DockerArgs()
        self.assertEqual(args.build, [])
        self.assertEqual(args.run, [])

    def test_docker_args_with_build_args(self):
        """Test creating DockerArgs with build arguments."""
        args = DockerArgs(build=["--no-cache", "-q"])
        self.assertEqual(args.build, ["--no-cache", "-q"])
        self.assertEqual(args.run, [])

    def test_docker_args_with_run_args(self):
        """Test creating DockerArgs with run arguments."""
        args = DockerArgs(run=["--rm", "--tty"])
        self.assertEqual(args.build, [])
        self.assertEqual(args.run, ["--rm", "--tty"])

    def test_docker_args_with_both(self):
        """Test creating DockerArgs with both build and run arguments."""
        args = DockerArgs(build=["-q"], run=["--rm", "--network=host"])
        self.assertEqual(args.build, ["-q"])
        self.assertEqual(args.run, ["--rm", "--network=host"])

    def test_docker_args_equality(self):
        """Test that two DockerArgs with same values are equal."""
        args1 = DockerArgs(build=["-q"], run=["--rm"])
        args2 = DockerArgs(build=["-q"], run=["--rm"])
        self.assertEqual(args1, args2)

    def test_docker_args_inequality_on_build(self):
        """Test that DockerArgs with different build args are not equal."""
        args1 = DockerArgs(build=["-q"])
        args2 = DockerArgs(build=["--no-cache"])
        self.assertNotEqual(args1, args2)

    def test_docker_args_inequality_on_run(self):
        """Test that DockerArgs with different run args are not equal."""
        args1 = DockerArgs(run=["--rm"])
        args2 = DockerArgs(run=["--tty"])
        self.assertNotEqual(args1, args2)

    def test_docker_args_build_and_run_are_independent(self):
        """Test that build and run lists are independent (separate default_factory)."""
        args1 = DockerArgs()
        args1.build.append("--no-cache")
        args2 = DockerArgs()
        # args2.build should still be empty (separate default_factory list)
        self.assertEqual(args2.build, [])


class TestParseDockerArgs(unittest.TestCase):
    """Tests for the parse_docker_args function (item-type validation)."""

    def test_non_string_build_item_raises_value_error(self):
        """Test that a non-string item in args.build raises ValueError."""
        with self.assertRaises(ValueError) as cm:
            parse_docker_args({"build": [123]}, "test-runner")
        self.assertIn("args.build[0]", str(cm.exception))
        self.assertIn("must be a string", str(cm.exception))

    def test_non_string_run_item_raises_value_error(self):
        """Test that a non-string item in args.run raises ValueError."""
        with self.assertRaises(ValueError) as cm:
            parse_docker_args({"run": [None]}, "test-runner")
        self.assertIn("args.run[0]", str(cm.exception))
        self.assertIn("must be a string", str(cm.exception))

    def test_valid_string_items_pass(self):
        """Test that valid string items are accepted."""
        args = parse_docker_args({"build": ["--no-cache"], "run": ["--rm"]}, "test-runner")
        self.assertEqual(args.build, ["--no-cache"])
        self.assertEqual(args.run, ["--rm"])

    def test_none_returns_empty_docker_args(self):
        """Test that None returns a default DockerArgs."""
        args = parse_docker_args(None, "test-runner")
        self.assertEqual(args.build, [])
        self.assertEqual(args.run, [])


if __name__ == "__main__":
    unittest.main()
