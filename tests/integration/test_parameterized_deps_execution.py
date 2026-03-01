"""Integration tests for parameterized dependency execution."""

import os
import re
import unittest

from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from tasktree.cli import app
from fixture_utils import copy_fixture_files


def strip_ansi_codes(text: str) -> str:
    """
    Remove ANSI escape sequences from text.
    """
    ansi_escape = re.compile(r"\x1b\[[0-9;]*m")
    return ansi_escape.sub("", text)


class TestParameterizedDependencyExecution(unittest.TestCase):
    """
    Test that parameterized dependencies execute correctly end-to-end.
    """

    def setUp(self):
        """
        Set up test fixtures.
        """
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_parameterized_dependency_with_different_args(self):
        """
        Test that tasks can invoke same dependency with different arguments.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("parameterized_dep_different_args", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run test_debug - should build with debug mode
                result = self.runner.invoke(app, ["test_debug"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify debug build was created
                self.assertTrue((project_root / "build-debug.log").exists())
                self.assertTrue((project_root / "test-debug.log").exists())
                self.assertFalse((project_root / "build-release.log").exists())

                # Verify debug build content
                debug_content = (project_root / "build-debug.log").read_text()
                self.assertIn("debug", debug_content)
                self.assertIn("optimize=false", debug_content)

                # Run test_release - should build with release mode
                result = self.runner.invoke(app, ["test_release"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify release build was created
                self.assertTrue((project_root / "build-release.log").exists())
                self.assertTrue((project_root / "test-release.log").exists())

                # Verify release build content
                release_content = (project_root / "build-release.log").read_text()
                self.assertIn("release", release_content)
                self.assertIn("optimize=true", release_content)

            finally:
                os.chdir(original_cwd)

    def test_multiple_invocations_same_task(self):
        """
        Test task with multiple invocations of same dependency with different args.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("parameterized_dep_multiple_invocations", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run link - should compile both x86 and arm
                result = self.runner.invoke(app, ["link"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify both targets were compiled
                self.assertTrue((project_root / "compiled-x86.o").exists())
                self.assertTrue((project_root / "compiled-arm.o").exists())
                self.assertTrue((project_root / "linked.bin").exists())

                # Verify linked output contains both compilations
                linked_content = (project_root / "linked.bin").read_text()
                self.assertIn("x86", linked_content)
                self.assertIn("arm", linked_content)

            finally:
                os.chdir(original_cwd)

    def test_named_argument_dependency(self):
        """
        Test dependencies using named argument syntax.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("parameterized_dep_named_args", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run process - should generate XML with pretty=true
                result = self.runner.invoke(app, ["process"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify XML was generated
                self.assertTrue((project_root / "data.xml").exists())
                self.assertTrue((project_root / "processed.log").exists())

                # Verify content
                xml_content = (project_root / "data.xml").read_text()
                self.assertIn("xml", xml_content)
                self.assertIn("pretty=true", xml_content)

            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
