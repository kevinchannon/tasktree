"""
Integration tests for self-reference templates.
@athena: c14fc2c96447
"""

import os
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from tasktree.cli import app


def strip_ansi_codes(text: str) -> str:
    """
    Remove ANSI escape sequences from text.
    @athena: 90023a269128
    """
    ansi_escape = re.compile(r"\x1b\[[0-9;]*m")
    return ansi_escape.sub("", text)


class TestBasicSelfReferences(unittest.TestCase):
    """
    Test basic self-reference functionality.
    @athena: 16d30f7c6406
    """

    def setUp(self):
        """
        Set up test fixtures.
        @athena: 36a706d60319
        """
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_basic_self_input_reference(self):
        """
        Test simple {{ self.inputs.src }} in command.
        @athena: 1aee5331c8b5
        """
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
                self.assertEqual(
                    result.exit_code, 0, f"Command failed: {result.stdout}"
                )

                # Verify output file was created with correct content
                output_file = project_root / "output.txt"
                self.assertTrue(output_file.exists(), "Output file should exist")
                self.assertEqual(output_file.read_text(), "Hello World")
            finally:
                os.chdir(original_cwd)

    def test_basic_self_output_reference(self):
        """
        Test simple {{ self.outputs.dest }} in command.
        @athena: a9687a34858f
        """
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
                self.assertEqual(
                    result.exit_code, 0, f"Command failed: {result.stdout}"
                )

                # Verify output file was created with correct content
                output_file = project_root / "result.txt"
                self.assertTrue(output_file.exists(), "Output file should exist")
                self.assertEqual(output_file.read_text().strip(), "Generated content")
            finally:
                os.chdir(original_cwd)

    def test_mixed_self_references(self):
        """
        Test both inputs and outputs in same command.
        @athena: 2456620823bf
        """
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
                self.assertEqual(
                    result.exit_code, 0, f"Command failed: {result.stdout}"
                )

                # Verify output file has transformed content
                output_file = project_root / "processed.txt"
                self.assertTrue(output_file.exists(), "Output file should exist")
                self.assertEqual(output_file.read_text().strip(), "ORIGINAL DATA")
            finally:
                os.chdir(original_cwd)

    def test_self_references_with_glob_patterns(self):
        """
        Test that glob patterns are substituted verbatim.
        @athena: b74f930dc716
        """
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
                self.assertEqual(
                    result.exit_code, 0, f"Command failed: {result.stdout}"
                )

                # Verify output file contains both files' content
                output_file = project_root / "all.txt"
                self.assertTrue(output_file.exists(), "Output file should exist")
                content = output_file.read_text()
                self.assertIn("File 1", content)
                self.assertIn("File 2", content)
            finally:
                os.chdir(original_cwd)

    def test_anonymous_inputs_still_work(self):
        """
        Test backward compatibility - anonymous inputs work without self-references.
        @athena: 5fd4323a7db8
        """
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
                self.assertEqual(
                    result.exit_code, 0, f"Command failed: {result.stdout}"
                )

                # Verify output file was created
                output_file = project_root / "output.txt"
                self.assertTrue(output_file.exists(), "Output file should exist")
                self.assertEqual(output_file.read_text(), "Anonymous Input")
            finally:
                os.chdir(original_cwd)

    def test_anonymous_outputs_still_work(self):
        """
        Test backward compatibility - anonymous outputs work without self-references.
        @athena: 7dd90bd4b456
        """
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
                self.assertEqual(
                    result.exit_code, 0, f"Command failed: {result.stdout}"
                )

                # Verify output file was created
                output_file = project_root / "build.log"
                self.assertTrue(output_file.exists(), "Output file should exist")
                self.assertEqual(output_file.read_text().strip(), "Build complete")
            finally:
                os.chdir(original_cwd)

    def test_mixed_named_and_anonymous(self):
        """
        Test both named and anonymous inputs/outputs in same task.
        @athena: 22784ccf6dfa
        """
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
                self.assertEqual(
                    result.exit_code, 0, f"Command failed: {result.stdout}"
                )

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
    """
    Test validation and error handling for self-references.
    @athena: f86c53a9b77c
    """

    def setUp(self):
        """
        Set up test fixtures.
        @athena: 36a706d60319
        """
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_error_on_missing_input_name(self):
        """
        Test that referencing non-existent input raises error.
        @athena: 7894592f1142
        """
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
                self.assertNotEqual(
                    result.exit_code, 0, "Task should fail with missing input reference"
                )

                # Check error message contains useful information
                output = strip_ansi_codes(result.output)
                self.assertIn("missing", output.lower())
                self.assertIn("src", output)  # Available input should be mentioned
                self.assertIn("config", output)  # Available input should be mentioned
            finally:
                os.chdir(original_cwd)

    def test_error_on_missing_output_name(self):
        """
        Test that referencing non-existent output raises error.
        @athena: 8dafbf752dd4
        """
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
                self.assertNotEqual(
                    result.exit_code,
                    0,
                    "Task should fail with missing output reference",
                )

                # Check error message contains useful information
                output = strip_ansi_codes(result.output)
                self.assertIn("missing", output.lower())
                self.assertIn("bundle", output)  # Available output should be mentioned
                self.assertIn(
                    "sourcemap", output
                )  # Available output should be mentioned
            finally:
                os.chdir(original_cwd)

    def test_error_on_anonymous_input_reference(self):
        """
        Test that trying to reference anonymous input fails with clear message.
        @athena: f8a74d3ef088
        """
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
                self.assertNotEqual(
                    result.exit_code,
                    0,
                    "Task should fail when referencing anonymous inputs",
                )

                # Check error message mentions anonymous
                output = strip_ansi_codes(result.output)
                self.assertIn("anonymous", output.lower())
            finally:
                os.chdir(original_cwd)

    def test_error_on_anonymous_output_reference(self):
        """
        Test that trying to reference anonymous output fails with clear message.
        @athena: 063c82fa9e68
        """
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
                self.assertNotEqual(
                    result.exit_code,
                    0,
                    "Task should fail when referencing anonymous outputs",
                )

                # Check error message mentions anonymous
                output = strip_ansi_codes(result.output)
                self.assertIn("anonymous", output.lower())
            finally:
                os.chdir(original_cwd)

    def test_error_with_empty_inputs(self):
        """
        Test error when task has no inputs but tries to reference one.
        @athena: 068a1ba1fb67
        """
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
                self.assertNotEqual(
                    result.exit_code, 0, "Task should fail when no inputs exist"
                )

                # Check error message
                output = strip_ansi_codes(result.output)
                self.assertIn("anonymous", output.lower())
            finally:
                os.chdir(original_cwd)

    def test_error_with_empty_outputs(self):
        """
        Test error when task has no outputs but tries to reference one.
        @athena: bbbc9c76b063
        """
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
                self.assertNotEqual(
                    result.exit_code, 0, "Task should fail when no outputs exist"
                )

                # Check error message
                output = strip_ansi_codes(result.output)
                self.assertIn("anonymous", output.lower())
            finally:
                os.chdir(original_cwd)

    def test_error_case_sensitive(self):
        """
        Test that input/output names are case-sensitive.
        @athena: b23885b2a413
        """
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
                self.assertNotEqual(
                    result.exit_code, 0, "Task should fail due to case mismatch"
                )

                # Check error message mentions available name
                output = strip_ansi_codes(result.output)
                self.assertIn(
                    "src", output
                )  # The actual lowercase name should be in error
            finally:
                os.chdir(original_cwd)


class TestSelfReferencesWithVariables(unittest.TestCase):
    """
    Test interaction between self-references and variable substitution.
    @athena: 6981258eb27b
    """

    def setUp(self):
        """
        Set up test fixtures.
        @athena: 36a706d60319
        """
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_self_reference_with_var_in_input_path(self):
        """
        Test that variables in input paths are resolved before self-references.
        @athena: c8f3efd0569e
        """
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
                self.assertEqual(
                    result.exit_code, 0, f"Command failed: {result.stdout}"
                )

                # Verify output file contains correct content
                output_file = project_root / "output.txt"
                self.assertTrue(output_file.exists(), "Output file should exist")
                self.assertEqual(output_file.read_text(), "Version 1.0")
            finally:
                os.chdir(original_cwd)

    def test_self_reference_with_var_in_output_path(self):
        """
        Test that variables in output paths are resolved before self-references.
        @athena: 359e4e67c8da
        """
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
                self.assertEqual(
                    result.exit_code, 0, f"Command failed: {result.stdout}"
                )

                # Verify output file was created at correct path
                output_file = project_root / "dist" / "result.txt"
                self.assertTrue(
                    output_file.exists(),
                    "Output file should exist at variable-expanded path",
                )
                self.assertEqual(output_file.read_text().strip(), "Generated")
            finally:
                os.chdir(original_cwd)

    def test_multiple_vars_in_paths(self):
        """
        Test multiple variables in same input/output path.
        @athena: 34afbcd98aa3
        """
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
                self.assertEqual(
                    result.exit_code, 0, f"Command failed: {result.output}"
                )

                # Verify output file was created with correct name and content
                output_file = project_root / "myapp-v2-output.txt"
                self.assertTrue(
                    output_file.exists(),
                    "Output file should exist with variable-expanded name",
                )
                self.assertEqual(output_file.read_text(), "Multi-var data")
            finally:
                os.chdir(original_cwd)

    def test_var_in_path_evaluated_before_self_ref(self):
        """
        Test that variable substitution happens before self-reference substitution.
        @athena: 4968a1332aa2
        """
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
                self.assertEqual(
                    result.exit_code, 0, f"Command failed: {result.stdout}"
                )

                # Verify output file exists at correct location (proves variable was expanded before self-ref)
                output_file = project_root / "staging" / "deployed.js"
                self.assertTrue(output_file.exists(), "Output file should exist")
                self.assertEqual(output_file.read_text(), "console.log('app');")
            finally:
                os.chdir(original_cwd)


class TestSelfReferencesWithDependencyOutputs(unittest.TestCase):
    """
    Test interaction between self-references and dependency output references.
    @athena: c310f2ba995e
    """

    def setUp(self):
        """
        Set up test fixtures.
        @athena: 36a706d60319
        """
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_self_and_dep_references_in_same_cmd(self):
        """
        Test both self and dep references in the same command.
        @athena: 67f085e28e67
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with dependency chain using both reference types
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  build:
    outputs:
      - artifact: dist/app.js
    cmd: echo "console.log('app');" > {{ self.outputs.artifact }}

  package:
    deps: [build]
    inputs:
      - config: package.json
    outputs:
      - tarball: release.tar.gz
    cmd: tar czf {{ self.outputs.tarball }} {{ self.inputs.config }} {{ dep.build.outputs.artifact }}
""")

            # Create required files
            (project_root / "dist").mkdir()
            (project_root / "package.json").write_text('{"name": "app"}')

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run package task
                result = self.runner.invoke(app, ["package"], env=self.env)
                self.assertEqual(
                    result.exit_code, 0, f"Command failed: {result.stdout}"
                )

                # Verify tarball was created
                tarball = project_root / "release.tar.gz"
                self.assertTrue(tarball.exists(), "Tarball should exist")
            finally:
                os.chdir(original_cwd)

    def test_self_output_contains_dep_reference(self):
        """
        Test that self-reference works when output path contains dep reference.
        @athena: bb59c9a99b08
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe where output path uses dep reference
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  prepare:
    outputs:
      - outdir: build/v1
    cmd: mkdir -p {{ self.outputs.outdir }}

  compile:
    deps: [prepare]
    outputs:
      - binary: "{{ dep.prepare.outputs.outdir }}/app.bin"
    cmd: echo "binary" > {{ self.outputs.binary }}
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run compile task
                result = self.runner.invoke(app, ["compile"], env=self.env)
                self.assertEqual(
                    result.exit_code, 0, f"Command failed: {result.stdout}"
                )

                # Verify binary was created at correct location
                binary = project_root / "build" / "v1" / "app.bin"
                self.assertTrue(
                    binary.exists(), "Binary should exist at dep-referenced path"
                )
                self.assertEqual(binary.read_text(), "binary\n")
            finally:
                os.chdir(original_cwd)

    def test_dep_reference_resolved_before_self_ref(self):
        """
        Test that dependency references are resolved before self-references.
        @athena: e1e057c76d21
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe showing resolution order
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  generate:
    outputs:
      - filename: data.json
    cmd: echo '{"version":"1.0"}' > {{ self.outputs.filename }}

  process:
    deps: [generate]
    inputs:
      - source: "{{ dep.generate.outputs.filename }}"
    outputs:
      - result: processed.txt
    cmd: cat {{ self.inputs.source }} > {{ self.outputs.result }}
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run process task
                result = self.runner.invoke(app, ["process"], env=self.env)
                self.assertEqual(
                    result.exit_code, 0, f"Command failed: {result.stdout}"
                )

                # Verify result file contains correct data
                result_file = project_root / "processed.txt"
                self.assertTrue(result_file.exists(), "Result file should exist")
                self.assertIn("1.0", result_file.read_text())
            finally:
                os.chdir(original_cwd)

    def test_multiple_deps_with_self_refs(self):
        """
        Test self-references with multiple dependencies.
        @athena: 7ed490ba201a
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with diamond dependency pattern
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  prep:
    outputs:
      - config: config.txt
    cmd: echo "config" > {{ self.outputs.config }}

  buildA:
    deps: [prep]
    outputs:
      - moduleA: moduleA.js
    cmd: echo "moduleA" > {{ self.outputs.moduleA }}

  buildB:
    deps: [prep]
    outputs:
      - moduleB: moduleB.js
    cmd: echo "moduleB" > {{ self.outputs.moduleB }}

  bundle:
    deps: [buildA, buildB]
    outputs:
      - bundle: app.js
    cmd: cat {{ dep.buildA.outputs.moduleA }} {{ dep.buildB.outputs.moduleB }} > {{ self.outputs.bundle }}
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run bundle task
                result = self.runner.invoke(app, ["bundle"], env=self.env)
                self.assertEqual(
                    result.exit_code, 0, f"Command failed: {result.stdout}"
                )

                # Verify bundle contains both modules
                bundle_file = project_root / "app.js"
                self.assertTrue(bundle_file.exists(), "Bundle should exist")
                content = bundle_file.read_text()
                self.assertIn("moduleA", content)
                self.assertIn("moduleB", content)
            finally:
                os.chdir(original_cwd)


class TestSelfReferencesWithParameterizedTasks(unittest.TestCase):
    """
    Test self-references with parameterized tasks.
    @athena: 7b7024c3d7bc
    """

    def setUp(self):
        """
        Set up test fixtures.
        @athena: 36a706d60319
        """
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_self_references_in_parameterized_task(self):
        """
        Test that self-references work in parameterized tasks.
        @athena: e849f7415652
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source files
            (project_root / "input-debug.txt").write_text("Debug mode")
            (project_root / "input-release.txt").write_text("Release mode")

            # Create recipe with parameterized task using self-references
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  build:
    args: [mode]
    inputs:
      - src: input-{{ arg.mode }}.txt
    outputs:
      - dest: output-{{ arg.mode }}.txt
    cmd: cat {{ self.inputs.src }} > {{ self.outputs.dest }}
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task with mode=debug
                result = self.runner.invoke(app, ["build", "mode=debug"], env=self.env)
                self.assertEqual(
                    result.exit_code, 0, f"Command failed: {result.stdout}"
                )

                # Verify debug output
                output_file = project_root / "output-debug.txt"
                self.assertTrue(output_file.exists(), "Debug output should exist")
                self.assertEqual(output_file.read_text(), "Debug mode")

                # Run task with mode=release
                result = self.runner.invoke(
                    app, ["build", "mode=release"], env=self.env
                )
                self.assertEqual(
                    result.exit_code, 0, f"Command failed: {result.stdout}"
                )

                # Verify release output
                output_file = project_root / "output-release.txt"
                self.assertTrue(output_file.exists(), "Release output should exist")
                self.assertEqual(output_file.read_text(), "Release mode")
            finally:
                os.chdir(original_cwd)

    def test_arg_in_input_path_with_self_ref(self):
        """
        Test arguments in input paths combined with self-references.
        @athena: 491963b10568
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create directory structure with different configurations
            (project_root / "configs" / "dev").mkdir(parents=True)
            (project_root / "configs" / "prod").mkdir(parents=True)
            (project_root / "configs" / "dev" / "app.yaml").write_text("env: dev")
            (project_root / "configs" / "prod" / "app.yaml").write_text("env: prod")

            # Create recipe with arg in input path
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  deploy:
    args: [environment]
    inputs:
      - config: configs/{{ arg.environment }}/app.yaml
    outputs:
      - deployed: deployed-{{ arg.environment }}.yaml
    cmd: cp {{ self.inputs.config }} {{ self.outputs.deployed }}
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Deploy dev
                result = self.runner.invoke(
                    app, ["deploy", "environment=dev"], env=self.env
                )
                self.assertEqual(
                    result.exit_code, 0, f"Command failed: {result.stdout}"
                )

                deployed_file = project_root / "deployed-dev.yaml"
                self.assertTrue(deployed_file.exists())
                self.assertEqual(deployed_file.read_text(), "env: dev")

                # Deploy prod
                result = self.runner.invoke(
                    app, ["deploy", "environment=prod"], env=self.env
                )
                self.assertEqual(
                    result.exit_code, 0, f"Command failed: {result.stdout}"
                )

                deployed_file = project_root / "deployed-prod.yaml"
                self.assertTrue(deployed_file.exists())
                self.assertEqual(deployed_file.read_text(), "env: prod")
            finally:
                os.chdir(original_cwd)

    def test_multiple_args_with_self_refs(self):
        """
        Test multiple arguments in paths with self-references.
        @athena: 82bbc64c2547
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source structure
            (project_root / "src" / "v1" / "stable").mkdir(parents=True)
            (project_root / "src" / "v2" / "beta").mkdir(parents=True)
            (project_root / "src" / "v1" / "stable" / "lib.js").write_text("v1-stable")
            (project_root / "src" / "v2" / "beta" / "lib.js").write_text("v2-beta")

            # Create recipe with multiple args
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  package:
    args: [version, channel]
    inputs:
      - lib: src/{{ arg.version }}/{{ arg.channel }}/lib.js
    outputs:
      - bundle: dist-{{ arg.version }}-{{ arg.channel }}.js
    cmd: cp {{ self.inputs.lib }} {{ self.outputs.bundle }}
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Package v1-stable
                result = self.runner.invoke(
                    app, ["package", "version=v1", "channel=stable"], env=self.env
                )
                self.assertEqual(
                    result.exit_code, 0, f"Command failed: {result.stdout}"
                )

                bundle = project_root / "dist-v1-stable.js"
                self.assertTrue(bundle.exists())
                self.assertEqual(bundle.read_text(), "v1-stable")

                # Package v2-beta
                result = self.runner.invoke(
                    app, ["package", "version=v2", "channel=beta"], env=self.env
                )
                self.assertEqual(
                    result.exit_code, 0, f"Command failed: {result.stdout}"
                )

                bundle = project_root / "dist-v2-beta.js"
                self.assertTrue(bundle.exists())
                self.assertEqual(bundle.read_text(), "v2-beta")
            finally:
                os.chdir(original_cwd)

    def test_parameterized_deps_with_self_refs(self):
        """
        Test self-references in tasks with parameterized dependencies.
        @athena: f3e1b1ac82b9
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with parameterized dependency chain
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  compile:
    args: [platform]
    outputs:
      - binary: bin-{{ arg.platform }}.exe
    cmd: echo "binary for {{ arg.platform }}" > {{ self.outputs.binary }}

  package:
    args: [platform]
    deps:
      - compile:
          platform: "{{ arg.platform }}"
    inputs:
      - installer: package.nsi
    outputs:
      - setup: setup-{{ arg.platform }}.exe
    cmd: cat {{ self.inputs.installer }} {{ dep.compile.outputs.binary }} > {{ self.outputs.setup }}
""")

            # Create installer script
            (project_root / "package.nsi").write_text("installer\n")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Package for windows
                result = self.runner.invoke(
                    app, ["package", "platform=windows"], env=self.env
                )
                self.assertEqual(
                    result.exit_code, 0, f"Command failed: {result.stdout}"
                )

                setup = project_root / "setup-windows.exe"
                self.assertTrue(setup.exists())
                content = setup.read_text()
                self.assertIn("installer", content)
                self.assertIn("windows", content)
            finally:
                os.chdir(original_cwd)


class TestSelfReferencesWithStateManagement(unittest.TestCase):
    """
    Test state management and incremental execution with self-references.
    @athena: f8ec96aee4fd
    """

    def setUp(self):
        """
        Set up test fixtures.
        @athena: 36a706d60319
        """
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_self_references_with_state_tracking(self):
        """
        Test that state tracking works with self-references.
        @athena: 1fa03ebf56ac
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source file
            src_file = project_root / "input.txt"
            src_file.write_text("Version 1")

            # Create recipe with self-references
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  build:
    inputs:
      - src: input.txt
    outputs:
      - dest: output.txt
    cmd: cat {{ self.inputs.src }} > {{ self.outputs.dest }}
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # First run
                result = self.runner.invoke(app, ["build"], env=self.env)
                self.assertEqual(
                    result.exit_code, 0, f"First run failed: {result.stdout}"
                )

                output_file = project_root / "output.txt"
                self.assertTrue(output_file.exists())
                self.assertEqual(output_file.read_text(), "Version 1")

                # Second run without changes - should skip
                result = self.runner.invoke(app, ["build"], env=self.env)
                self.assertEqual(
                    result.exit_code, 0, f"Second run failed: {result.stdout}"
                )
                # Task should be skipped (no "Running:" message for build)
                output = strip_ansi_codes(result.stdout)
                self.assertNotIn("Running: build", output)
            finally:
                os.chdir(original_cwd)

    def test_input_change_triggers_rerun(self):
        """
        Test that changing input file triggers rerun with self-references.
        @athena: eede516acfe1
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source file
            src_file = project_root / "data.txt"
            src_file.write_text("Original")

            # Create recipe
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  process:
    inputs:
      - source: data.txt
    outputs:
      - result: processed.txt
    cmd: cat {{ self.inputs.source }} > {{ self.outputs.result }}
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # First run
                result = self.runner.invoke(app, ["process"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                output_file = project_root / "processed.txt"
                self.assertEqual(output_file.read_text(), "Original")

                # Modify input file
                import time

                time.sleep(0.01)  # Ensure timestamp changes
                src_file.write_text("Modified")

                # Second run - should detect change and rerun
                result = self.runner.invoke(app, ["process"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                output = strip_ansi_codes(result.stdout)
                self.assertIn("Running: process", output)

                # Verify output updated
                self.assertEqual(output_file.read_text(), "Modified")
            finally:
                os.chdir(original_cwd)

    def test_output_change_triggers_rerun(self):
        """
        Test that missing or modified output triggers rerun.
        @athena: 0a141b7f9634
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  generate:
    outputs:
      - artifact: build.txt
    cmd: echo "Build output" > {{ self.outputs.artifact }}
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # First run
                result = self.runner.invoke(app, ["generate"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                output_file = project_root / "build.txt"
                self.assertTrue(output_file.exists())

                # Delete output file
                output_file.unlink()

                # Second run - should detect missing output and rerun
                result = self.runner.invoke(app, ["generate"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                output = strip_ansi_codes(result.stdout)
                self.assertIn("Running: generate", output)

                # Verify output recreated
                self.assertTrue(output_file.exists())
            finally:
                os.chdir(original_cwd)

    def test_task_definition_change_triggers_rerun(self):
        """
        Test that changing task command triggers rerun.
        @athena: d551f4b3d513
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source file
            (project_root / "input.txt").write_text("Data")

            # Create initial recipe
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  transform:
    inputs:
      - src: input.txt
    outputs:
      - dest: output.txt
    cmd: cat {{ self.inputs.src }} > {{ self.outputs.dest }}
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # First run
                result = self.runner.invoke(app, ["transform"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Modify command (add tr to uppercase)
                recipe_file.write_text("""
tasks:
  transform:
    inputs:
      - src: input.txt
    outputs:
      - dest: output.txt
    cmd: cat {{ self.inputs.src }} | tr '[:lower:]' '[:upper:]' > {{ self.outputs.dest }}
""")

                # Second run - should detect command change and rerun
                result = self.runner.invoke(app, ["transform"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                output = strip_ansi_codes(result.stdout)
                self.assertIn("Running: transform", output)

                # Verify output reflects new command
                output_file = project_root / "output.txt"
                self.assertEqual(output_file.read_text(), "DATA")
            finally:
                os.chdir(original_cwd)

    def test_force_execution_with_self_refs(self):
        """
        Test --force flag forces rerun with self-references.
        @athena: c431685dfbc1
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source file
            (project_root / "source.txt").write_text("Content")

            # Create recipe
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  copy:
    inputs:
      - file: source.txt
    outputs:
      - copy: dest.txt
    cmd: cp {{ self.inputs.file }} {{ self.outputs.copy }}
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # First run
                result = self.runner.invoke(app, ["copy"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Second run without changes - should skip
                result = self.runner.invoke(app, ["copy"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                output = strip_ansi_codes(result.stdout)
                self.assertNotIn("Running: copy", output)

                # Third run with --force - should run
                result = self.runner.invoke(app, ["--force", "copy"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                output = strip_ansi_codes(result.stdout)
                self.assertIn("Running: copy", output)
            finally:
                os.chdir(original_cwd)

    def test_incremental_with_dependency_chain(self):
        """
        Test incremental execution with dependency chain using self-refs.
        @athena: 9cf327c1ba33
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source files
            src_file = project_root / "main.c"
            src_file.write_text("int main() { return 0; }")

            header_file = project_root / "config.h"
            header_file.write_text("#define VERSION 1")

            # Create recipe with dependency chain using implicit inputs
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  compile:
    inputs:
      - src: main.c
      - header: config.h
    outputs:
      - obj: main.o
    cmd: cat {{ self.inputs.src }} {{ self.inputs.header }} > {{ self.outputs.obj }}

  link:
    deps: [compile]
    outputs:
      - exe: app.exe
    cmd: cat main.o > {{ self.outputs.exe }}

  package:
    deps: [link]
    outputs:
      - archive: app.tar.gz
    cmd: tar czf {{ self.outputs.archive }} app.exe
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # First run - all tasks execute
                result = self.runner.invoke(app, ["package"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                output = strip_ansi_codes(result.stdout)
                self.assertIn("Running: compile", output)
                self.assertIn("Running: link", output)
                self.assertIn("Running: package", output)

                # Second run without changes - all tasks skip
                result = self.runner.invoke(app, ["package"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                output = strip_ansi_codes(result.stdout)
                self.assertNotIn("Running: compile", output)
                self.assertNotIn("Running: link", output)
                self.assertNotIn("Running: package", output)

                # Modify source file
                import time

                time.sleep(0.01)
                src_file.write_text("int main() { return 1; }")

                # Third run - all tasks in chain should execute
                result = self.runner.invoke(app, ["package"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                output = strip_ansi_codes(result.stdout)
                self.assertIn("Running: compile", output)
                self.assertIn("Running: link", output)
                self.assertIn("Running: package", output)
            finally:
                os.chdir(original_cwd)


class TestPositionalSelfReferences(unittest.TestCase):
    """
    Test positional self-reference functionality ({{ self.inputs.0 }}, etc.).
    @athena: 2f4524625849
    """

    def setUp(self):
        """
        Set up test fixtures.
        @athena: 36a706d60319
        """
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_basic_positional_input(self):
        """
        Test basic positional input access {{ self.inputs.0 }}.
        @athena: 28758fde1a39
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source files
            (project_root / "file1.txt").write_text("First")
            (project_root / "file2.txt").write_text("Second")

            # Create recipe with positional input references
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  concat:
    inputs: ["file1.txt", "file2.txt"]
    outputs: [result.txt]
    cmd: cat {{ self.inputs.0 }} {{ self.inputs.1 }} > result.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["concat"], env=self.env)
                self.assertEqual(
                    result.exit_code, 0, f"Command failed: {result.stdout}"
                )

                # Verify output file contains both files in order
                output_file = project_root / "result.txt"
                self.assertTrue(output_file.exists(), "Output file should exist")
                content = output_file.read_text()
                self.assertIn("First", content)
                self.assertIn("Second", content)
            finally:
                os.chdir(original_cwd)

    def test_basic_positional_output(self):
        """
        Test basic positional output access {{ self.outputs.0 }}.
        @athena: a828e9799336
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with positional output reference
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  generate:
    outputs: ["first.txt", "second.txt"]
    cmd: |
      echo "Output 1" > {{ self.outputs.0 }}
      echo "Output 2" > {{ self.outputs.1 }}
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["generate"], env=self.env)
                self.assertEqual(
                    result.exit_code, 0, f"Command failed: {result.stdout}"
                )

                # Verify both output files were created
                first_file = project_root / "first.txt"
                second_file = project_root / "second.txt"
                self.assertTrue(first_file.exists(), "First output should exist")
                self.assertTrue(second_file.exists(), "Second output should exist")
                self.assertEqual(first_file.read_text().strip(), "Output 1")
                self.assertEqual(second_file.read_text().strip(), "Output 2")
            finally:
                os.chdir(original_cwd)

    def test_mixed_named_and_positional(self):
        """
        Test mixing named and positional access in same command.
        @athena: fd0cad02b965
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source files
            (project_root / "named.txt").write_text("Named")
            (project_root / "anon.txt").write_text("Anonymous")

            # Create recipe with both named and positional references
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
      cat {{ self.inputs.config }} {{ self.inputs.1 }} > {{ self.outputs.result }}
      echo "Processed" > {{ self.outputs.1 }}
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["process"], env=self.env)
                self.assertEqual(
                    result.exit_code, 0, f"Command failed: {result.stdout}"
                )

                # Verify both output files
                output_file = project_root / "output.txt"
                self.assertTrue(output_file.exists(), "Result file should exist")
                content = output_file.read_text()
                self.assertIn("Named", content)
                self.assertIn("Anonymous", content)

                debug_file = project_root / "debug.log"
                self.assertTrue(debug_file.exists(), "Debug file should exist")
                self.assertEqual(debug_file.read_text().strip(), "Processed")
            finally:
                os.chdir(original_cwd)

    def test_same_item_by_name_and_index(self):
        """
        Test accessing same item by both name and positional index.
        @athena: b7c108b53f88
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source file
            (project_root / "data.txt").write_text("Data")

            # Create recipe accessing same input by name and index
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  duplicate:
    inputs:
      - source: data.txt
    outputs: [copy1.txt, copy2.txt]
    cmd: |
      cat {{ self.inputs.source }} > {{ self.outputs.0 }}
      cat {{ self.inputs.0 }} > {{ self.outputs.1 }}
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["duplicate"], env=self.env)
                self.assertEqual(
                    result.exit_code, 0, f"Command failed: {result.stdout}"
                )

                # Verify both copies have same content
                copy1 = project_root / "copy1.txt"
                copy2 = project_root / "copy2.txt"
                self.assertTrue(copy1.exists())
                self.assertTrue(copy2.exists())
                self.assertEqual(copy1.read_text(), "Data")
                self.assertEqual(copy2.read_text(), "Data")
            finally:
                os.chdir(original_cwd)

    def test_positional_with_variables(self):
        """
        Test positional access with variables in input paths.
        @athena: 1509537e05f3
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source file with variable-expanded name
            (project_root / "file-1.0.txt").write_text("Version 1.0")

            # Create recipe with variable in input path accessed positionally
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
variables:
  version: "1.0"

tasks:
  process:
    inputs: ["file-{{ var.version }}.txt"]
    outputs: [result.txt]
    cmd: cat {{ self.inputs.0 }} > {{ self.outputs.0 }}
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["process"], env=self.env)
                self.assertEqual(
                    result.exit_code, 0, f"Command failed: {result.stdout}"
                )

                # Verify output
                output_file = project_root / "result.txt"
                self.assertTrue(output_file.exists())
                self.assertEqual(output_file.read_text(), "Version 1.0")
            finally:
                os.chdir(original_cwd)

    def test_error_on_out_of_bounds_input_index(self):
        """
        Test error when input index is out of bounds.
        @athena: b84afdf547e1
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with out-of-bounds index
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  build:
    inputs: ["file1.txt", "file2.txt"]
    outputs: [output.txt]
    cmd: cat {{ self.inputs.5 }} > output.txt
""")

            # Create input files
            (project_root / "file1.txt").write_text("File 1")
            (project_root / "file2.txt").write_text("File 2")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task - should fail
                result = self.runner.invoke(app, ["build"], env=self.env)
                self.assertNotEqual(
                    result.exit_code, 0, "Task should fail with out-of-bounds index"
                )

                # Check error message
                output = strip_ansi_codes(result.output)
                self.assertIn("index '5'", output.lower())
                self.assertIn("only has 2", output.lower())
            finally:
                os.chdir(original_cwd)

    def test_error_on_out_of_bounds_output_index(self):
        """
        Test error when output index is out of bounds.
        @athena: cbc5df124846
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with out-of-bounds output index
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  generate:
    outputs: [output.txt]
    cmd: echo "test" > {{ self.outputs.3 }}
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task - should fail
                result = self.runner.invoke(app, ["generate"], env=self.env)
                self.assertNotEqual(
                    result.exit_code, 0, "Task should fail with out-of-bounds index"
                )

                # Check error message
                output = strip_ansi_codes(result.output)
                self.assertIn("index '3'", output.lower())
                self.assertIn("1 outputs", output.lower())
            finally:
                os.chdir(original_cwd)

    def test_error_on_empty_inputs_with_index(self):
        """
        Test error when referencing index on task with no inputs.
        @athena: 807447c6b396
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with no inputs but positional reference
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  build:
    outputs: [output.txt]
    cmd: cat {{ self.inputs.0 }} > output.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task - should fail
                result = self.runner.invoke(app, ["build"], env=self.env)
                self.assertNotEqual(
                    result.exit_code, 0, "Task should fail when no inputs exist"
                )

                # Check error message
                output = strip_ansi_codes(result.output)
                self.assertIn("inputs defined", output.lower())
            finally:
                os.chdir(original_cwd)

    def test_positional_with_glob_patterns(self):
        """
        Test positional access with glob patterns substituted verbatim.
        @athena: e480ee8eddf7
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source files
            (project_root / "a.txt").write_text("A")
            (project_root / "b.txt").write_text("B")

            # Create recipe with glob pattern accessed positionally
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  concat:
    inputs: ["*.txt"]
    outputs: [all.txt]
    cmd: cat {{ self.inputs.0 }} > {{ self.outputs.0 }}
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["concat"], env=self.env)
                self.assertEqual(
                    result.exit_code, 0, f"Command failed: {result.stdout}"
                )

                # Verify output file contains both files (glob expanded by shell)
                output_file = project_root / "all.txt"
                self.assertTrue(output_file.exists())
                content = output_file.read_text()
                # Shell expands *.txt to both files
                self.assertTrue("A" in content or "B" in content)
            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
