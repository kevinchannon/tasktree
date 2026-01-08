"""Integration tests for dependency output references."""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tasktree.cli import app
from typer.testing import CliRunner


class TestDependencyOutputReferences(unittest.TestCase):
    """Test {{ dep.task.outputs.name }} template references."""

    def setUp(self):
        self.runner = CliRunner()
        self.original_cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self.original_cwd)

    def test_basic_output_reference(self):
        """Test basic named output reference."""
        with TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create recipe with named output reference
            recipe_path = tmpdir / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
  generate:
    outputs:
      - config: "generated/config.txt"
    cmd: |
      mkdir -p generated
      echo "config-data" > generated/config.txt

  build:
    deps: [generate]
    outputs:
      - bundle: "dist/app.js"
    cmd: |
      mkdir -p dist
      cat {{ dep.generate.outputs.config }} > dist/app.js
      echo " bundled" >> dist/app.js

  deploy:
    deps: [build]
    cmd: |
      echo "Deploying {{ dep.build.outputs.bundle }}"
      cat {{ dep.build.outputs.bundle }}
"""
            )

            # Run deploy task (should execute all dependencies)
            os.chdir(tmpdir)
            result = self.runner.invoke(app, ["deploy"])

            # Check execution succeeded
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("Deploying dist/app.js", result.stdout)
            self.assertIn("config-data bundled", result.stdout)

            # Verify files were created
            self.assertTrue((tmpdir / "generated/config.txt").exists())
            self.assertTrue((tmpdir / "dist/app.js").exists())

            # Verify content
            bundle_content = (tmpdir / "dist/app.js").read_text()
            self.assertIn("config-data", bundle_content)
            self.assertIn("bundled", bundle_content)

    def test_mixed_named_and_anonymous_outputs(self):
        """Test task with both named and anonymous outputs."""
        with TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            recipe_path = tmpdir / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
  compile:
    outputs:
      - binary: "build/app"
      - "build/app.debug"
      - symbols: "build/app.sym"
    cmd: |
      mkdir -p build
      echo "binary" > build/app
      echo "debug" > build/app.debug
      echo "symbols" > build/app.sym

  package:
    deps: [compile]
    cmd: |
      echo "Packaging {{ dep.compile.outputs.binary }}"
      echo "Symbols: {{ dep.compile.outputs.symbols }}"
      cat {{ dep.compile.outputs.binary }} {{ dep.compile.outputs.symbols }}
"""
            )

            os.chdir(tmpdir)
            result = self.runner.invoke(app, ["package"])

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("Packaging build/app", result.stdout)
            self.assertIn("Symbols: build/app.sym", result.stdout)
            self.assertIn("binary", result.stdout)
            self.assertIn("symbols", result.stdout)

    def test_transitive_output_references(self):
        """Test output references across multiple levels."""
        with TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            recipe_path = tmpdir / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
  base:
    outputs:
      - lib: "out/libbase.a"
    cmd: |
      mkdir -p out
      echo "base-lib" > out/libbase.a

  middleware:
    deps: [base]
    outputs:
      - lib: "out/libmiddleware.a"
    cmd: |
      echo "middleware uses {{ dep.base.outputs.lib }}" > out/libmiddleware.a

  app:
    deps: [middleware]
    cmd: |
      echo "App uses {{ dep.middleware.outputs.lib }}"
      cat {{ dep.middleware.outputs.lib }}
"""
            )

            os.chdir(tmpdir)
            result = self.runner.invoke(app, ["app"])

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("App uses out/libmiddleware.a", result.stdout)
            self.assertIn("middleware uses out/libbase.a", result.stdout)

    def test_error_on_missing_output_name(self):
        """Test error when referencing non-existent output name."""
        with TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            recipe_path = tmpdir / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
  build:
    outputs:
      - bundle: "dist/app.js"
    cmd: echo "build"

  deploy:
    deps: [build]
    cmd: echo "{{ dep.build.outputs.missing }}"
"""
            )

            os.chdir(tmpdir)
            result = self.runner.invoke(app, ["deploy"])

            self.assertNotEqual(result.exit_code, 0)
            self.assertIn("no output named 'missing'", result.stdout)
            self.assertIn("Available named outputs", result.stdout)
            self.assertIn("bundle", result.stdout)

    def test_error_on_task_not_in_deps(self):
        """Test error when referencing task not in dependencies."""
        with TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            recipe_path = tmpdir / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
  build:
    outputs:
      - bundle: "dist/app.js"
    cmd: echo "build"

  other:
    cmd: echo "other"

  deploy:
    deps: [other]
    cmd: echo "{{ dep.build.outputs.bundle }}"
"""
            )

            os.chdir(tmpdir)
            result = self.runner.invoke(app, ["deploy"])

            self.assertNotEqual(result.exit_code, 0)
            self.assertIn("not list it as a dependency", result.stdout)
            self.assertIn("build", result.stdout)

    def test_output_references_in_outputs_field(self):
        """Test that output references work in outputs field."""
        with TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            recipe_path = tmpdir / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
  generate:
    outputs:
      - id: "gen/build-id.txt"
    cmd: |
      mkdir -p gen
      echo "12345" > gen/build-id.txt

  build:
    deps: [generate]
    outputs:
      - artifact: "dist/app-{{ dep.generate.outputs.id }}.tar.gz"
    cmd: |
      mkdir -p dist
      # Create artifact with ID in name
      ID=$(cat {{ dep.generate.outputs.id }})
      echo "artifact-$ID" > dist/app-{{ dep.generate.outputs.id }}.tar.gz
"""
            )

            os.chdir(tmpdir)
            result = self.runner.invoke(app, ["build"])

            self.assertEqual(result.exit_code, 0, result.stdout)

            # The output filename should contain the reference path
            expected_file = tmpdir / "dist" / "app-gen/build-id.txt.tar.gz"
            self.assertTrue(expected_file.exists(), f"Expected file not found: {expected_file}")

    def test_backward_compatibility_anonymous_outputs(self):
        """Test that existing anonymous outputs still work."""
        with TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            recipe_path = tmpdir / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
  build:
    outputs: ["dist/bundle.js", "dist/bundle.css"]
    cmd: |
      mkdir -p dist
      echo "js" > dist/bundle.js
      echo "css" > dist/bundle.css

  deploy:
    deps: [build]
    cmd: |
      echo "Deploying"
      cat dist/bundle.js dist/bundle.css
"""
            )

            os.chdir(tmpdir)
            result = self.runner.invoke(app, ["deploy"])

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("js", result.stdout)
            self.assertIn("css", result.stdout)


if __name__ == "__main__":
    unittest.main()
