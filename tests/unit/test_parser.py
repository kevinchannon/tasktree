"""Tests for parser module."""

import os
import platform
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

from tasktree.parser import (
    CircularImportError,
    Task,
    find_recipe_file,
    parse_arg_spec,
    parse_recipe,
)


class TestParseArgSpec(unittest.TestCase):
    def test_parse_simple_arg(self):
        """Test parsing a simple argument name."""
        name, arg_type, default = parse_arg_spec("environment")
        self.assertEqual(name, "environment")
        self.assertEqual(arg_type, "str")
        self.assertIsNone(default)

    def test_parse_arg_with_default(self):
        """Test parsing argument with default value."""
        name, arg_type, default = parse_arg_spec("region=eu-west-1")
        self.assertEqual(name, "region")
        self.assertEqual(arg_type, "str")
        self.assertEqual(default, "eu-west-1")

    def test_parse_arg_with_type(self):
        """Test parsing argument with type."""
        name, arg_type, default = parse_arg_spec("port:int")
        self.assertEqual(name, "port")
        self.assertEqual(arg_type, "int")
        self.assertIsNone(default)

    def test_parse_arg_with_type_and_default(self):
        """Test parsing argument with type and default."""
        name, arg_type, default = parse_arg_spec("port:int=8080")
        self.assertEqual(name, "port")
        self.assertEqual(arg_type, "int")
        self.assertEqual(default, "8080")


class TestParseRecipe(unittest.TestCase):
    def test_parse_simple_recipe(self):
        """Test parsing a simple recipe with one task."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
  build:
    cmd: cargo build --release
"""
            )

            recipe = parse_recipe(recipe_path)
            self.assertIn("build", recipe.tasks)
            task = recipe.tasks["build"]
            self.assertEqual(task.name, "build")
            self.assertEqual(task.cmd, "cargo build --release")

    def test_parse_task_with_all_fields(self):
        """Test parsing task with all fields."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
  build:
    desc: Build the project
    deps: [lint]
    inputs: ["src/**/*.rs"]
    outputs: [target/release/bin]
    working_dir: subproject
    args: [environment, region=eu-west-1]
    cmd: cargo build --release
"""
            )

            recipe = parse_recipe(recipe_path)
            task = recipe.tasks["build"]
            self.assertEqual(task.desc, "Build the project")
            self.assertEqual(task.deps, ["lint"])
            self.assertEqual(task.inputs, ["src/**/*.rs"])
            self.assertEqual(task.outputs, ["target/release/bin"])
            self.assertEqual(task.working_dir, "subproject")
            self.assertEqual(task.args, ["environment", "region=eu-west-1"])
            self.assertEqual(task.cmd, "cargo build --release")

    def test_parse_with_imports(self):
        """Test parsing recipe with imports."""
        with TemporaryDirectory() as tmpdir:
            # Create import file
            import_dir = Path(tmpdir) / "common"
            import_dir.mkdir()
            import_file = import_dir / "build.yaml"
            import_file.write_text(
                """
tasks:
  compile:
    cmd: cargo build
"""
            )

            # Create main recipe
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
imports:
  - file: common/build.yaml
    as: build

tasks:
  test:
    deps: [build.compile]
    cmd: cargo test
"""
            )

            recipe = parse_recipe(recipe_path)
            self.assertIn("build.compile", recipe.tasks)
            self.assertIn("test", recipe.tasks)

            compile_task = recipe.tasks["build.compile"]
            self.assertEqual(compile_task.name, "build.compile")
            self.assertEqual(compile_task.cmd, "cargo build")

            test_task = recipe.tasks["test"]
            self.assertEqual(test_task.deps, ["build.compile"])


class TestParseImports(unittest.TestCase):
    """Test parsing of recipe imports with various edge cases."""

    def test_multiple_imports(self):
        """Test importing multiple files."""
        with TemporaryDirectory() as tmpdir:
            # Create first import
            (Path(tmpdir) / "build.yaml").write_text("""
tasks:
  compile:
    cmd: cargo build
""")
            # Create second import
            (Path(tmpdir) / "test.yaml").write_text("""
tasks:
  unit:
    cmd: cargo test --lib
  integration:
    cmd: cargo test --test '*'
""")

            # Create main recipe
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
imports:
  - file: build.yaml
    as: build
  - file: test.yaml
    as: test

tasks:
  all:
    deps: [build.compile, test.unit, test.integration]
    cmd: echo "All done"
""")

            recipe = parse_recipe(recipe_path)
            self.assertIn("build.compile", recipe.tasks)
            self.assertIn("test.unit", recipe.tasks)
            self.assertIn("test.integration", recipe.tasks)
            self.assertIn("all", recipe.tasks)

            all_task = recipe.tasks["all"]
            self.assertEqual(all_task.deps, ["build.compile", "test.unit", "test.integration"])

    def test_nested_imports(self):
        """Test that imported files can also have imports (nested imports)."""
        with TemporaryDirectory() as tmpdir:
            # Create deepest level import
            (Path(tmpdir) / "base.yaml").write_text("""
tasks:
  setup:
    cmd: echo "base setup"
""")

            # Create middle level import that imports base
            (Path(tmpdir) / "common.yaml").write_text("""
imports:
  - file: base.yaml
    as: base

tasks:
  prepare:
    deps: [base.setup]
    cmd: echo "common prepare"
""")

            # Create main recipe that imports common
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
imports:
  - file: common.yaml
    as: common

tasks:
  build:
    deps: [common.prepare, common.base.setup]
    cmd: echo "building"
""")

            recipe = parse_recipe(recipe_path)
            self.assertIn("common.base.setup", recipe.tasks)
            self.assertIn("common.prepare", recipe.tasks)
            self.assertIn("build", recipe.tasks)

            build_task = recipe.tasks["build"]
            self.assertEqual(build_task.deps, ["common.prepare", "common.base.setup"])

    def test_deep_nested_imports(self):
        """Test deeply nested imports (A -> B -> C -> D)."""
        with TemporaryDirectory() as tmpdir:
            # Level 4 (deepest)
            (Path(tmpdir) / "level4.yaml").write_text("""
tasks:
  task4:
    cmd: echo "level 4"
""")

            # Level 3
            (Path(tmpdir) / "level3.yaml").write_text("""
imports:
  - file: level4.yaml
    as: l4

tasks:
  task3:
    deps: [l4.task4]
    cmd: echo "level 3"
""")

            # Level 2
            (Path(tmpdir) / "level2.yaml").write_text("""
imports:
  - file: level3.yaml
    as: l3

tasks:
  task2:
    deps: [l3.task3]
    cmd: echo "level 2"
""")

            # Level 1 (main)
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
imports:
  - file: level2.yaml
    as: l2

tasks:
  task1:
    deps: [l2.task2]
    cmd: echo "level 1"
""")

            recipe = parse_recipe(recipe_path)
            self.assertIn("l2.l3.l4.task4", recipe.tasks)
            self.assertIn("l2.l3.task3", recipe.tasks)
            self.assertIn("l2.task2", recipe.tasks)
            self.assertIn("task1", recipe.tasks)

    def test_diamond_import_topology(self):
        """Test diamond import pattern: A imports B and C, both import D."""
        with TemporaryDirectory() as tmpdir:
            # Base file (D)
            (Path(tmpdir) / "base.yaml").write_text("""
tasks:
  setup:
    cmd: echo "base setup"
""")

            # Left branch (B)
            (Path(tmpdir) / "left.yaml").write_text("""
imports:
  - file: base.yaml
    as: base

tasks:
  left-task:
    deps: [base.setup]
    cmd: echo "left"
""")

            # Right branch (C)
            (Path(tmpdir) / "right.yaml").write_text("""
imports:
  - file: base.yaml
    as: base

tasks:
  right-task:
    deps: [base.setup]
    cmd: echo "right"
""")

            # Main file (A)
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
imports:
  - file: left.yaml
    as: left
  - file: right.yaml
    as: right

tasks:
  main:
    deps: [left.left-task, right.right-task]
    cmd: echo "main"
""")

            recipe = parse_recipe(recipe_path)
            # Both paths to base.setup should exist
            self.assertIn("left.base.setup", recipe.tasks)
            self.assertIn("right.base.setup", recipe.tasks)
            self.assertIn("left.left-task", recipe.tasks)
            self.assertIn("right.right-task", recipe.tasks)
            self.assertIn("main", recipe.tasks)

    def test_import_file_not_found(self):
        """Test that importing a non-existent file raises an error."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
imports:
  - file: nonexistent.yaml
    as: missing

tasks:
  task:
    cmd: echo "test"
""")

            with self.assertRaises(FileNotFoundError):
                parse_recipe(recipe_path)

    def test_import_with_relative_paths(self):
        """Test importing files from subdirectories."""
        with TemporaryDirectory() as tmpdir:
            # Create nested directory structure
            subdir = Path(tmpdir) / "tasks" / "build"
            subdir.mkdir(parents=True)

            (subdir / "compile.yaml").write_text("""
tasks:
  rust:
    cmd: cargo build
  python:
    cmd: python -m build
""")

            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
imports:
  - file: tasks/build/compile.yaml
    as: compile

tasks:
  all:
    deps: [compile.rust, compile.python]
    cmd: echo "done"
""")

            recipe = parse_recipe(recipe_path)
            self.assertIn("compile.rust", recipe.tasks)
            self.assertIn("compile.python", recipe.tasks)

    def test_import_preserves_task_properties(self):
        """Test that imported tasks preserve all their properties."""
        with TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "import.yaml").write_text("""
tasks:
  build:
    desc: Build the project
    inputs: ["src/**/*.rs"]
    outputs: [target/release/bin]
    working_dir: subproject
    args: [environment, region=eu-west-1]
    cmd: cargo build --release
""")

            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
imports:
  - file: import.yaml
    as: imported
""")

            recipe = parse_recipe(recipe_path)
            task = recipe.tasks["imported.build"]

            self.assertEqual(task.desc, "Build the project")
            self.assertEqual(task.inputs, ["src/**/*.rs"])
            self.assertEqual(task.outputs, ["target/release/bin"])
            self.assertEqual(task.working_dir, "subproject")
            self.assertEqual(task.args, ["environment", "region=eu-west-1"])
            self.assertEqual(task.cmd, "cargo build --release")

    def test_cross_import_dependencies(self):
        """Test tasks in one import depending on tasks from another import."""
        with TemporaryDirectory() as tmpdir:
            # First import defines build
            (Path(tmpdir) / "build.yaml").write_text("""
tasks:
  compile:
    cmd: cargo build
""")

            # Second import depends on first import
            (Path(tmpdir) / "test.yaml").write_text("""
tasks:
  run-tests:
    deps: [build.compile]
    cmd: cargo test
""")

            # Main recipe imports both
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
imports:
  - file: build.yaml
    as: build
  - file: test.yaml
    as: test
""")

            recipe = parse_recipe(recipe_path)

            # The dependency should be rewritten to use the full namespace
            test_task = recipe.tasks["test.run-tests"]
            # Note: This tests current behavior - the dep might stay as "build.compile"
            # or might need namespace resolution
            self.assertEqual(test_task.deps, ["build.compile"])

    def test_empty_import_file(self):
        """Test importing a file with no tasks."""
        with TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "empty.yaml").write_text("")

            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
imports:
  - file: empty.yaml
    as: empty

tasks:
  task:
    cmd: echo "test"
""")

            recipe = parse_recipe(recipe_path)
            # Should not crash, just have no tasks from the import
            self.assertIn("task", recipe.tasks)
            # No tasks should be prefixed with "empty."
            empty_tasks = [name for name in recipe.tasks if name.startswith("empty.")]
            self.assertEqual(len(empty_tasks), 0)

    def test_import_file_with_only_whitespace(self):
        """Test importing a file that only contains whitespace/comments."""
        with TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "whitespace.yaml").write_text("""
# This file only has comments


# And whitespace
""")

            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
imports:
  - file: whitespace.yaml
    as: ws

tasks:
  task:
    cmd: echo "test"
""")

            recipe = parse_recipe(recipe_path)
            self.assertIn("task", recipe.tasks)

    def test_circular_import_self_reference(self):
        """Test that a file importing itself raises CircularImportError."""
        with TemporaryDirectory() as tmpdir:
            # Create a file that imports itself
            (Path(tmpdir) / "self.yaml").write_text("""
imports:
  - file: self.yaml
    as: myself

tasks:
  task:
    cmd: echo "test"
""")

            recipe_path = Path(tmpdir) / "self.yaml"
            with self.assertRaises(CircularImportError) as cm:
                parse_recipe(recipe_path)

            # Check error message shows the circular chain
            self.assertIn("Circular import detected", str(cm.exception))
            self.assertIn("self.yaml", str(cm.exception))

    def test_circular_import_two_files(self):
        """Test that A→B→A circular import is detected."""
        with TemporaryDirectory() as tmpdir:
            # A imports B
            (Path(tmpdir) / "a.yaml").write_text("""
imports:
  - file: b.yaml
    as: b

tasks:
  task-a:
    cmd: echo "a"
""")

            # B imports A (creates cycle)
            (Path(tmpdir) / "b.yaml").write_text("""
imports:
  - file: a.yaml
    as: a

tasks:
  task-b:
    cmd: echo "b"
""")

            recipe_path = Path(tmpdir) / "a.yaml"
            with self.assertRaises(CircularImportError) as cm:
                parse_recipe(recipe_path)

            error_msg = str(cm.exception)
            self.assertIn("Circular import detected", error_msg)
            # Should show the chain: a.yaml → b.yaml → a.yaml
            self.assertIn("a.yaml", error_msg)
            self.assertIn("b.yaml", error_msg)

    def test_circular_import_three_files(self):
        """Test that A→B→C→A circular import is detected."""
        with TemporaryDirectory() as tmpdir:
            # A imports B
            (Path(tmpdir) / "a.yaml").write_text("""
imports:
  - file: b.yaml
    as: b

tasks:
  task-a:
    cmd: echo "a"
""")

            # B imports C
            (Path(tmpdir) / "b.yaml").write_text("""
imports:
  - file: c.yaml
    as: c

tasks:
  task-b:
    cmd: echo "b"
""")

            # C imports A (creates cycle)
            (Path(tmpdir) / "c.yaml").write_text("""
imports:
  - file: a.yaml
    as: a

tasks:
  task-c:
    cmd: echo "c"
""")

            recipe_path = Path(tmpdir) / "a.yaml"
            with self.assertRaises(CircularImportError) as cm:
                parse_recipe(recipe_path)

            error_msg = str(cm.exception)
            self.assertIn("Circular import detected", error_msg)
            # Should show all three files in the chain
            self.assertIn("a.yaml", error_msg)
            self.assertIn("b.yaml", error_msg)
            self.assertIn("c.yaml", error_msg)

    def test_import_path_resolution_file_relative(self):
        """Test imports are resolved relative to importing file, not project root."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create directory structure
            common_dir = project_root / "common"
            shared_dir = project_root / "shared"
            common_dir.mkdir()
            shared_dir.mkdir()

            # shared/utils.yaml
            (shared_dir / "utils.yaml").write_text("""
tasks:
  utility:
    cmd: echo "utility task"
""")

            # common/base.yaml imports ../shared/utils.yaml (relative to common/)
            (common_dir / "base.yaml").write_text("""
imports:
  - file: ../shared/utils.yaml
    as: utils

tasks:
  base-task:
    deps: [utils.utility]
    cmd: echo "base"
""")

            # Main recipe imports common/base.yaml
            recipe_path = project_root / "tasktree.yaml"
            recipe_path.write_text("""
imports:
  - file: common/base.yaml
    as: common

tasks:
  main:
    deps: [common.base-task]
    cmd: echo "main"
""")

            recipe = parse_recipe(recipe_path)

            # Should have all tasks with proper namespacing
            self.assertIn("common.utils.utility", recipe.tasks)
            self.assertIn("common.base-task", recipe.tasks)
            self.assertIn("main", recipe.tasks)

            # Verify dependency chain
            main_task = recipe.tasks["main"]
            self.assertEqual(main_task.deps, ["common.base-task"])

            base_task = recipe.tasks["common.base-task"]
            self.assertEqual(base_task.deps, ["common.utils.utility"])

    def test_nested_import_file_not_found(self):
        """Test clear error when nested import file doesn't exist."""
        with TemporaryDirectory() as tmpdir:
            # common.yaml tries to import a file that doesn't exist
            (Path(tmpdir) / "common.yaml").write_text("""
imports:
  - file: nonexistent.yaml
    as: missing

tasks:
  task:
    cmd: echo "test"
""")

            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
imports:
  - file: common.yaml
    as: common
""")

            with self.assertRaises(FileNotFoundError) as cm:
                parse_recipe(recipe_path)

            self.assertIn("Import file not found", str(cm.exception))


class TestParseMultilineCommands(unittest.TestCase):
    """Test parsing of different YAML multi-line command formats."""

    def test_parse_single_line_command(self):
        """Test parsing a single-line command (cmd: <string>)."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
  build:
    cmd: echo "single line"
"""
            )

            recipe = parse_recipe(recipe_path)
            task = recipe.tasks["build"]
            self.assertEqual(task.cmd, 'echo "single line"')

    def test_parse_literal_block_scalar(self):
        """Test parsing literal block scalar (cmd: |) which preserves newlines."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
  build:
    cmd: |
      echo "line 1"
      echo "line 2"
      echo "line 3"
"""
            )

            recipe = parse_recipe(recipe_path)
            task = recipe.tasks["build"]
            # Literal block scalar preserves newlines
            expected = 'echo "line 1"\necho "line 2"\necho "line 3"\n'
            self.assertEqual(task.cmd, expected)

    def test_parse_folded_block_scalar(self):
        """Test parsing folded block scalar (cmd: >) which folds newlines into spaces."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
  build:
    cmd: >
      echo "this is a very long command"
      "that spans multiple lines"
      "but becomes a single line"
"""
            )

            recipe = parse_recipe(recipe_path)
            task = recipe.tasks["build"]
            # Folded block scalar converts newlines to spaces
            expected = 'echo "this is a very long command" "that spans multiple lines" "but becomes a single line"\n'
            self.assertEqual(task.cmd, expected)

    def test_parse_literal_block_with_shell_commands(self):
        """Test parsing literal block with actual shell commands."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
  clean:
    cmd: |
      rm -rf dist/
      rm -rf build/
      find . -name __pycache__ -exec rm -rf {} +
"""
            )

            recipe = parse_recipe(recipe_path)
            task = recipe.tasks["clean"]
            # Should preserve each command on its own line
            self.assertIn("rm -rf dist/", task.cmd)
            self.assertIn("rm -rf build/", task.cmd)
            self.assertIn("find . -name __pycache__", task.cmd)
            # Verify newlines are preserved
            lines = task.cmd.strip().split("\n")
            self.assertEqual(len(lines), 3)

    def test_parse_literal_block_with_variables(self):
        """Test parsing literal block that uses shell variables."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
  deploy:
    cmd: |
      VERSION=$(cat version.txt)
      echo "Deploying version $VERSION"
"""
            )

            recipe = parse_recipe(recipe_path)
            task = recipe.tasks["deploy"]
            # Should preserve the multi-line shell script
            self.assertIn("VERSION=$(cat version.txt)", task.cmd)
            self.assertIn('echo "Deploying version $VERSION"', task.cmd)

    def test_parse_literal_block_strip_final_newlines(self):
        """Test that literal block scalar (|-) strips final newlines."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
  build:
    cmd: |-
      echo "line 1"
      echo "line 2"
"""
            )

            recipe = parse_recipe(recipe_path)
            task = recipe.tasks["build"]
            # |- strips the final newline
            expected = 'echo "line 1"\necho "line 2"'
            self.assertEqual(task.cmd, expected)


class TestParserErrors(unittest.TestCase):
    """Tests for parser error conditions."""

    def test_parse_invalid_yaml_syntax(self):
        """Test yaml.YAMLError is raised for invalid YAML."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            # Create a file with invalid YAML syntax
            recipe_path.write_text(
                """
tasks:
  build:
    cmd: echo "test"
    deps: [invalid
"""
            )

            with self.assertRaises(yaml.YAMLError):
                parse_recipe(recipe_path)

    def test_parse_task_not_dictionary(self):
        """Test ValueError when task is not a dict."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            # Task defined as a string instead of a dictionary
            recipe_path.write_text(
                """
tasks:
  build: echo "this should be a dict"
"""
            )

            with self.assertRaises(ValueError) as cm:
                parse_recipe(recipe_path)
            self.assertIn("must be a dictionary", str(cm.exception))

    def test_parse_task_missing_cmd(self):
        """Test ValueError when task has no 'cmd' field."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            # Task defined without required 'cmd' field
            recipe_path.write_text(
                """
tasks:
  build:
    desc: Build task
    outputs: [output.txt]
"""
            )

            with self.assertRaises(ValueError) as cm:
                parse_recipe(recipe_path)
            self.assertIn("missing required 'cmd' field", str(cm.exception))


class TestFindRecipeFile(unittest.TestCase):
    """Tests for find_recipe_file() function."""

    def test_find_recipe_file_current_dir_tasktree(self):
        """Test finds tasktree.yaml in current directory."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir).resolve()
            recipe_path = project_root / "tasktree.yaml"
            recipe_path.write_text("tasks:\n  build:\n    cmd: echo test")

            result = find_recipe_file(project_root)
            self.assertEqual(result, recipe_path)

    def test_find_recipe_file_current_dir_tt(self):
        """Test finds tt.yaml in current directory."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir).resolve()
            recipe_path = project_root / "tt.yaml"
            recipe_path.write_text("tasks:\n  build:\n    cmd: echo test")

            result = find_recipe_file(project_root)
            self.assertEqual(result, recipe_path)

    def test_find_recipe_file_parent_directory(self):
        """Test searches parent directories."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir).resolve()
            recipe_path = project_root / "tasktree.yaml"
            recipe_path.write_text("tasks:\n  build:\n    cmd: echo test")

            # Create subdirectory
            subdir = project_root / "src" / "nested"
            subdir.mkdir(parents=True)

            # Search from subdirectory should find parent recipe
            result = find_recipe_file(subdir)
            self.assertEqual(result, recipe_path)

    def test_find_recipe_file_not_found(self):
        """Test returns None when no recipe at root."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            result = find_recipe_file(project_root)
            self.assertIsNone(result)

    def test_find_recipe_file_multiple_files_raises_error(self):
        """Test raises error when multiple recipe files found."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir).resolve()
            tasktree_path = project_root / "tasktree.yaml"
            tt_path = project_root / "tt.yaml"

            # Create both files
            tasktree_path.write_text("tasks:\n  build:\n    cmd: echo from tasktree")
            tt_path.write_text("tasks:\n  build:\n    cmd: echo from tt")

            # Should raise ValueError with helpful message
            with self.assertRaises(ValueError) as cm:
                find_recipe_file(project_root)

            error_msg = str(cm.exception)
            self.assertIn("Multiple recipe files found", error_msg)
            self.assertIn("tasktree.yaml", error_msg)
            self.assertIn("tt.yaml", error_msg)
            self.assertIn("--tasks", error_msg)

    def test_find_recipe_file_yml_extension(self):
        """Test finds tasktree.yml (with .yml extension)."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir).resolve()
            recipe_path = project_root / "tasktree.yml"
            recipe_path.write_text("tasks:\n  build:\n    cmd: echo test")

            result = find_recipe_file(project_root)
            self.assertEqual(result, recipe_path)

    def test_find_recipe_file_tasks_extension(self):
        """Test finds *.tasks files."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir).resolve()
            recipe_path = project_root / "build.tasks"
            recipe_path.write_text("tasks:\n  build:\n    cmd: echo test")

            result = find_recipe_file(project_root)
            self.assertEqual(result, recipe_path)

    def test_find_recipe_file_multiple_tasks_files_raises_error(self):
        """Test raises error when multiple *.tasks files found."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir).resolve()
            build_tasks = project_root / "build.tasks"
            test_tasks = project_root / "test.tasks"

            build_tasks.write_text("tasks:\n  build:\n    cmd: echo build")
            test_tasks.write_text("tasks:\n  test:\n    cmd: echo test")

            # Should raise ValueError
            with self.assertRaises(ValueError) as cm:
                find_recipe_file(project_root)

            error_msg = str(cm.exception)
            self.assertIn("Multiple recipe files found", error_msg)
            self.assertIn("--tasks", error_msg)


class TestEnvironmentParsing(unittest.TestCase):
    """Test parsing of environments section."""

    def test_parse_environments_section(self):
        """Test parsing environments from YAML."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            recipe_path = project_root / "tasktree.yaml"

            recipe_path.write_text("""
environments:
  default: bash-strict
  bash-strict:
    shell: bash
    args: ['-c']
    preamble: |
      set -euo pipefail

  python:
    shell: python
    args: ['-c']

tasks:
  test:
    cmd: echo test
""")

            recipe = parse_recipe(recipe_path)

            # Check environments were parsed
            self.assertEqual(len(recipe.environments), 2)
            self.assertIn("bash-strict", recipe.environments)
            self.assertIn("python", recipe.environments)

            # Check default environment
            self.assertEqual(recipe.default_env, "bash-strict")

            # Check bash-strict environment
            bash_env = recipe.environments["bash-strict"]
            self.assertEqual(bash_env.name, "bash-strict")
            self.assertEqual(bash_env.shell, "bash")
            self.assertEqual(bash_env.args, ["-c"])
            self.assertIn("set -euo pipefail", bash_env.preamble)

            # Check python environment
            py_env = recipe.environments["python"]
            self.assertEqual(py_env.name, "python")
            self.assertEqual(py_env.shell, "python")
            self.assertEqual(py_env.args, ["-c"])

    def test_parse_recipe_without_environments(self):
        """Test parsing recipe without environments section."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            recipe_path = project_root / "tasktree.yaml"

            recipe_path.write_text("""
tasks:
  test:
    cmd: echo test
""")

            recipe = parse_recipe(recipe_path)

            # Should have no environments
            self.assertEqual(len(recipe.environments), 0)
            self.assertEqual(recipe.default_env, "")

    def test_environment_missing_shell(self):
        """Test error when environment doesn't specify shell."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            recipe_path = project_root / "tasktree.yaml"

            recipe_path.write_text("""
environments:
  bad-env:
    args: ['-c']

tasks:
  test:
    cmd: echo test
""")

            with self.assertRaises(ValueError) as cm:
                parse_recipe(recipe_path)

            # Updated error message accounts for Docker environments
            self.assertIn("must specify either 'shell'", str(cm.exception))


class TestTasksFieldValidation(unittest.TestCase):
    """Tests for validating that tasks must be under 'tasks:' key."""

    def test_missing_tasks_key_with_task_definitions(self):
        """Test that root-level task definitions raise an error."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
build:
  cmd: cargo build

test:
  cmd: cargo test
""")

            with self.assertRaises(ValueError) as cm:
                parse_recipe(recipe_path)

            error_msg = str(cm.exception)
            self.assertIn("Task definitions must be under a top-level 'tasks:' key", error_msg)
            self.assertIn("build", error_msg)
            self.assertIn("test", error_msg)
            self.assertIn("Did you mean:", error_msg)

    def test_invalid_top_level_keys(self):
        """Test that unknown top-level keys raise an error."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
custom_section:
  foo: bar

another_unknown:
  baz: qux

tasks:
  build:
    cmd: echo build
""")

            with self.assertRaises(ValueError) as cm:
                parse_recipe(recipe_path)

            error_msg = str(cm.exception)
            self.assertIn("Unknown top-level keys", error_msg)
            self.assertIn("custom_section", error_msg)
            self.assertIn("another_unknown", error_msg)
            self.assertIn("Valid top-level keys are", error_msg)

    def test_empty_file_is_valid(self):
        """Test that an empty YAML file is valid (no tasks defined)."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("")

            recipe = parse_recipe(recipe_path)

            self.assertEqual(len(recipe.tasks), 0)

    def test_only_import_no_tasks(self):
        """Test that a file with only imports is valid."""
        with TemporaryDirectory() as tmpdir:
            # Create a base file with tasks
            base_path = Path(tmpdir) / "base.yaml"
            base_path.write_text("""
tasks:
  setup:
    cmd: echo setup
""")

            # Create main file with only import
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
imports:
  - file: base.yaml
    as: base
""")

            recipe = parse_recipe(recipe_path)

            # Should have the imported task
            self.assertIn("base.setup", recipe.tasks)

    def test_only_environments_no_tasks(self):
        """Test that a file with only environments is valid."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
environments:
  bash-strict:
    shell: /bin/bash
    args: ['-e', '-u']
""")

            recipe = parse_recipe(recipe_path)

            self.assertEqual(len(recipe.tasks), 0)
            self.assertIn("bash-strict", recipe.environments)

    def test_task_named_tasks_is_allowed(self):
        """Test that a task named 'tasks' is allowed under tasks: key."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
tasks:
  tasks:
    desc: A task named tasks
    cmd: echo "I am a task named tasks"

  build:
    cmd: cargo build
""")

            recipe = parse_recipe(recipe_path)

            self.assertIn("tasks", recipe.tasks)
            self.assertIn("build", recipe.tasks)
            self.assertEqual(recipe.tasks["tasks"].desc, "A task named tasks")

    def test_empty_tasks_section_is_valid(self):
        """Test that tasks: {} or tasks: with no value is valid."""
        with TemporaryDirectory() as tmpdir:
            # Test with empty dict
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
tasks: {}
""")

            recipe = parse_recipe(recipe_path)
            self.assertEqual(len(recipe.tasks), 0)

            # Test with null value
            recipe_path.write_text("""
tasks:
""")

            recipe = parse_recipe(recipe_path)
            self.assertEqual(len(recipe.tasks), 0)


class TestVariablesParsing(unittest.TestCase):
    """Test parsing of variables section with environment variable support."""

    def test_parse_env_variable_basic(self):
        """Test basic environment variable reference."""
        with TemporaryDirectory() as tmpdir:
            # Set environment variable
            os.environ["TEST_VAR"] = "test_value"
            try:
                recipe_path = Path(tmpdir) / "tasktree.yaml"
                recipe_path.write_text("""
variables:
  my_var: { env: TEST_VAR }

tasks:
  test:
    cmd: echo "{{ var.my_var }}"
""")

                recipe = parse_recipe(recipe_path)

                # Check variable was resolved
                self.assertEqual(recipe.variables["my_var"], "test_value")
            finally:
                del os.environ["TEST_VAR"]

    def test_parse_env_variable_not_set(self):
        """Test error when environment variable is not set."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
variables:
  my_var: { env: UNDEFINED_ENV_VAR }

tasks:
  test:
    cmd: echo test
""")

            with self.assertRaises(ValueError) as cm:
                parse_recipe(recipe_path)

            error_msg = str(cm.exception)
            self.assertIn("UNDEFINED_ENV_VAR", error_msg)
            self.assertIn("not set", error_msg)
            self.assertIn("Hint:", error_msg)

    def test_parse_env_variable_in_variable_expansion(self):
        """Test env variable used in other variable definitions."""
        with TemporaryDirectory() as tmpdir:
            os.environ["BASE_URL"] = "https://api.example.com"
            try:
                recipe_path = Path(tmpdir) / "tasktree.yaml"
                recipe_path.write_text("""
variables:
  base: { env: BASE_URL }
  users: "{{ var.base }}/users"
  posts: "{{ var.base }}/posts"

tasks:
  test:
    cmd: echo test
""")

                recipe = parse_recipe(recipe_path)

                self.assertEqual(recipe.variables["base"], "https://api.example.com")
                self.assertEqual(recipe.variables["users"], "https://api.example.com/users")
                self.assertEqual(recipe.variables["posts"], "https://api.example.com/posts")
            finally:
                del os.environ["BASE_URL"]

    def test_parse_env_variable_always_string(self):
        """Test env variable values are always strings."""
        with TemporaryDirectory() as tmpdir:
            os.environ["PORT"] = "8080"
            try:
                recipe_path = Path(tmpdir) / "tasktree.yaml"
                recipe_path.write_text("""
variables:
  port: { env: PORT }

tasks:
  test:
    cmd: echo "{{ var.port }}"
""")

                recipe = parse_recipe(recipe_path)

                # Should be string "8080", not int 8080
                self.assertEqual(recipe.variables["port"], "8080")
                self.assertIsInstance(recipe.variables["port"], str)
            finally:
                del os.environ["PORT"]

    def test_parse_env_variable_invalid_syntax_extra_keys(self):
        """Test error for { env: VAR, other: value } syntax."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
variables:
  my_var: { env: TEST_VAR, default: "foo" }

tasks:
  test:
    cmd: echo test
""")

            with self.assertRaises(ValueError) as cm:
                parse_recipe(recipe_path)

            error_msg = str(cm.exception)
            self.assertIn("extra keys", error_msg.lower())
            self.assertIn("default", error_msg)

    def test_parse_env_variable_invalid_name_empty(self):
        """Test error for { env: } with empty value."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
variables:
  my_var: { env: }

tasks:
  test:
    cmd: echo test
""")

            with self.assertRaises(ValueError) as cm:
                parse_recipe(recipe_path)

            error_msg = str(cm.exception)
            self.assertIn("Invalid environment variable reference", error_msg)

    def test_parse_env_variable_invalid_name_format(self):
        """Test error for invalid env var name format."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
variables:
  my_var: { env: "INVALID NAME" }

tasks:
  test:
    cmd: echo test
""")

            with self.assertRaises(ValueError) as cm:
                parse_recipe(recipe_path)

            error_msg = str(cm.exception)
            self.assertIn("Invalid environment variable name", error_msg)
            self.assertIn("INVALID NAME", error_msg)

    def test_parse_multiple_env_variables(self):
        """Test multiple environment variables in same recipe."""
        with TemporaryDirectory() as tmpdir:
            os.environ["API_KEY"] = "secret123"
            os.environ["DB_HOST"] = "localhost"
            try:
                recipe_path = Path(tmpdir) / "tasktree.yaml"
                recipe_path.write_text("""
variables:
  api_key: { env: API_KEY }
  db_host: { env: DB_HOST }
  connection: "{{ var.db_host }}:5432"

tasks:
  test:
    cmd: echo test
""")

                recipe = parse_recipe(recipe_path)

                self.assertEqual(recipe.variables["api_key"], "secret123")
                self.assertEqual(recipe.variables["db_host"], "localhost")
                self.assertEqual(recipe.variables["connection"], "localhost:5432")
            finally:
                del os.environ["API_KEY"]
                del os.environ["DB_HOST"]

    def test_parse_mixed_regular_and_env_variables(self):
        """Test mixing regular variables and env variables."""
        with TemporaryDirectory() as tmpdir:
            os.environ["REGION"] = "us-west-2"
            try:
                recipe_path = Path(tmpdir) / "tasktree.yaml"
                recipe_path.write_text("""
variables:
  app_name: "myapp"
  version: 1.0
  region: { env: REGION }
  deploy_target: "{{ var.app_name }}-{{ var.version }}-{{ var.region }}"

tasks:
  test:
    cmd: echo test
""")

                recipe = parse_recipe(recipe_path)

                self.assertEqual(recipe.variables["app_name"], "myapp")
                self.assertEqual(recipe.variables["version"], "1.0")
                self.assertEqual(recipe.variables["region"], "us-west-2")
                self.assertEqual(recipe.variables["deploy_target"], "myapp-1.0-us-west-2")
            finally:
                del os.environ["REGION"]


class TestFileReadVariables(unittest.TestCase):
    """Test parsing of variables section with file read support."""

    def test_file_read_basic(self):
        """Test basic file reading."""
        with TemporaryDirectory() as tmpdir:
            # Create data file
            data_file = Path(tmpdir) / "api-key.txt"
            data_file.write_text("secret123\n")

            # Create recipe
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
variables:
  api_key: { read: api-key.txt }

tasks:
  test:
    cmd: echo test
""")

            recipe = parse_recipe(recipe_path)

            # Verify trailing newline was stripped
            self.assertEqual(recipe.variables["api_key"], "secret123")

    def test_file_read_trailing_newline_stripped(self):
        """Test trailing newline is stripped."""
        with TemporaryDirectory() as tmpdir:
            data_file = Path(tmpdir) / "version.txt"
            data_file.write_text("1.2.3\n")

            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
variables:
  version: { read: version.txt }

tasks:
  test:
    cmd: echo test
""")

            recipe = parse_recipe(recipe_path)
            self.assertEqual(recipe.variables["version"], "1.2.3")

    def test_file_read_empty_file(self):
        """Test empty file returns empty string."""
        with TemporaryDirectory() as tmpdir:
            data_file = Path(tmpdir) / "empty.txt"
            data_file.write_text("")

            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
variables:
  empty: { read: empty.txt }

tasks:
  test:
    cmd: echo test
""")

            recipe = parse_recipe(recipe_path)
            self.assertEqual(recipe.variables["empty"], "")

    def test_file_read_only_newline(self):
        """Test file with only newline returns empty string."""
        with TemporaryDirectory() as tmpdir:
            data_file = Path(tmpdir) / "newline.txt"
            data_file.write_text("\n")

            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
variables:
  newline: { read: newline.txt }

tasks:
  test:
    cmd: echo test
""")

            recipe = parse_recipe(recipe_path)
            self.assertEqual(recipe.variables["newline"], "")

    def test_file_read_preserve_internal_newlines(self):
        """Test multi-line content preserved."""
        with TemporaryDirectory() as tmpdir:
            data_file = Path(tmpdir) / "multiline.txt"
            data_file.write_text("line1\nline2\nline3\n")

            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
variables:
  multiline: { read: multiline.txt }

tasks:
  test:
    cmd: echo test
""")

            recipe = parse_recipe(recipe_path)
            # Only final newline stripped
            self.assertEqual(recipe.variables["multiline"], "line1\nline2\nline3")

    def test_file_read_preserve_leading_trailing_spaces(self):
        """Test whitespace preserved except final newline."""
        with TemporaryDirectory() as tmpdir:
            data_file = Path(tmpdir) / "spaces.txt"
            data_file.write_text("  value with spaces  \n")

            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
variables:
  spaces: { read: spaces.txt }

tasks:
  test:
    cmd: echo test
""")

            recipe = parse_recipe(recipe_path)
            self.assertEqual(recipe.variables["spaces"], "  value with spaces  ")

    def test_file_read_relative_path(self):
        """Test relative path resolves from recipe file."""
        with TemporaryDirectory() as tmpdir:
            data_file = Path(tmpdir) / "data.txt"
            data_file.write_text("content")

            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
variables:
  data: { read: data.txt }

tasks:
  test:
    cmd: echo test
""")

            recipe = parse_recipe(recipe_path)
            self.assertEqual(recipe.variables["data"], "content")

    def test_file_read_nested_relative_path(self):
        """Test nested relative path like secrets/api-key.txt."""
        with TemporaryDirectory() as tmpdir:
            secrets_dir = Path(tmpdir) / "secrets"
            secrets_dir.mkdir()

            data_file = secrets_dir / "api-key.txt"
            data_file.write_text("secret-key")

            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
variables:
  api_key: { read: secrets/api-key.txt }

tasks:
  test:
    cmd: echo test
""")

            recipe = parse_recipe(recipe_path)
            self.assertEqual(recipe.variables["api_key"], "secret-key")

    def test_file_read_absolute_path(self):
        """Test absolute paths work."""
        with TemporaryDirectory() as tmpdir:
            data_file = Path(tmpdir) / "absolute.txt"
            data_file.write_text("absolute-content")

            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(f"""
variables:
  data: {{ read: {data_file} }}

tasks:
  test:
    cmd: echo test
""")

            recipe = parse_recipe(recipe_path)
            self.assertEqual(recipe.variables["data"], "absolute-content")

    def test_file_read_tilde_expansion(self):
        """Test tilde expands to home directory."""
        import os
        home = Path.home()

        with TemporaryDirectory() as tmpdir:
            # Create a temp file in home directory
            test_file = home / ".test-tasktree-file-read.txt"
            try:
                test_file.write_text("home-content")

                recipe_path = Path(tmpdir) / "tasktree.yaml"
                recipe_path.write_text("""
variables:
  data: { read: ~/.test-tasktree-file-read.txt }

tasks:
  test:
    cmd: echo test
""")

                recipe = parse_recipe(recipe_path)
                self.assertEqual(recipe.variables["data"], "home-content")

            finally:
                if test_file.exists():
                    test_file.unlink()

    def test_file_read_file_not_found(self):
        """Test error when file doesn't exist."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
variables:
  missing: { read: nonexistent.txt }

tasks:
  test:
    cmd: echo test
""")

            with self.assertRaises(ValueError) as ctx:
                parse_recipe(recipe_path)

            self.assertIn("Failed to read file", str(ctx.exception))
            self.assertIn("nonexistent.txt", str(ctx.exception))
            self.assertIn("File not found", str(ctx.exception))

    def test_file_read_invalid_utf8(self):
        """Test error for binary file."""
        with TemporaryDirectory() as tmpdir:
            # Create binary file
            data_file = Path(tmpdir) / "binary.dat"
            data_file.write_bytes(b'\x80\x81\x82\x83')

            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
variables:
  binary: { read: binary.dat }

tasks:
  test:
    cmd: echo test
""")

            with self.assertRaises(ValueError) as ctx:
                parse_recipe(recipe_path)

            self.assertIn("invalid UTF-8", str(ctx.exception))
            self.assertIn("text files", str(ctx.exception))

    def test_file_read_in_variable_expansion(self):
        """Test file content used in other variables."""
        with TemporaryDirectory() as tmpdir:
            data_file = Path(tmpdir) / "base.txt"
            data_file.write_text("https://api.example.com")

            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
variables:
  base_url: { read: base.txt }
  users_endpoint: "{{ var.base_url }}/users"

tasks:
  test:
    cmd: echo test
""")

            recipe = parse_recipe(recipe_path)
            self.assertEqual(recipe.variables["base_url"], "https://api.example.com")
            self.assertEqual(recipe.variables["users_endpoint"], "https://api.example.com/users")

    def test_file_read_invalid_syntax_extra_keys(self):
        """Test error for extra keys in file read reference."""
        with TemporaryDirectory() as tmpdir:
            data_file = Path(tmpdir) / "data.txt"
            data_file.write_text("content")

            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
variables:
  data: { read: data.txt, default: "foo" }

tasks:
  test:
    cmd: echo test
""")

            with self.assertRaises(ValueError) as ctx:
                parse_recipe(recipe_path)

            self.assertIn("Invalid file read reference", str(ctx.exception))
            self.assertIn("extra keys", str(ctx.exception).lower())

    def test_file_read_invalid_syntax_empty_path(self):
        """Test error for empty filepath."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
variables:
  data: { read: }

tasks:
  test:
    cmd: echo test
""")

            with self.assertRaises(ValueError) as ctx:
                parse_recipe(recipe_path)

            self.assertIn("Invalid file read reference", str(ctx.exception))
            self.assertIn("non-empty string", str(ctx.exception))

    def test_file_read_mixed_with_env_and_regular(self):
        """Test all three variable types together."""
        # Set environment variable for test
        os.environ["TEST_ENV_VAR"] = "env-value"

        try:
            with TemporaryDirectory() as tmpdir:
                data_file = Path(tmpdir) / "file-value.txt"
                data_file.write_text("file-value")

                recipe_path = Path(tmpdir) / "tasktree.yaml"
                recipe_path.write_text("""
variables:
  regular: "regular-value"
  from_env: { env: TEST_ENV_VAR }
  from_file: { read: file-value.txt }

tasks:
  test:
    cmd: echo test
""")

                recipe = parse_recipe(recipe_path)
                self.assertEqual(recipe.variables["regular"], "regular-value")
                self.assertEqual(recipe.variables["from_env"], "env-value")
                self.assertEqual(recipe.variables["from_file"], "file-value")

        finally:
            del os.environ["TEST_ENV_VAR"]


class TestEvalVariables(unittest.TestCase):
    """Tests for { eval: command } variable references."""

    def test_eval_basic_command(self):
        """Test basic command evaluation."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
variables:
  greeting: { eval: "echo hello" }

tasks:
  test:
    cmd: echo "{{ var.greeting }}"
"""
            )

            recipe = parse_recipe(recipe_path)
            self.assertEqual(recipe.variables["greeting"], "hello")

    def test_eval_strips_trailing_newline(self):
        """Test that trailing newline is stripped from command output."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            # echo produces output with trailing newline
            recipe_path.write_text(
                """
variables:
  output: { eval: "echo test" }

tasks:
  test:
    cmd: echo done
"""
            )

            recipe = parse_recipe(recipe_path)
            # Should strip the trailing newline
            self.assertEqual(recipe.variables["output"], "test")

    def test_eval_preserves_internal_newlines(self):
        """Test that internal newlines are preserved."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            if platform.system() == "Windows":
                # Windows cmd uses echo. for blank lines
                cmd = 'echo line1 && echo. && echo line2'
            else:
                cmd = "echo -e 'line1\\nline2'"
            recipe_path.write_text(
                f"""
variables:
  lines: {{ eval: "{cmd}" }}

tasks:
  test:
    cmd: echo done
"""
            )

            recipe = parse_recipe(recipe_path)
            # Should have internal newline but not trailing one
            self.assertIn("\n", recipe.variables["lines"])

    def test_eval_empty_output(self):
        """Test command with empty output."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            if platform.system() == "Windows":
                cmd = "cmd /c exit 0"
            else:
                cmd = "true"
            recipe_path.write_text(
                f"""
variables:
  empty: {{ eval: "{cmd}" }}

tasks:
  test:
    cmd: echo done
"""
            )

            recipe = parse_recipe(recipe_path)
            self.assertEqual(recipe.variables["empty"], "")

    def test_eval_command_failure(self):
        """Test that non-zero exit code raises error."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            if platform.system() == "Windows":
                cmd = "cmd /c exit 1"
            else:
                cmd = "false"
            recipe_path.write_text(
                f"""
variables:
  bad: {{ eval: "{cmd}" }}

tasks:
  test:
    cmd: echo done
"""
            )

            with self.assertRaises(ValueError) as cm:
                parse_recipe(recipe_path)
            error_msg = str(cm.exception)
            self.assertIn("Command failed", error_msg)
            self.assertIn("bad", error_msg)
            self.assertIn("Exit code:", error_msg)

    def test_eval_nonexistent_command(self):
        """Test that nonexistent command produces helpful error."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
variables:
  bad: { eval: "nonexistent-command-xyz" }

tasks:
  test:
    cmd: echo done
"""
            )

            with self.assertRaises(ValueError) as cm:
                parse_recipe(recipe_path)
            error_msg = str(cm.exception)
            self.assertIn("Command failed", error_msg)
            self.assertIn("bad", error_msg)

    def test_eval_working_directory(self):
        """Test that command runs from recipe file directory."""
        with TemporaryDirectory() as tmpdir:
            # Create a marker file
            marker_file = Path(tmpdir) / "marker.txt"
            marker_file.write_text("found")

            recipe_path = Path(tmpdir) / "tasktree.yaml"
            if platform.system() == "Windows":
                cmd = "type marker.txt"
            else:
                cmd = "cat marker.txt"
            recipe_path.write_text(
                f"""
variables:
  marker: {{ eval: "{cmd}" }}

tasks:
  test:
    cmd: echo done
"""
            )

            recipe = parse_recipe(recipe_path)
            self.assertEqual(recipe.variables["marker"], "found")

    def test_eval_with_variable_substitution(self):
        """Test eval output can use variable substitution."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
variables:
  prefix: "hello"
  suffix: { eval: "echo world" }
  combined: "{{ var.prefix }}-{{ var.suffix }}"

tasks:
  test:
    cmd: echo done
"""
            )

            recipe = parse_recipe(recipe_path)
            self.assertEqual(recipe.variables["suffix"], "world")
            self.assertEqual(recipe.variables["combined"], "hello-world")

    def test_eval_in_variable_substitution(self):
        """Test that eval output itself can contain variable references."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
variables:
  base: "test"
  # Command outputs a string with variable reference
  template: { eval: "echo '{{ var.base }}-value'" }

tasks:
  test:
    cmd: echo done
"""
            )

            recipe = parse_recipe(recipe_path)
            # The output should have the variable substituted
            self.assertEqual(recipe.variables["template"], "test-value")

    def test_eval_validation_missing_command(self):
        """Test validation error when eval has no command."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
variables:
  bad: { eval: }

tasks:
  test:
    cmd: echo done
"""
            )

            with self.assertRaises(ValueError) as cm:
                parse_recipe(recipe_path)
            error_msg = str(cm.exception)
            self.assertIn("Invalid eval reference", error_msg)
            self.assertIn("bad", error_msg)

    def test_eval_validation_extra_keys(self):
        """Test validation error when eval has extra keys."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
variables:
  bad: { eval: "echo test", timeout: 5 }

tasks:
  test:
    cmd: echo done
"""
            )

            with self.assertRaises(ValueError) as cm:
                parse_recipe(recipe_path)
            error_msg = str(cm.exception)
            self.assertIn("Invalid eval reference", error_msg)
            self.assertIn("extra keys", error_msg)
            self.assertIn("timeout", error_msg)

    def test_eval_validation_non_string_command(self):
        """Test validation error when command is not a string."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
variables:
  bad: { eval: 123 }

tasks:
  test:
    cmd: echo done
"""
            )

            with self.assertRaises(ValueError) as cm:
                parse_recipe(recipe_path)
            error_msg = str(cm.exception)
            self.assertIn("Invalid eval reference", error_msg)
            self.assertIn("must be a non-empty string", error_msg)

    def test_eval_uses_default_env(self):
        """Test that eval uses default environment if specified."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            # This tests that the environment resolution works
            # We use a simple command that works in both bash and cmd
            recipe_path.write_text(
                """
environments:
  default: bash-env
  bash-env:
    shell: bash
    args: ["-c"]

variables:
  result: { eval: "echo test" }

tasks:
  test:
    cmd: echo done
"""
            )

            recipe = parse_recipe(recipe_path)
            self.assertEqual(recipe.variables["result"], "test")

    def test_eval_with_pipes_and_redirection(self):
        """Test that commands with pipes work correctly."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            if platform.system() == "Windows":
                # Windows cmd piping
                cmd = 'echo test | findstr test'
            else:
                cmd = "echo test | grep test"
            recipe_path.write_text(
                f"""
variables:
  filtered: {{ eval: "{cmd}" }}

tasks:
  test:
    cmd: echo done
"""
            )

            recipe = parse_recipe(recipe_path)
            self.assertEqual(recipe.variables["filtered"], "test")

    def test_eval_mixed_with_other_variable_types(self):
        """Test eval works alongside env and read variables."""
        with TemporaryDirectory() as tmpdir:
            # Setup environment variable
            os.environ["TEST_EVAL_VAR"] = "env-value"

            # Create file to read
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("file-value\n")

            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
variables:
  from_env: { env: TEST_EVAL_VAR }
  from_file: { read: "test.txt" }
  from_eval: { eval: "echo eval-value" }
  combined: "{{ var.from_env }}-{{ var.from_file }}-{{ var.from_eval }}"

tasks:
  test:
    cmd: echo done
"""
            )

            try:
                recipe = parse_recipe(recipe_path)
                self.assertEqual(recipe.variables["from_env"], "env-value")
                self.assertEqual(recipe.variables["from_file"], "file-value")
                self.assertEqual(recipe.variables["from_eval"], "eval-value")
                self.assertEqual(recipe.variables["combined"], "env-value-file-value-eval-value")
            finally:
                del os.environ["TEST_EVAL_VAR"]


if __name__ == "__main__":
    unittest.main()
