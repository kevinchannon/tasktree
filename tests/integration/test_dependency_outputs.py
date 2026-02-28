"""Integration tests for dependency output references."""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tasktree.cli import app
from typer.testing import CliRunner

from tests.fixture_utils import copy_fixture_files


class TestDependencyOutputReferences(unittest.TestCase):
    """
    Test {{ dep.task.outputs.name }} template references.
    """

    def setUp(self):
        """
        """
        self.runner = CliRunner()
        self.original_cwd = os.getcwd()

    def tearDown(self):
        """
        """
        os.chdir(self.original_cwd)

    def test_basic_output_reference(self):
        """
        Test basic named output reference.
        """
        with TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            copy_fixture_files("dep_output_basic_reference", tmpdir)

            os.chdir(tmpdir)
            result = self.runner.invoke(app, ["deploy"])

            self.assertEqual(result.exit_code, 0, result.stdout)

            self.assertTrue((tmpdir / "generated/config.txt").exists())
            self.assertTrue((tmpdir / "dist/app.js").exists())

            config_content = (tmpdir / "generated/config.txt").read_text().strip()
            self.assertEqual("config-data", config_content)

            bundle_content = (tmpdir / "dist/app.js").read_text()
            self.assertIn("config-data", bundle_content)
            self.assertIn("bundled", bundle_content)

    def test_mixed_named_and_anonymous_outputs(self):
        """
        Test task with both named and anonymous outputs.
        """
        with TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            copy_fixture_files("dep_output_mixed_named_anonymous", tmpdir)

            os.chdir(tmpdir)
            result = self.runner.invoke(app, ["package"])

            self.assertEqual(result.exit_code, 0, result.stdout)

            self.assertTrue((tmpdir / "build/app").exists())
            self.assertTrue((tmpdir / "build/app.debug").exists())
            self.assertTrue((tmpdir / "build/app.sym").exists())

            self.assertEqual("binary", (tmpdir / "build/app").read_text().strip())
            self.assertEqual("debug", (tmpdir / "build/app.debug").read_text().strip())
            self.assertEqual("symbols", (tmpdir / "build/app.sym").read_text().strip())

    def test_transitive_output_references(self):
        """
        Test output references across multiple levels.
        """
        with TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            copy_fixture_files("dep_output_transitive", tmpdir)

            os.chdir(tmpdir)
            result = self.runner.invoke(app, ["app"])

            self.assertEqual(result.exit_code, 0, result.stdout)

            self.assertTrue((tmpdir / "out/libbase.a").exists())
            self.assertTrue((tmpdir / "out/libmiddleware.a").exists())

            base_content = (tmpdir / "out/libbase.a").read_text().strip()
            self.assertEqual("base-lib", base_content)

            middleware_content = (tmpdir / "out/libmiddleware.a").read_text().strip()
            self.assertIn("middleware uses out/libbase.a", middleware_content)

    def test_error_on_missing_output_name(self):
        """
        Test error when referencing non-existent output name.
        """
        with TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            copy_fixture_files("dep_output_error_missing_name", tmpdir)

            os.chdir(tmpdir)
            result = self.runner.invoke(app, ["deploy"])

            self.assertNotEqual(result.exit_code, 0)
            self.assertIsNotNone(result.exception)
            error_msg = str(result.output)
            self.assertIn("no output named 'missing'", error_msg)
            self.assertIn("Available named outputs", error_msg)
            self.assertIn("bundle", error_msg)

    def test_error_on_task_not_in_deps(self):
        """
        Test error when referencing task not in dependencies.
        """
        with TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            copy_fixture_files("dep_output_error_not_in_deps", tmpdir)

            os.chdir(tmpdir)
            result = self.runner.invoke(app, ["deploy"])

            self.assertNotEqual(result.exit_code, 0)
            self.assertIsNotNone(result.exception)
            error_msg = str(result.output)
            self.assertIn("unknown task", error_msg)
            self.assertIn("build", error_msg)

    def test_output_references_in_outputs_field(self):
        """
        Test that output references work in outputs field.
        """
        with TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            copy_fixture_files("dep_output_in_outputs_field", tmpdir)

            os.chdir(tmpdir)
            result = self.runner.invoke(app, ["build"])

            self.assertEqual(result.exit_code, 0, result.stdout)

            artifact = tmpdir / "dist/app-build.tar.gz"
            self.assertTrue(artifact.exists())

            content = artifact.read_text()
            self.assertIn("artifact-12345", content)
            self.assertIn("Using ID from: gen/build-id.txt", content)

    def test_backward_compatibility_anonymous_outputs(self):
        """
        Test that existing anonymous outputs still work.
        """
        with TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            copy_fixture_files("dep_output_backward_compat_anonymous", tmpdir)

            os.chdir(tmpdir)
            result = self.runner.invoke(app, ["deploy"])

            self.assertEqual(result.exit_code, 0, result.stdout)

            self.assertTrue((tmpdir / "dist/bundle.js").exists())
            self.assertTrue((tmpdir / "dist/bundle.css").exists())

            self.assertEqual("js", (tmpdir / "dist/bundle.js").read_text().strip())
            self.assertEqual("css", (tmpdir / "dist/bundle.css").read_text().strip())


if __name__ == "__main__":
    unittest.main()
