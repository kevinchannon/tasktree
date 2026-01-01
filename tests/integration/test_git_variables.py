"""Integration tests for git variables feature."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from tasktree.executor import Executor
from tasktree.parser import parse_recipe
from tasktree.state import StateManager


class TestGitVariables(unittest.TestCase):
    """Test git variable substitution in task execution."""

    def setUp(self):
        """Create temporary git repository for testing."""
        self.test_dir = tempfile.mkdtemp()
        self.recipe_file = Path(self.test_dir) / "tasktree.yaml"

        # Initialize git repo
        subprocess.run(['git', 'init'], cwd=self.test_dir, check=True, capture_output=True)
        subprocess.run(['git', 'config', 'user.name', 'Integration Test'], cwd=self.test_dir, check=True, capture_output=True)
        subprocess.run(['git', 'config', 'user.email', 'integration@test.com'], cwd=self.test_dir, check=True, capture_output=True)

        # Create initial commit
        test_file = Path(self.test_dir) / 'initial.txt'
        test_file.write_text('initial content')
        subprocess.run(['git', 'add', '.'], cwd=self.test_dir, check=True, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'Initial commit'], cwd=self.test_dir, check=True, capture_output=True)

        # Create a tag
        subprocess.run(['git', 'tag', 'v0.1.0'], cwd=self.test_dir, check=True, capture_output=True)

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_all_git_variables_in_command(self):
        """Test that all 8 git variables work in task commands."""
        output_file = Path(self.test_dir) / "output.txt"

        recipe_content = f"""
tasks:
  test-git-vars:
    cmd: |
      echo "commit={{{{ git.commit }}}}" > {output_file}
      echo "commit_short={{{{ git.commit_short }}}}" >> {output_file}
      echo "branch={{{{ git.branch }}}}" >> {output_file}
      echo "user_name={{{{ git.user_name }}}}" >> {output_file}
      echo "user_email={{{{ git.user_email }}}}" >> {output_file}
      echo "tag={{{{ git.tag }}}}" >> {output_file}
      echo "describe={{{{ git.describe }}}}" >> {output_file}
      echo "is_dirty={{{{ git.is_dirty }}}}" >> {output_file}
"""
        self.recipe_file.write_text(recipe_content)

        # Parse recipe and execute task
        recipe = parse_recipe(self.recipe_file)
        state = StateManager(recipe.project_root)
        state.load()
        executor = Executor(recipe, state)
        executor.execute_task("test-git-vars")

        # Read output and verify
        output = output_file.read_text()
        lines = {line.split("=", 1)[0]: line.split("=", 1)[1] for line in output.strip().split("\n")}

        # Verify all variables were substituted
        self.assertIn("commit", lines)
        self.assertEqual(len(lines["commit"]), 40)  # Full SHA is 40 chars

        self.assertIn("commit_short", lines)
        self.assertEqual(len(lines["commit_short"]), 7)  # Short SHA is typically 7 chars

        self.assertIn("branch", lines)
        self.assertRegex(lines["branch"], r"(master|main)")

        self.assertIn("user_name", lines)
        self.assertEqual(lines["user_name"], "Integration Test")

        self.assertIn("user_email", lines)
        self.assertEqual(lines["user_email"], "integration@test.com")

        self.assertIn("tag", lines)
        self.assertEqual(lines["tag"], "v0.1.0")

        self.assertIn("describe", lines)
        self.assertEqual(lines["describe"], "v0.1.0")

        self.assertIn("is_dirty", lines)
        self.assertEqual(lines["is_dirty"], "false")

    def test_git_variables_with_working_dir(self):
        """Test that git variables are resolved from task's working directory."""
        # Create subdirectory
        subdir = Path(self.test_dir) / "subdir"
        subdir.mkdir()
        output_file = Path(self.test_dir) / "branch.txt"

        recipe_content = f"""
tasks:
  test-workdir:
    working_dir: subdir
    cmd: echo "{{{{ git.branch }}}}" > {output_file}
"""
        self.recipe_file.write_text(recipe_content)

        recipe = parse_recipe(self.recipe_file)
        state = StateManager(recipe.project_root)
        state.load()
        executor = Executor(recipe, state)
        executor.execute_task("test-workdir")

        output = output_file.read_text().strip()
        # Should still get branch from parent git repo
        self.assertRegex(output, r"(master|main)")

    def test_git_variables_mixed_with_builtin_vars(self):
        """Test git variables work alongside built-in variables."""
        output_file = Path(self.test_dir) / "mixed.txt"

        recipe_content = f"""
tasks:
  mixed-vars:
    cmd: |
      echo "Task {{{{ tt.task_name }}}} on branch {{{{ git.branch }}}}" > {output_file}
      echo "User: {{{{ git.user_name }}}}" >> {output_file}
"""
        self.recipe_file.write_text(recipe_content)

        recipe = parse_recipe(self.recipe_file)
        state = StateManager(recipe.project_root)
        state.load()
        executor = Executor(recipe, state)
        executor.execute_task("mixed-vars")

        output = output_file.read_text()
        lines = [line for line in output.strip().split("\n")]

        self.assertRegex(lines[0], r"Task mixed-vars on branch (master|main)")
        self.assertIn("User: Integration Test", lines[1])

    def test_git_is_dirty_detects_changes(self):
        """Test {{ git.is_dirty }} correctly detects uncommitted changes."""
        output_file = Path(self.test_dir) / "dirty.txt"

        # First test - clean repo
        recipe_content = f"""
tasks:
  check-dirty:
    cmd: echo "{{{{ git.is_dirty }}}}" > {output_file}
"""
        self.recipe_file.write_text(recipe_content)

        recipe = parse_recipe(self.recipe_file)
        state = StateManager(recipe.project_root)
        state.load()
        executor = Executor(recipe, state)
        executor.execute_task("check-dirty")

        output = output_file.read_text().strip()
        self.assertEqual(output, "false")

        # Make uncommitted change
        test_file = Path(self.test_dir) / 'modified.txt'
        test_file.write_text('new content')

        # Second test - dirty repo
        executor2 = Executor(recipe, state)  # New executor with fresh git cache
        executor2.execute_task("check-dirty", force=True)

        output = output_file.read_text().strip()
        self.assertEqual(output, "true")

    def test_git_describe_after_tag(self):
        """Test {{ git.describe }} with commits after tag."""
        # Create another commit after tag
        test_file = Path(self.test_dir) / 'after_tag.txt'
        test_file.write_text('after tag')
        subprocess.run(['git', 'add', '.'], cwd=self.test_dir, check=True, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'After tag'], cwd=self.test_dir, check=True, capture_output=True)

        output_file = Path(self.test_dir) / "describe.txt"

        recipe_content = f"""
tasks:
  test-describe:
    cmd: echo "{{{{ git.describe }}}}" > {output_file}
"""
        self.recipe_file.write_text(recipe_content)

        recipe = parse_recipe(self.recipe_file)
        state = StateManager(recipe.project_root)
        state.load()
        executor = Executor(recipe, state)
        executor.execute_task("test-describe")

        output = output_file.read_text().strip()
        # Should be like "v0.1.0-1-g<short-sha>"
        self.assertRegex(output, r"v0\.1\.0-1-g[a-f0-9]{7}")

    def test_git_variables_in_conditional_command(self):
        """Test using git variables in conditional logic."""
        output_file = Path(self.test_dir) / "conditional.txt"

        recipe_content = f"""
tasks:
  conditional-deploy:
    cmd: |
      if [ "{{{{ git.is_dirty }}}}" = "true" ]; then
        echo "BLOCKED: uncommitted changes" > {output_file}
      else
        echo "DEPLOY: {{{{ git.describe }}}}" > {output_file}
      fi
"""
        self.recipe_file.write_text(recipe_content)

        recipe = parse_recipe(self.recipe_file)
        state = StateManager(recipe.project_root)
        state.load()
        executor = Executor(recipe, state)
        executor.execute_task("conditional-deploy")

        output = output_file.read_text().strip()
        # Clean repo should deploy
        self.assertEqual(output, "DEPLOY: v0.1.0")

    def test_git_variables_cached_within_executor(self):
        """Test that git variables are cached within a single executor instance."""
        output_file = Path(self.test_dir) / "cached.txt"

        recipe_content = f"""
tasks:
  task1:
    cmd: echo "{{{{ git.commit }}}}" > {output_file}

  task2:
    deps: [task1]
    cmd: echo "{{{{ git.commit }}}}" >> {output_file}
"""
        self.recipe_file.write_text(recipe_content)

        recipe = parse_recipe(self.recipe_file)
        state = StateManager(recipe.project_root)
        state.load()
        executor = Executor(recipe, state)
        executor.execute_task("task2")

        # Both tasks should have written the same commit SHA
        output = output_file.read_text().strip()
        lines = output.split("\n")
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0], lines[1])  # Same commit SHA

    def test_git_variable_error_handling_not_in_repo(self):
        """Test clear error when git variable used outside git repo."""
        # Create non-git subdirectory
        non_git_dir = Path(self.test_dir) / "non-git"
        non_git_dir.mkdir()
        recipe_in_non_git = non_git_dir / "tasktree.yaml"

        recipe_content = """
tasks:
  fail-task:
    cmd: echo "{{ git.commit }}"
"""
        recipe_in_non_git.write_text(recipe_content)

        # Parse recipe and try to execute
        from tasktree.executor import ExecutionError

        recipe = parse_recipe(recipe_in_non_git)
        state = StateManager(recipe.project_root)
        state.load()
        executor = Executor(recipe, state)

        with self.assertRaises(ExecutionError) as cm:
            executor.execute_task("fail-task")

        self.assertIn("git.commit", str(cm.exception))

    def test_git_tag_error_when_no_tags(self):
        """Test clear error when git.tag used but no tags exist."""
        # Create new git repo without tags
        new_dir = tempfile.mkdtemp()
        try:
            subprocess.run(['git', 'init'], cwd=new_dir, check=True, capture_output=True)
            subprocess.run(['git', 'config', 'user.name', 'Test'], cwd=new_dir, check=True, capture_output=True)
            subprocess.run(['git', 'config', 'user.email', 'test@test.com'], cwd=new_dir, check=True, capture_output=True)

            test_file = Path(new_dir) / 'file.txt'
            test_file.write_text('content')
            subprocess.run(['git', 'add', '.'], cwd=new_dir, check=True, capture_output=True)
            subprocess.run(['git', 'commit', '-m', 'Commit'], cwd=new_dir, check=True, capture_output=True)

            recipe_file = Path(new_dir) / "tasktree.yaml"
            recipe_content = """
tasks:
  fail-task:
    cmd: echo "{{ git.tag }}"
"""
            recipe_file.write_text(recipe_content)

            from tasktree.executor import ExecutionError

            recipe = parse_recipe(recipe_file)
            state = StateManager(recipe.project_root)
            state.load()
            executor = Executor(recipe, state)

            with self.assertRaises(ExecutionError) as cm:
                executor.execute_task("fail-task")

            self.assertIn("git.tag", str(cm.exception))
        finally:
            import shutil
            shutil.rmtree(new_dir, ignore_errors=True)

    def test_git_variables_in_version_stamping(self):
        """Test realistic version stamping use case."""
        version_file = Path(self.test_dir) / "VERSION"
        metadata_file = Path(self.test_dir) / "METADATA"

        recipe_content = f"""
tasks:
  stamp-version:
    cmd: |
      echo "{{{{ git.describe }}}}" > {version_file}
      echo "Built from {{{{ git.commit }}}} by {{{{ git.user_name }}}}" > {metadata_file}
"""
        self.recipe_file.write_text(recipe_content)

        recipe = parse_recipe(self.recipe_file)
        state = StateManager(recipe.project_root)
        state.load()
        executor = Executor(recipe, state)
        executor.execute_task("stamp-version")

        version = version_file.read_text().strip()
        metadata = metadata_file.read_text().strip()

        self.assertEqual(version, "v0.1.0")
        self.assertRegex(metadata, r"Built from [a-f0-9]{40} by Integration Test")


if __name__ == "__main__":
    unittest.main()
