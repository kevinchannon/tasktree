"""Integration tests for template substitution in dependency arguments.

This module tests the new feature where task arguments can be substituted
into dependency arguments using {{ arg.* }} templates.
"""

import subprocess
import tempfile
from pathlib import Path


class TestParameterizedDependenciesWithTemplates:
    """
    Test template substitution in dependency arguments.
    @athena: 98e6139cdc98
    """

    def test_simple_template_substitution(self):
        """
        Test basic {{ arg.* }} template substitution in dependency args.
        @athena: 955de4510516
        """
        recipe_content = """
tasks:
  foo:
    args: [ "mode" ]
    cmd: "echo foo_mode={{ arg.mode }}"

  bar:
    deps:
      - foo: [ "{{ arg.env }}" ]
    args: [ "env" ]
    cmd: "echo bar_env={{ arg.env }}"
"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            recipe_path = Path(tmp_dir) / "tt.yaml"
            recipe_path.write_text(recipe_content)

            # Run bar with env=production
            result = subprocess.run(
                ["python3", "-m", "tasktree.cli", "bar", "production"],
                cwd=tmp_dir,
                capture_output=True,
                text=True
            )

            assert result.returncode == 0, f"Command failed: {result.stderr}"
            # foo should be called with mode=production
            assert "foo_mode=production" in result.stdout
            # bar should be called with env=production
            assert "bar_env=production" in result.stdout

    def test_template_with_string_type(self):
        """
        Test template substitution with string types (safer than int).
        @athena: 1a865ba0a251
        """
        recipe_content = """
tasks:
  build:
    args: [ "mode" ]
    cmd: "echo build_mode={{ arg.mode }}"

  deploy:
    deps:
      - build: [ "{{ arg.m }}" ]
    args: [ "m" ]
    cmd: "echo deploy_mode={{ arg.m }}"
"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            recipe_path = Path(tmp_dir) / "tt.yaml"
            recipe_path.write_text(recipe_content)

            # Run deploy with m=release
            result = subprocess.run(
                ["python3", "-m", "tasktree.cli", "deploy", "release"],
                cwd=tmp_dir,
                capture_output=True,
                text=True
            )

            assert result.returncode == 0, f"Command failed: {result.stderr}\nStdout: {result.stdout}"
            # build should be called with mode=release
            assert "build_mode=release" in result.stdout
            # deploy should be called with m=release
            assert "deploy_mode=release" in result.stdout

    def test_multiple_templates_in_one_dependency(self):
        """
        Test multiple template substitutions in a single dependency.
        @athena: 1fcdc3ec034b
        """
        recipe_content = """
tasks:
  compile:
    args: [ "mode", "arch" ]
    cmd: "echo compile_mode={{ arg.mode }}_arch={{ arg.arch }}"

  test:
    deps:
      - compile: [ "{{ arg.build_mode }}", "{{ arg.architecture }}" ]
    args: [ "build_mode", "architecture" ]
    cmd: "echo test_done"
"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            recipe_path = Path(tmp_dir) / "tt.yaml"
            recipe_path.write_text(recipe_content)

            # Run test with build_mode=release architecture=x86_64
            result = subprocess.run(
                ["python3", "-m", "tasktree.cli", "test", "release", "x86_64"],
                cwd=tmp_dir,
                capture_output=True,
                text=True
            )

            assert result.returncode == 0, f"Command failed: {result.stderr}"
            # compile should be called with mode=release, arch=x86_64
            assert "compile_mode=release_arch=x86_64" in result.stdout
            assert "test_done" in result.stdout

    def test_named_args_with_templates(self):
        """
        Test template substitution with named arguments.
        @athena: 21c32062ceed
        """
        recipe_content = """
tasks:
  build:
    args: [ "mode", "optimize" ]
    cmd: "echo build_mode={{ arg.mode }}_opt={{ arg.optimize }}"

  test:
    deps:
      - build: { mode: "{{ arg.env }}", optimize: true }
    args: [ "env" ]
    cmd: "echo test_env={{ arg.env }}"
"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            recipe_path = Path(tmp_dir) / "tt.yaml"
            recipe_path.write_text(recipe_content)

            # Run test with env=debug
            result = subprocess.run(
                ["python3", "-m", "tasktree.cli", "test", "debug"],
                cwd=tmp_dir,
                capture_output=True,
                text=True
            )

            assert result.returncode == 0, f"Command failed: {result.stderr}"
            # build should be called with mode=debug, optimize=true
            assert "build_mode=debug_opt=true" in result.stdout  # Note: bool lowercased
            assert "test_env=debug" in result.stdout

    def test_backward_compatibility_literal_args(self):
        """
        Test that literal dependency args still work (backward compatibility).
        @athena: 893161e3c845
        """
        recipe_content = """
tasks:
  build:
    args: [ "mode" ]
    cmd: "echo build_mode={{ arg.mode }}"

  test:
    deps:
      - build: [ "debug" ]  # Literal value, no template
    cmd: "echo test_done"
"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            recipe_path = Path(tmp_dir) / "tt.yaml"
            recipe_path.write_text(recipe_content)

            # Run test (no args needed)
            result = subprocess.run(
                ["python3", "-m", "tasktree.cli", "test"],
                cwd=tmp_dir,
                capture_output=True,
                text=True
            )

            assert result.returncode == 0, f"Command failed: {result.stderr}"
            # build should be called with literal mode=debug
            assert "build_mode=debug" in result.stdout
            assert "test_done" in result.stdout

    def test_template_with_choices_validation(self):
        """
        Test that type validation works after template substitution.
        @athena: c6dd72e1a80a
        """
        recipe_content = """
tasks:
  build:
    args:
      - mode: { type: str, choices: [ "debug", "release" ] }
    cmd: "echo build_mode={{ arg.mode }}"

  test:
    deps:
      - build: [ "{{ arg.env }}" ]
    args:
      - env: { type: str, choices: [ "debug", "release" ] }
    cmd: "echo test_env={{ arg.env }}"
"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            recipe_path = Path(tmp_dir) / "tt.yaml"
            recipe_path.write_text(recipe_content)

            # Run test with valid choice
            result = subprocess.run(
                ["python3", "-m", "tasktree.cli", "test", "release"],
                cwd=tmp_dir,
                capture_output=True,
                text=True
            )

            assert result.returncode == 0, f"Command failed: {result.stderr}"
            assert "build_mode=release" in result.stdout
            assert "test_env=release" in result.stdout

    def test_invalid_template_reference(self):
        """
        Test that referencing undefined parent arg fails with clear error.
        @athena: 22125cec994e
        """
        recipe_content = """
tasks:
  build:
    args: [ "mode" ]
    cmd: "echo build_mode={{ arg.mode }}"

  test:
    deps:
      - build: [ "{{ arg.undefined_arg }}" ]
    args: [ "env" ]
    cmd: "echo test"
"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            recipe_path = Path(tmp_dir) / "tt.yaml"
            recipe_path.write_text(recipe_content)

            # Run test - should fail because undefined_arg doesn't exist
            result = subprocess.run(
                ["python3", "-m", "tasktree.cli", "test", "debug"],
                cwd=tmp_dir,
                capture_output=True,
                text=True
            )

            assert result.returncode != 0, "Command should have failed"
            # Error messages can appear in either stdout or stderr
            output = result.stdout + result.stderr
            assert "undefined_arg" in output or "not defined" in output.lower()
