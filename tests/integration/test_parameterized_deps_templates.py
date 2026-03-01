"""Integration tests for template substitution in dependency arguments.

This module tests the new feature where task arguments can be substituted
into dependency arguments using {{ arg.* }} templates.
"""

import subprocess
import tempfile
from pathlib import Path

from fixture_utils import copy_fixture_files


class TestParameterizedDependenciesWithTemplates:
    """
    Test template substitution in dependency arguments.
    """

    def test_simple_template_substitution(self):
        """
        Test basic {{ arg.* }} template substitution in dependency args.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            copy_fixture_files("parameterized_dep_template_simple", Path(tmp_dir))

            result = subprocess.run(
                ["python3", "-m", "tasktree.cli", "bar", "production"],
                cwd=tmp_dir,
                capture_output=True,
                text=True,
            )

            assert result.returncode == 0, f"Command failed: {result.stderr}"
            assert "foo_mode=production" in result.stdout
            assert "bar_env=production" in result.stdout

    def test_template_with_string_type(self):
        """
        Test template substitution with string types (safer than int).
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            copy_fixture_files("parameterized_dep_template_string_type", Path(tmp_dir))

            result = subprocess.run(
                ["python3", "-m", "tasktree.cli", "deploy", "release"],
                cwd=tmp_dir,
                capture_output=True,
                text=True,
            )

            assert result.returncode == 0, (
                f"Command failed: {result.stderr}\nStdout: {result.stdout}"
            )
            assert "build_mode=release" in result.stdout
            assert "deploy_mode=release" in result.stdout

    def test_multiple_templates_in_one_dependency(self):
        """
        Test multiple template substitutions in a single dependency.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            copy_fixture_files("parameterized_dep_template_multiple", Path(tmp_dir))

            result = subprocess.run(
                ["python3", "-m", "tasktree.cli", "test", "release", "x86_64"],
                cwd=tmp_dir,
                capture_output=True,
                text=True,
            )

            assert result.returncode == 0, f"Command failed: {result.stderr}"
            assert "compile_mode=release_arch=x86_64" in result.stdout
            assert "test_done" in result.stdout

    def test_named_args_with_templates(self):
        """
        Test template substitution with named arguments.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            copy_fixture_files("parameterized_dep_template_named_args", Path(tmp_dir))

            result = subprocess.run(
                ["python3", "-m", "tasktree.cli", "test", "debug"],
                cwd=tmp_dir,
                capture_output=True,
                text=True,
            )

            assert result.returncode == 0, f"Command failed: {result.stderr}"
            assert "build_mode=debug_opt=true" in result.stdout
            assert "test_env=debug" in result.stdout

    def test_backward_compatibility_literal_args(self):
        """
        Test that literal dependency args still work (backward compatibility).
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            copy_fixture_files(
                "parameterized_dep_template_backward_compat", Path(tmp_dir)
            )

            result = subprocess.run(
                ["python3", "-m", "tasktree.cli", "test"],
                cwd=tmp_dir,
                capture_output=True,
                text=True,
            )

            assert result.returncode == 0, f"Command failed: {result.stderr}"
            assert "build_mode=debug" in result.stdout
            assert "test_done" in result.stdout

    def test_template_with_choices_validation(self):
        """
        Test that type validation works after template substitution.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            copy_fixture_files("parameterized_dep_template_choices", Path(tmp_dir))

            result = subprocess.run(
                ["python3", "-m", "tasktree.cli", "test", "release"],
                cwd=tmp_dir,
                capture_output=True,
                text=True,
            )

            assert result.returncode == 0, f"Command failed: {result.stderr}"
            assert "build_mode=release" in result.stdout
            assert "test_env=release" in result.stdout

    def test_invalid_template_reference(self):
        """
        Test that referencing undefined parent arg fails with clear error.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            copy_fixture_files("parameterized_dep_template_invalid_ref", Path(tmp_dir))

            result = subprocess.run(
                ["python3", "-m", "tasktree.cli", "test", "debug"],
                cwd=tmp_dir,
                capture_output=True,
                text=True,
            )

            assert result.returncode != 0, "Command should have failed"
            output = result.stdout + result.stderr
            assert "undefined_arg" in output or "not defined" in output.lower()
