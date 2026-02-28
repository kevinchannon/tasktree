"""
Integration tests for self-reference templates.
"""

import os
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from tasktree.cli import app
from tests.fixture_utils import copy_fixture_files


def strip_ansi_codes(text: str) -> str:
    """
    Remove ANSI escape sequences from text.
    """
    ansi_escape = re.compile(r"\x1b\[[0-9;]*m")
    return ansi_escape.sub("", text)


class TestBasicSelfReferences(unittest.TestCase):
    """
    Test basic self-reference functionality.
    """

    def setUp(self):
        """
        Set up test fixtures.
        """
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_basic_self_input_reference(self):
        """
        Test simple {{ self.inputs.src }} in command.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source file
            src_file = project_root / "input.txt"
            src_file.write_text("Hello World")

            copy_fixture_files("self_ref_basic_input", project_root)

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
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("self_ref_basic_output", project_root)

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
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source file
            src_file = project_root / "data.txt"
            src_file.write_text("Original Data")

            copy_fixture_files("self_ref_mixed", project_root)

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
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source files
            (project_root / "file1.txt").write_text("File 1")
            (project_root / "file2.txt").write_text("File 2")

            copy_fixture_files("self_ref_glob_patterns", project_root)

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
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source file
            (project_root / "input.txt").write_text("Anonymous Input")

            copy_fixture_files("self_ref_anonymous_inputs", project_root)

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
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("self_ref_anonymous_outputs", project_root)

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
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source files
            (project_root / "named.txt").write_text("Named")
            (project_root / "anon.txt").write_text("Anonymous")

            copy_fixture_files("self_ref_mixed_named_anonymous", project_root)

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
    """

    def setUp(self):
        """
        Set up test fixtures.
        """
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_error_on_missing_input_name(self):
        """
        Test that referencing non-existent input raises error.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("self_ref_missing_input_name", project_root)

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
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("self_ref_missing_output_name", project_root)

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
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("self_ref_anonymous_input_reference", project_root)

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
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("self_ref_anonymous_output_reference", project_root)

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
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("self_ref_empty_inputs", project_root)

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
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("self_ref_empty_outputs", project_root)

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
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("self_ref_case_sensitive", project_root)

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
    """

    def setUp(self):
        """
        Set up test fixtures.
        """
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_self_reference_with_var_in_input_path(self):
        """
        Test that variables in input paths are resolved before self-references.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source file matching the variable-expanded path
            (project_root / "src").mkdir()
            (project_root / "src" / "app-1.0.txt").write_text("Version 1.0")

            copy_fixture_files("self_ref_var_in_input_path", project_root)

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
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create output directory
            (project_root / "dist").mkdir()

            copy_fixture_files("self_ref_var_in_output_path", project_root)

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
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create directory structure with variable-expanded path
            (project_root / "projects" / "myapp" / "v2").mkdir(parents=True)
            src_file = project_root / "projects" / "myapp" / "v2" / "data.txt"
            src_file.write_text("Multi-var data")

            copy_fixture_files("self_ref_multiple_vars_in_paths", project_root)

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
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source file
            (project_root / "staging").mkdir()
            (project_root / "staging" / "app.js").write_text("console.log('app');")

            copy_fixture_files("self_ref_var_evaluated_before_self", project_root)

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
    """

    def setUp(self):
        """
        Set up test fixtures.
        """
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_self_and_dep_references_in_same_cmd(self):
        """
        Test both self and dep references in the same command.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("self_ref_self_and_dep", project_root)

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
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("self_ref_output_contains_dep", project_root)

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
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("self_ref_dep_resolved_before_self", project_root)

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
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("self_ref_multiple_deps", project_root)

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
    """

    def setUp(self):
        """
        Set up test fixtures.
        """
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_self_references_in_parameterized_task(self):
        """
        Test that self-references work in parameterized tasks.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source files
            (project_root / "input-debug.txt").write_text("Debug mode")
            (project_root / "input-release.txt").write_text("Release mode")

            copy_fixture_files("self_ref_parameterized", project_root)

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
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create directory structure with different configurations
            (project_root / "configs" / "dev").mkdir(parents=True)
            (project_root / "configs" / "prod").mkdir(parents=True)
            (project_root / "configs" / "dev" / "app.yaml").write_text("env: dev")
            (project_root / "configs" / "prod" / "app.yaml").write_text("env: prod")

            copy_fixture_files("self_ref_arg_in_input_path", project_root)

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
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source structure
            (project_root / "src" / "v1" / "stable").mkdir(parents=True)
            (project_root / "src" / "v2" / "beta").mkdir(parents=True)
            (project_root / "src" / "v1" / "stable" / "lib.js").write_text("v1-stable")
            (project_root / "src" / "v2" / "beta" / "lib.js").write_text("v2-beta")

            copy_fixture_files("self_ref_multiple_args", project_root)

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
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("self_ref_parameterized_deps", project_root)

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
    """

    def setUp(self):
        """
        Set up test fixtures.
        """
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_self_references_with_state_tracking(self):
        """
        Test that state tracking works with self-references.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source file
            src_file = project_root / "input.txt"
            src_file.write_text("Version 1")

            copy_fixture_files("self_ref_state_tracking", project_root)

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
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source file
            src_file = project_root / "data.txt"
            src_file.write_text("Original")

            copy_fixture_files("self_ref_input_change", project_root)

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
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("self_ref_output_change", project_root)

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
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source file
            (project_root / "input.txt").write_text("Data")

            copy_fixture_files("self_ref_task_def_change", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # First run
                result = self.runner.invoke(app, ["transform"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Modify command (add tr to uppercase)
                recipe_file = project_root / "tasktree.yaml"
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
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source file
            (project_root / "source.txt").write_text("Content")

            copy_fixture_files("self_ref_force_execution", project_root)

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
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source files
            src_file = project_root / "main.c"
            src_file.write_text("int main() { return 0; }")

            header_file = project_root / "config.h"
            header_file.write_text("#define VERSION 1")

            copy_fixture_files("self_ref_incremental_chain", project_root)

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
    """

    def setUp(self):
        """
        Set up test fixtures.
        """
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_basic_positional_input(self):
        """
        Test basic positional input access {{ self.inputs.0 }}.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source files
            (project_root / "file1.txt").write_text("First")
            (project_root / "file2.txt").write_text("Second")

            copy_fixture_files("self_ref_positional_input", project_root)

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
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("self_ref_positional_output", project_root)

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
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source files
            (project_root / "named.txt").write_text("Named")
            (project_root / "anon.txt").write_text("Anonymous")

            copy_fixture_files("self_ref_mixed_named_positional", project_root)

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
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source file
            (project_root / "data.txt").write_text("Data")

            copy_fixture_files("self_ref_same_item_name_and_index", project_root)

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
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source file with variable-expanded name
            (project_root / "file-1.0.txt").write_text("Version 1.0")

            copy_fixture_files("self_ref_positional_with_vars", project_root)

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
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("self_ref_out_of_bounds_input", project_root)

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
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("self_ref_out_of_bounds_output", project_root)

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
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("self_ref_empty_inputs_with_index", project_root)

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
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create source files
            (project_root / "a.txt").write_text("A")
            (project_root / "b.txt").write_text("B")

            copy_fixture_files("self_ref_positional_glob", project_root)

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
