"""Integration tests for dependency output references."""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tasktree.cli import app
from typer.testing import CliRunner


class TestDependencyOutputReferences(unittest.TestCase):
    """
    Test {{ dep.task.outputs.name }} template references.
    @athena: 398929af7bd8
    """

    def setUp(self):
        """
        @athena: a7ea58f41c87
        """
        self.runner = CliRunner()
        self.original_cwd = os.getcwd()

    def tearDown(self):
        """
        @athena: 63b8f9e02fea
        """
        os.chdir(self.original_cwd)

    def test_basic_output_reference(self):
        """
        Test basic named output reference.
        @athena: d557dfa33e2b
        """
        with TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create recipe with named output reference
            recipe_path = tmpdir / "tasktree.yaml"
            recipe_path.write_text("""
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
""")

            # Run deploy task (should execute all dependencies)
            os.chdir(tmpdir)
            result = self.runner.invoke(app, ["deploy"])

            # Check execution succeeded
            self.assertEqual(result.exit_code, 0, result.stdout)

            # Verify files were created (proof that templates resolved correctly)
            self.assertTrue((tmpdir / "generated/config.txt").exists())
            self.assertTrue((tmpdir / "dist/app.js").exists())

            # Verify content (proof that dependency outputs were used correctly)
            config_content = (tmpdir / "generated/config.txt").read_text().strip()
            self.assertEqual("config-data", config_content)

            bundle_content = (tmpdir / "dist/app.js").read_text()
            self.assertIn("config-data", bundle_content)
            self.assertIn("bundled", bundle_content)

    def test_mixed_named_and_anonymous_outputs(self):
        """
        Test task with both named and anonymous outputs.
        @athena: 62e974978726
        """
        with TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            recipe_path = tmpdir / "tasktree.yaml"
            recipe_path.write_text("""
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
""")

            os.chdir(tmpdir)
            result = self.runner.invoke(app, ["package"])

            self.assertEqual(result.exit_code, 0, result.stdout)

            # Verify files were created (proof that templates resolved correctly)
            self.assertTrue((tmpdir / "build/app").exists())
            self.assertTrue((tmpdir / "build/app.debug").exists())
            self.assertTrue((tmpdir / "build/app.sym").exists())

            # Verify content (proof that named outputs were accessed correctly)
            self.assertEqual("binary", (tmpdir / "build/app").read_text().strip())
            self.assertEqual("debug", (tmpdir / "build/app.debug").read_text().strip())
            self.assertEqual("symbols", (tmpdir / "build/app.sym").read_text().strip())

    def test_transitive_output_references(self):
        """
        Test output references across multiple levels.
        @athena: 3e58fb45ddb0
        """
        with TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            recipe_path = tmpdir / "tasktree.yaml"
            recipe_path.write_text("""
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
""")

            os.chdir(tmpdir)
            result = self.runner.invoke(app, ["app"])

            self.assertEqual(result.exit_code, 0, result.stdout)

            # Verify files were created (proof that transitive templates resolved correctly)
            self.assertTrue((tmpdir / "out/libbase.a").exists())
            self.assertTrue((tmpdir / "out/libmiddleware.a").exists())

            # Verify content (proof that transitive dependency outputs were used correctly)
            base_content = (tmpdir / "out/libbase.a").read_text().strip()
            self.assertEqual("base-lib", base_content)

            middleware_content = (tmpdir / "out/libmiddleware.a").read_text().strip()
            self.assertIn("middleware uses out/libbase.a", middleware_content)

    def test_error_on_missing_output_name(self):
        """
        Test error when referencing non-existent output name.
        @athena: 3290631bbe12
        """
        with TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            recipe_path = tmpdir / "tasktree.yaml"
            recipe_path.write_text("""
tasks:
  build:
    outputs:
      - bundle: "dist/app.js"
    cmd: echo "build"

  deploy:
    deps: [build]
    cmd: echo "{{ dep.build.outputs.missing }}"
""")

            os.chdir(tmpdir)
            result = self.runner.invoke(app, ["deploy"])

            self.assertNotEqual(result.exit_code, 0)
            # Error messages are in the exception, not stdout
            self.assertIsNotNone(result.exception)
            error_msg = str(result.output)
            self.assertIn("no output named 'missing'", error_msg)
            self.assertIn("Available named outputs", error_msg)
            self.assertIn("bundle", error_msg)

    def test_error_on_task_not_in_deps(self):
        """
        Test error when referencing task not in dependencies.
        @athena: 4c08aaeae0a5
        """
        with TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            recipe_path = tmpdir / "tasktree.yaml"
            recipe_path.write_text("""
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
""")

            os.chdir(tmpdir)
            result = self.runner.invoke(app, ["deploy"])

            self.assertNotEqual(result.exit_code, 0)
            # Error messages are in the exception, not stdout
            self.assertIsNotNone(result.exception)
            error_msg = str(result.output)
            # The task isn't in resolved_tasks because it's not a dependency
            self.assertIn("unknown task", error_msg)
            self.assertIn("build", error_msg)

    def test_output_references_in_outputs_field(self):
        """
        Test that output references work in outputs field.
        @athena: b0ed86fa55ca
        """
        with TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            recipe_path = tmpdir / "tasktree.yaml"
            recipe_path.write_text("""
tasks:
  generate:
    outputs:
      - id_file: "gen/build-id.txt"
    cmd: |
      mkdir -p gen
      echo "12345" > gen/build-id.txt

  build:
    deps: [generate]
    outputs:
      - artifact: "dist/app-build.tar.gz"
    cmd: |
      mkdir -p dist
      # Use dependency output in command
      ID=$(cat {{ dep.generate.outputs.id_file }})
      echo "artifact-$ID" > dist/app-build.tar.gz
      # Verify the template was resolved correctly in cmd
      echo "Using ID from: {{ dep.generate.outputs.id_file }}" >> dist/app-build.tar.gz
""")

            os.chdir(tmpdir)
            result = self.runner.invoke(app, ["build"])

            self.assertEqual(result.exit_code, 0, result.stdout)

            # Verify the dependency output was used correctly in the command
            artifact = tmpdir / "dist/app-build.tar.gz"
            self.assertTrue(artifact.exists())

            content = artifact.read_text()
            self.assertIn("artifact-12345", content)
            self.assertIn("Using ID from: gen/build-id.txt", content)

    def test_backward_compatibility_anonymous_outputs(self):
        """
        Test that existing anonymous outputs still work.
        @athena: 99fb7c088df2
        """
        with TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            recipe_path = tmpdir / "tasktree.yaml"
            recipe_path.write_text("""
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
""")

            os.chdir(tmpdir)
            result = self.runner.invoke(app, ["deploy"])

            self.assertEqual(result.exit_code, 0, result.stdout)

            # Verify files were created (proof that anonymous outputs still work)
            self.assertTrue((tmpdir / "dist/bundle.js").exists())
            self.assertTrue((tmpdir / "dist/bundle.css").exists())

            # Verify content
            self.assertEqual("js", (tmpdir / "dist/bundle.js").read_text().strip())
            self.assertEqual("css", (tmpdir / "dist/bundle.css").read_text().strip())


if __name__ == "__main__":
    unittest.main()
