"""Unit tests for DockerArgs dataclass."""

import unittest

from tasktree.parser import DockerArgs


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


if __name__ == "__main__":
    unittest.main()
