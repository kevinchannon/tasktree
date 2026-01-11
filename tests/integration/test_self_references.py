"""Integration tests for self-reference templates."""

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


class TestBasicSelfReferences(unittest.TestCase):
    """Test basic self-reference functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_basic_self_input_reference(self):
        """Test simple {{ self.inputs.src }} in command."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source file
            src_file = project_root / "input.txt"
            src_file.write_text("Hello World")

            # Create recipe with self-reference to input
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  process:
    inputs:
      - src: input.txt
    outputs: [output.txt]
    cmd: cat {{ self.inputs.src }} > output.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["process"], env=self.env)
                self.assertEqual(result.exit_code, 0, f"Command failed: {result.stdout}")

                # Verify output file was created with correct content
                output_file = project_root / "output.txt"
                self.assertTrue(output_file.exists(), "Output file should exist")
                self.assertEqual(output_file.read_text(), "Hello World")
            finally:
                os.chdir(original_cwd)

    def test_basic_self_output_reference(self):
        """Test simple {{ self.outputs.dest }} in command."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with self-reference to output
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  generate:
    outputs:
      - dest: result.txt
    cmd: echo "Generated content" > {{ self.outputs.dest }}
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["generate"], env=self.env)
                self.assertEqual(result.exit_code, 0, f"Command failed: {result.stdout}")

                # Verify output file was created with correct content
                output_file = project_root / "result.txt"
                self.assertTrue(output_file.exists(), "Output file should exist")
                self.assertEqual(output_file.read_text().strip(), "Generated content")
            finally:
                os.chdir(original_cwd)

    def test_mixed_self_references(self):
        """Test both inputs and outputs in same command."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source file
            src_file = project_root / "data.txt"
            src_file.write_text("Original Data")

            # Create recipe with both input and output self-references
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  transform:
    inputs:
      - source: data.txt
    outputs:
      - target: processed.txt
    cmd: cat {{ self.inputs.source }} | tr '[:lower:]' '[:upper:]' > {{ self.outputs.target }}
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["transform"], env=self.env)
                self.assertEqual(result.exit_code, 0, f"Command failed: {result.stdout}")

                # Verify output file has transformed content
                output_file = project_root / "processed.txt"
                self.assertTrue(output_file.exists(), "Output file should exist")
                self.assertEqual(output_file.read_text().strip(), "ORIGINAL DATA")
            finally:
                os.chdir(original_cwd)

    def test_self_references_with_glob_patterns(self):
        """Test that glob patterns are substituted verbatim."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source files
            (project_root / "file1.txt").write_text("File 1")
            (project_root / "file2.txt").write_text("File 2")

            # Create recipe with glob pattern in input
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  concat:
    inputs:
      - sources: "*.txt"
    outputs:
      - combined: all.txt
    cmd: cat {{ self.inputs.sources }} > {{ self.outputs.combined }}
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["concat"], env=self.env)
                self.assertEqual(result.exit_code, 0, f"Command failed: {result.stdout}")

                # Verify output file contains both files' content
                output_file = project_root / "all.txt"
                self.assertTrue(output_file.exists(), "Output file should exist")
                content = output_file.read_text()
                self.assertIn("File 1", content)
                self.assertIn("File 2", content)
            finally:
                os.chdir(original_cwd)

    def test_anonymous_inputs_still_work(self):
        """Test backward compatibility - anonymous inputs work without self-references."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source file
            (project_root / "input.txt").write_text("Anonymous Input")

            # Create recipe with anonymous input (no self-reference)
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  copy:
    inputs: [input.txt]
    outputs: [output.txt]
    cmd: cp input.txt output.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["copy"], env=self.env)
                self.assertEqual(result.exit_code, 0, f"Command failed: {result.stdout}")

                # Verify output file was created
                output_file = project_root / "output.txt"
                self.assertTrue(output_file.exists(), "Output file should exist")
                self.assertEqual(output_file.read_text(), "Anonymous Input")
            finally:
                os.chdir(original_cwd)

    def test_anonymous_outputs_still_work(self):
        """Test backward compatibility - anonymous outputs work without self-references."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with anonymous output (no self-reference)
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  build:
    outputs: [build.log]
    cmd: echo "Build complete" > build.log
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["build"], env=self.env)
                self.assertEqual(result.exit_code, 0, f"Command failed: {result.stdout}")

                # Verify output file was created
                output_file = project_root / "build.log"
                self.assertTrue(output_file.exists(), "Output file should exist")
                self.assertEqual(output_file.read_text().strip(), "Build complete")
            finally:
                os.chdir(original_cwd)

    def test_mixed_named_and_anonymous(self):
        """Test both named and anonymous inputs/outputs in same task."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source files
            (project_root / "named.txt").write_text("Named")
            (project_root / "anon.txt").write_text("Anonymous")

            # Create recipe with mixed inputs/outputs
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  process:
    inputs:
      - config: named.txt
      - anon.txt
    outputs:
      - result: output.txt
      - debug.log
    cmd: |
      cat {{ self.inputs.config }} anon.txt > {{ self.outputs.result }}
      echo "Processed" > debug.log
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["process"], env=self.env)
                self.assertEqual(result.exit_code, 0, f"Command failed: {result.stdout}")

                # Verify both output files were created
                output_file = project_root / "output.txt"
                self.assertTrue(output_file.exists(), "Output file should exist")
                content = output_file.read_text()
                self.assertIn("Named", content)
                self.assertIn("Anonymous", content)

                debug_file = project_root / "debug.log"
                self.assertTrue(debug_file.exists(), "Debug file should exist")
                self.assertEqual(debug_file.read_text().strip(), "Processed")
            finally:
                os.chdir(original_cwd)


class TestSelfReferenceValidation(unittest.TestCase):
    """Test validation and error handling for self-references."""

    def setUp(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_error_on_missing_input_name(self):
        """Test that referencing non-existent input raises error."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with reference to non-existent input
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  build:
    inputs:
      - src: "file.txt"
      - config: "config.json"
    outputs: [output.txt]
    cmd: cat {{ self.inputs.missing }} > output.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task - should fail
                result = self.runner.invoke(app, ["build"], env=self.env)
                self.assertNotEqual(result.exit_code, 0, "Task should fail with missing input reference")

                # Check error message contains useful information
                output = strip_ansi_codes(result.stdout)
                self.assertIn("missing", output.lower())
                self.assertIn("src", output)  # Available input should be mentioned
                self.assertIn("config", output)  # Available input should be mentioned
            finally:
                os.chdir(original_cwd)

    def test_error_on_missing_output_name(self):
        """Test that referencing non-existent output raises error."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with reference to non-existent output
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  deploy:
    outputs:
      - bundle: dist/app.js
      - sourcemap: dist/app.js.map
    cmd: cat {{ self.outputs.missing }}
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task - should fail
                result = self.runner.invoke(app, ["deploy"], env=self.env)
                self.assertNotEqual(result.exit_code, 0, "Task should fail with missing output reference")

                # Check error message contains useful information
                output = strip_ansi_codes(result.stdout)
                self.assertIn("missing", output.lower())
                self.assertIn("bundle", output)  # Available output should be mentioned
                self.assertIn("sourcemap", output)  # Available output should be mentioned
            finally:
                os.chdir(original_cwd)

    def test_error_on_anonymous_input_reference(self):
        """Test that trying to reference anonymous input fails with clear message."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with only anonymous inputs
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  build:
    inputs: ["file.txt", "config.json"]
    outputs: [output.txt]
    cmd: cat {{ self.inputs.src }} > output.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task - should fail
                result = self.runner.invoke(app, ["build"], env=self.env)
                self.assertNotEqual(result.exit_code, 0, "Task should fail when referencing anonymous inputs")

                # Check error message mentions anonymous
                output = strip_ansi_codes(result.stdout)
                self.assertIn("anonymous", output.lower())
            finally:
                os.chdir(original_cwd)

    def test_error_on_anonymous_output_reference(self):
        """Test that trying to reference anonymous output fails with clear message."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with only anonymous outputs
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  build:
    outputs: [output.txt, debug.log]
    cmd: cat {{ self.outputs.dest }}
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task - should fail
                result = self.runner.invoke(app, ["build"], env=self.env)
                self.assertNotEqual(result.exit_code, 0, "Task should fail when referencing anonymous outputs")

                # Check error message mentions anonymous
                output = strip_ansi_codes(result.stdout)
                self.assertIn("anonymous", output.lower())
            finally:
                os.chdir(original_cwd)

    def test_error_with_empty_inputs(self):
        """Test error when task has no inputs but tries to reference one."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with no inputs
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  build:
    outputs: [output.txt]
    cmd: cat {{ self.inputs.src }} > output.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task - should fail
                result = self.runner.invoke(app, ["build"], env=self.env)
                self.assertNotEqual(result.exit_code, 0, "Task should fail when no inputs exist")

                # Check error message
                output = strip_ansi_codes(result.stdout)
                self.assertIn("anonymous", output.lower())
            finally:
                os.chdir(original_cwd)

    def test_error_with_empty_outputs(self):
        """Test error when task has no outputs but tries to reference one."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with no outputs
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  build:
    cmd: cat {{ self.outputs.dest }}
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task - should fail
                result = self.runner.invoke(app, ["build"], env=self.env)
                self.assertNotEqual(result.exit_code, 0, "Task should fail when no outputs exist")

                # Check error message
                output = strip_ansi_codes(result.stdout)
                self.assertIn("anonymous", output.lower())
            finally:
                os.chdir(original_cwd)

    def test_error_case_sensitive(self):
        """Test that input/output names are case-sensitive."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with lowercase input name
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  build:
    inputs:
      - src: "file.txt"
    outputs: [output.txt]
    cmd: cat {{ self.inputs.SRC }} > output.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task - should fail (SRC != src)
                result = self.runner.invoke(app, ["build"], env=self.env)
                self.assertNotEqual(result.exit_code, 0, "Task should fail due to case mismatch")

                # Check error message mentions available name
                output = strip_ansi_codes(result.stdout)
                self.assertIn("src", output)  # The actual lowercase name should be in error
            finally:
                os.chdir(original_cwd)


class TestSelfReferencesWithVariables(unittest.TestCase):
    """Test interaction between self-references and variable substitution."""

    def setUp(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_self_reference_with_var_in_input_path(self):
        """Test that variables in input paths are resolved before self-references."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source file matching the variable-expanded path
            (project_root / "src").mkdir()
            (project_root / "src" / "app-1.0.txt").write_text("Version 1.0")

            # Create recipe with variable in input path
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
variables:
  version: "1.0"

tasks:
  process:
    inputs:
      - src: "src/app-{{ var.version }}.txt"
    outputs:
      - dest: output.txt
    cmd: cat {{ self.inputs.src }} > {{ self.outputs.dest }}
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["process"], env=self.env)
                self.assertEqual(result.exit_code, 0, f"Command failed: {result.stdout}")

                # Verify output file contains correct content
                output_file = project_root / "output.txt"
                self.assertTrue(output_file.exists(), "Output file should exist")
                self.assertEqual(output_file.read_text(), "Version 1.0")
            finally:
                os.chdir(original_cwd)

    def test_self_reference_with_var_in_output_path(self):
        """Test that variables in output paths are resolved before self-references."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create output directory
            (project_root / "dist").mkdir()

            # Create recipe with variable in output path
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
variables:
  build_dir: "dist"

tasks:
  generate:
    outputs:
      - artifact: "{{ var.build_dir }}/result.txt"
    cmd: echo "Generated" > {{ self.outputs.artifact }}
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["generate"], env=self.env)
                self.assertEqual(result.exit_code, 0, f"Command failed: {result.stdout}")

                # Verify output file was created at correct path
                output_file = project_root / "dist" / "result.txt"
                self.assertTrue(output_file.exists(), "Output file should exist at variable-expanded path")
                self.assertEqual(output_file.read_text().strip(), "Generated")
            finally:
                os.chdir(original_cwd)

    def test_multiple_vars_in_paths(self):
        """Test multiple variables in same input/output path."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create directory structure with variable-expanded path
            (project_root / "projects" / "myapp" / "v2").mkdir(parents=True)
            src_file = project_root / "projects" / "myapp" / "v2" / "data.txt"
            src_file.write_text("Multi-var data")

            # Create recipe with multiple variables in paths
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
variables:
  project: "myapp"
  version: "2"

tasks:
  process:
    inputs:
      - data: "projects/{{ var.project }}/v{{ var.version }}/data.txt"
    outputs:
      - result: "{{ var.project }}-v{{ var.version }}-output.txt"
    cmd: cat {{ self.inputs.data }} > {{ self.outputs.result }}
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["process"], env=self.env)
                self.assertEqual(result.exit_code, 0, f"Command failed: {result.stdout}")

                # Verify output file was created with correct name and content
                output_file = project_root / "myapp-v2-output.txt"
                self.assertTrue(output_file.exists(), "Output file should exist with variable-expanded name")
                self.assertEqual(output_file.read_text(), "Multi-var data")
            finally:
                os.chdir(original_cwd)

    def test_var_in_path_evaluated_before_self_ref(self):
        """Test that variable substitution happens before self-reference substitution."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source file
            (project_root / "staging").mkdir()
            (project_root / "staging" / "app.js").write_text("console.log('app');")

            # Create recipe where self-ref depends on variable being evaluated first
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
variables:
  env: "staging"

tasks:
  deploy:
    inputs:
      - bundle: "{{ var.env }}/app.js"
    outputs:
      - deployed: "{{ var.env }}/deployed.js"
    cmd: |
      # Command uses self-refs which should contain variable-expanded paths
      echo "Deploying {{ self.inputs.bundle }}"
      cp {{ self.inputs.bundle }} {{ self.outputs.deployed }}
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["deploy"], env=self.env)
                self.assertEqual(result.exit_code, 0, f"Command failed: {result.stdout}")

                # Verify output file exists at correct location (proves variable was expanded before self-ref)
                output_file = project_root / "staging" / "deployed.js"
                self.assertTrue(output_file.exists(), "Output file should exist")
                self.assertEqual(output_file.read_text(), "console.log('app');")
            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
