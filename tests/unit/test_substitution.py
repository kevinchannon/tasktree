"""Unit tests for substitution module."""

import os
import unittest

from tasktree.substitution import (
    PLACEHOLDER_PATTERN,
    substitute_arguments,
    substitute_all,
    substitute_builtin_variables,
    substitute_environment,
    substitute_variables,
)


class TestPlaceholderPattern(unittest.TestCase):
    """Test the regex pattern for matching placeholders."""

    def test_pattern_matches_var_prefix(self):
        """Test pattern matches {{ var.name }} syntax."""
        match = PLACEHOLDER_PATTERN.search("{{ var.foo }}")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "var")
        self.assertEqual(match.group(2), "foo")

    def test_pattern_matches_arg_prefix(self):
        """Test pattern matches {{ arg.name }} syntax."""
        match = PLACEHOLDER_PATTERN.search("{{ arg.bar }}")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "arg")
        self.assertEqual(match.group(2), "bar")

    def test_pattern_matches_env_prefix(self):
        """Test pattern matches {{ env.name }} syntax."""
        match = PLACEHOLDER_PATTERN.search("{{ env.USER }}")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "env")
        self.assertEqual(match.group(2), "USER")

    def test_pattern_matches_tt_prefix(self):
        """Test pattern matches {{ tt.name }} syntax."""
        match = PLACEHOLDER_PATTERN.search("{{ tt.project_root }}")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "tt")
        self.assertEqual(match.group(2), "project_root")

    def test_pattern_allows_whitespace(self):
        """Test pattern tolerates extra whitespace."""
        test_cases = [
            "{{var.name}}",
            "{{ var.name }}",
            "{{ var.name }}",
            "{{  var  .  name  }}",
        ]
        for text in test_cases:
            with self.subTest(text=text):
                match = PLACEHOLDER_PATTERN.search(text)
                self.assertIsNotNone(match)
                self.assertEqual(match.group(1), "var")
                self.assertEqual(match.group(2), "name")

    def test_pattern_requires_valid_identifier(self):
        """Test pattern only matches valid identifier names."""
        # Valid identifiers
        valid = ["foo", "foo_bar", "foo123", "_private"]
        for name in valid:
            with self.subTest(name=name):
                match = PLACEHOLDER_PATTERN.search(f"{{{{ var.{name} }}}}")
                self.assertIsNotNone(match)

        # Invalid identifiers (should not match)
        invalid = ["123foo", "foo-bar", "foo.bar", "foo bar"]
        for name in invalid:
            with self.subTest(name=name):
                match = PLACEHOLDER_PATTERN.search(f"{{{{ var.{name} }}}}")
                self.assertIsNone(match)


class TestSubstituteVariables(unittest.TestCase):
    """Test substitute_variables function."""

    def test_substitute_single_variable(self):
        """Test basic {{ var.x }} substitution."""
        result = substitute_variables("Hello {{ var.name }}!", {"name": "World"})
        self.assertEqual(result, "Hello World!")

    def test_substitute_multiple_variables(self):
        """Test multiple different variables in same string."""
        text = "{{ var.greeting }} {{ var.name }}!"
        variables = {"greeting": "Hello", "name": "World"}
        result = substitute_variables(text, variables)
        self.assertEqual(result, "Hello World!")

    def test_substitute_same_variable_multiple_times(self):
        """Test same variable appears multiple times."""
        text = "{{ var.name }} says hello to {{ var.name }}"
        variables = {"name": "Alice"}
        result = substitute_variables(text, variables)
        self.assertEqual(result, "Alice says hello to Alice")

    def test_substitute_no_placeholders(self):
        """Test string without placeholders returns unchanged."""
        text = "No placeholders here"
        result = substitute_variables(text, {"foo": "bar"})
        self.assertEqual(result, text)

    def test_substitute_ignores_arg_prefix(self):
        """Test {{ arg.name }} is not substituted."""
        text = "{{ var.foo }} {{ arg.bar }}"
        variables = {"foo": "FOO", "bar": "BAR"}
        result = substitute_variables(text, variables)
        self.assertEqual(result, "FOO {{ arg.bar }}")

    def test_substitute_undefined_variable_raises(self):
        """Test error for undefined variable reference."""
        with self.assertRaises(ValueError) as cm:
            substitute_variables("{{ var.missing }}", {})
        self.assertIn("missing", str(cm.exception))
        self.assertIn("not defined", str(cm.exception))

    def test_substitute_with_whitespace_variations(self):
        """Test whitespace handling in placeholders."""
        variables = {"name": "World"}
        test_cases = [
            ("{{var.name}}", "World"),
            ("{{ var.name }}", "World"),
            ("{{ var.name }}", "World"),
            ("{{  var  .  name  }}", "World"),
        ]
        for text, expected in test_cases:
            with self.subTest(text=text):
                result = substitute_variables(text, variables)
                self.assertEqual(result, expected)

    def test_substitute_empty_string_value(self):
        """Test variable with empty string value."""
        result = substitute_variables("foo{{ var.x }}bar", {"x": ""})
        self.assertEqual(result, "foobar")

    def test_substitute_in_complex_text(self):
        """Test substitution in realistic command string."""
        text = 'echo "Deploying to {{ var.server }} on port {{ var.port }}"'
        variables = {"server": "production.example.com", "port": "8080"}
        result = substitute_variables(text, variables)
        self.assertEqual(
            result, 'echo "Deploying to production.example.com on port 8080"'
        )


class TestSubstituteArguments(unittest.TestCase):
    """Test substitute_arguments function."""

    def test_substitute_single_argument(self):
        """Test basic {{ arg.x }} substitution."""
        result = substitute_arguments("Hello {{ arg.name }}!", {"name": "World"})
        self.assertEqual(result, "Hello World!")

    def test_substitute_multiple_arguments(self):
        """Test multiple different arguments in same string."""
        text = "deploy {{ arg.app }} to {{ arg.region }}"
        args = {"app": "myapp", "region": "us-west-1"}
        result = substitute_arguments(text, args)
        self.assertEqual(result, "deploy myapp to us-west-1")

    def test_substitute_converts_types_to_strings(self):
        """Test int/bool/float values are converted to strings."""
        text = "port={{ arg.port }} debug={{ arg.debug }} timeout={{ arg.timeout }}"
        args = {"port": 8080, "debug": True, "timeout": 30.5}
        result = substitute_arguments(text, args)
        self.assertEqual(result, "port=8080 debug=True timeout=30.5")

    def test_substitute_ignores_var_prefix(self):
        """Test {{ var.name }} is not substituted."""
        text = "{{ arg.foo }} {{ var.bar }}"
        args = {"foo": "FOO", "bar": "BAR"}
        result = substitute_arguments(text, args)
        self.assertEqual(result, "FOO {{ var.bar }}")

    def test_substitute_undefined_argument_raises(self):
        """Test error for undefined argument reference."""
        with self.assertRaises(ValueError) as cm:
            substitute_arguments("{{ arg.missing }}", {})
        self.assertIn("missing", str(cm.exception))
        self.assertIn("not defined", str(cm.exception))

    def test_substitute_none_value(self):
        """Test None value is converted to string."""
        result = substitute_arguments("value={{ arg.x }}", {"x": None})
        self.assertEqual(result, "value=None")

    def test_exported_arg_raises_error_when_used_in_template(self):
        """Test that exported arguments cannot be used in template substitution."""
        exported_args = {"server"}
        args = {"port": 8080}  # Only non-exported args

        with self.assertRaises(ValueError) as cm:
            substitute_arguments("{{ arg.server }}", args, exported_args)

        self.assertIn("server", str(cm.exception))
        self.assertIn("exported", str(cm.exception))
        self.assertIn("$server", str(cm.exception))
        self.assertIn("environment variable", str(cm.exception))

    def test_regular_arg_works_with_exported_args_set(self):
        """Test that regular args still work when exported_args is provided."""
        exported_args = {"server"}
        args = {"port": 8080}

        result = substitute_arguments("port={{ arg.port }}", args, exported_args)
        self.assertEqual(result, "port=8080")

    def test_mixed_exported_and_regular_args(self):
        """Test mixing exported and regular args in substitution."""
        exported_args = {"server", "user"}
        args = {"port": 8080, "verbose": True}

        text = "port={{ arg.port }} debug={{ arg.verbose }}"
        result = substitute_arguments(text, args, exported_args)
        self.assertEqual(result, "port=8080 debug=True")

        # Exported arg should fail
        with self.assertRaises(ValueError):
            substitute_arguments("{{ arg.server }}", args, exported_args)


class TestSubstituteEnvironment(unittest.TestCase):
    """Test substitute_environment function."""

    def test_substitute_single_env_var(self):
        """Test basic {{ env.VAR }} substitution."""
        os.environ['TEST_VAR'] = 'test_value'
        try:
            result = substitute_environment("Hello {{ env.TEST_VAR }}!")
            self.assertEqual(result, "Hello test_value!")
        finally:
            del os.environ['TEST_VAR']

    def test_substitute_multiple_env_vars(self):
        """Test multiple different env vars in same string."""
        os.environ['VAR1'] = 'value1'
        os.environ['VAR2'] = 'value2'
        try:
            text = "{{ env.VAR1 }} and {{ env.VAR2 }}"
            result = substitute_environment(text)
            self.assertEqual(result, "value1 and value2")
        finally:
            del os.environ['VAR1']
            del os.environ['VAR2']

    def test_substitute_same_env_var_multiple_times(self):
        """Test same env var appears multiple times."""
        os.environ['USER'] = 'testuser'
        try:
            text = "{{ env.USER }} says hello to {{ env.USER }}"
            result = substitute_environment(text)
            self.assertEqual(result, "testuser says hello to testuser")
        finally:
            del os.environ['USER']

    def test_substitute_no_placeholders(self):
        """Test string without placeholders returns unchanged."""
        text = "No placeholders here"
        result = substitute_environment(text)
        self.assertEqual(result, text)

    def test_substitute_ignores_var_prefix(self):
        """Test {{ var.name }} is not substituted."""
        os.environ['FOO'] = 'env_foo'
        try:
            text = "{{ env.FOO }} {{ var.bar }}"
            result = substitute_environment(text)
            self.assertEqual(result, "env_foo {{ var.bar }}")
        finally:
            del os.environ['FOO']

    def test_substitute_ignores_arg_prefix(self):
        """Test {{ arg.name }} is not substituted."""
        os.environ['FOO'] = 'env_foo'
        try:
            text = "{{ env.FOO }} {{ arg.bar }}"
            result = substitute_environment(text)
            self.assertEqual(result, "env_foo {{ arg.bar }}")
        finally:
            del os.environ['FOO']

    def test_substitute_undefined_env_var_raises(self):
        """Test error for undefined environment variable."""
        # Make sure var is not set
        if 'DEFINITELY_NOT_SET_VAR' in os.environ:
            del os.environ['DEFINITELY_NOT_SET_VAR']

        with self.assertRaises(ValueError) as cm:
            substitute_environment("{{ env.DEFINITELY_NOT_SET_VAR }}")
        self.assertIn("DEFINITELY_NOT_SET_VAR", str(cm.exception))
        self.assertIn("not set", str(cm.exception))

    def test_substitute_with_whitespace_variations(self):
        """Test whitespace handling in placeholders."""
        os.environ['TEST_VAR'] = 'value'
        try:
            test_cases = [
                ("{{env.TEST_VAR}}", "value"),
                ("{{ env.TEST_VAR }}", "value"),
                ("{{  env  .  TEST_VAR  }}", "value"),
            ]
            for text, expected in test_cases:
                with self.subTest(text=text):
                    result = substitute_environment(text)
                    self.assertEqual(result, expected)
        finally:
            del os.environ['TEST_VAR']

    def test_substitute_empty_string_value(self):
        """Test env var with empty string value."""
        os.environ['EMPTY_VAR'] = ''
        try:
            result = substitute_environment("foo{{ env.EMPTY_VAR }}bar")
            self.assertEqual(result, "foobar")
        finally:
            del os.environ['EMPTY_VAR']

    def test_substitute_in_complex_command(self):
        """Test substitution in realistic command string."""
        os.environ['DEPLOY_USER'] = 'admin'
        os.environ['DEPLOY_HOST'] = 'prod.example.com'
        try:
            text = 'scp package.tar.gz {{ env.DEPLOY_USER }}@{{ env.DEPLOY_HOST }}:/opt/'
            result = substitute_environment(text)
            self.assertEqual(result, 'scp package.tar.gz admin@prod.example.com:/opt/')
        finally:
            del os.environ['DEPLOY_USER']
            del os.environ['DEPLOY_HOST']


class TestSubstituteBuiltinVariables(unittest.TestCase):
    """Test substitute_builtin_variables function."""

    def test_substitute_single_builtin_var(self):
        """Test basic {{ tt.x }} substitution."""
        builtin_vars = {"project_root": "/home/user/project"}
        result = substitute_builtin_variables("Root: {{ tt.project_root }}", builtin_vars)
        self.assertEqual(result, "Root: /home/user/project")

    def test_substitute_multiple_builtin_vars(self):
        """Test multiple different built-in vars in same string."""
        builtin_vars = {
            "project_root": "/home/user/project",
            "task_name": "build",
        }
        text = "Task {{ tt.task_name }} in {{ tt.project_root }}"
        result = substitute_builtin_variables(text, builtin_vars)
        self.assertEqual(result, "Task build in /home/user/project")

    def test_substitute_all_builtin_vars(self):
        """Test all 8 built-in variables."""
        builtin_vars = {
            "project_root": "/home/user/project",
            "recipe_dir": "/home/user/project",
            "task_name": "build",
            "working_dir": "/home/user/project/src",
            "timestamp": "2024-12-28T14:30:45Z",
            "timestamp_unix": "1703772645",
            "user_home": "/home/user",
            "user_name": "alice",
        }
        text = (
            "Project: {{ tt.project_root }}, "
            "Recipe: {{ tt.recipe_dir }}, "
            "Task: {{ tt.task_name }}, "
            "Working: {{ tt.working_dir }}, "
            "Time: {{ tt.timestamp }}, "
            "Unix: {{ tt.timestamp_unix }}, "
            "Home: {{ tt.user_home }}, "
            "User: {{ tt.user_name }}"
        )
        result = substitute_builtin_variables(text, builtin_vars)
        self.assertEqual(
            result,
            "Project: /home/user/project, "
            "Recipe: /home/user/project, "
            "Task: build, "
            "Working: /home/user/project/src, "
            "Time: 2024-12-28T14:30:45Z, "
            "Unix: 1703772645, "
            "Home: /home/user, "
            "User: alice",
        )

    def test_substitute_same_builtin_var_multiple_times(self):
        """Test same built-in var appears multiple times."""
        builtin_vars = {"task_name": "build"}
        text = "{{ tt.task_name }} depends on {{ tt.task_name }}"
        result = substitute_builtin_variables(text, builtin_vars)
        self.assertEqual(result, "build depends on build")

    def test_substitute_no_placeholders(self):
        """Test string without placeholders returns unchanged."""
        builtin_vars = {"project_root": "/home/user/project"}
        text = "No placeholders here"
        result = substitute_builtin_variables(text, builtin_vars)
        self.assertEqual(result, text)

    def test_substitute_ignores_var_prefix(self):
        """Test {{ var.name }} is not substituted."""
        builtin_vars = {"project_root": "/home/user/project"}
        text = "{{ tt.project_root }} {{ var.foo }}"
        result = substitute_builtin_variables(text, builtin_vars)
        self.assertEqual(result, "/home/user/project {{ var.foo }}")

    def test_substitute_ignores_arg_prefix(self):
        """Test {{ arg.name }} is not substituted."""
        builtin_vars = {"project_root": "/home/user/project"}
        text = "{{ tt.project_root }} {{ arg.foo }}"
        result = substitute_builtin_variables(text, builtin_vars)
        self.assertEqual(result, "/home/user/project {{ arg.foo }}")

    def test_substitute_ignores_env_prefix(self):
        """Test {{ env.NAME }} is not substituted."""
        builtin_vars = {"project_root": "/home/user/project"}
        text = "{{ tt.project_root }} {{ env.USER }}"
        result = substitute_builtin_variables(text, builtin_vars)
        self.assertEqual(result, "/home/user/project {{ env.USER }}")

    def test_substitute_undefined_builtin_var_raises(self):
        """Test error for undefined built-in variable."""
        builtin_vars = {"project_root": "/home/user/project"}
        with self.assertRaises(ValueError) as cm:
            substitute_builtin_variables("{{ tt.missing }}", builtin_vars)
        self.assertIn("missing", str(cm.exception))
        self.assertIn("not defined", str(cm.exception))

    def test_substitute_with_whitespace_variations(self):
        """Test whitespace handling in placeholders."""
        builtin_vars = {"task_name": "build"}
        test_cases = [
            ("{{tt.task_name}}", "build"),
            ("{{ tt.task_name }}", "build"),
            ("{{ tt.task_name }}", "build"),
            ("{{  tt  .  task_name  }}", "build"),
        ]
        for text, expected in test_cases:
            with self.subTest(text=text):
                result = substitute_builtin_variables(text, builtin_vars)
                self.assertEqual(result, expected)

    def test_substitute_in_realistic_command(self):
        """Test substitution in realistic command string."""
        builtin_vars = {
            "project_root": "/home/user/project",
            "timestamp_unix": "1703772645",
        }
        text = 'tar czf {{ tt.project_root }}/dist/app-{{ tt.timestamp_unix }}.tar.gz .'
        result = substitute_builtin_variables(text, builtin_vars)
        self.assertEqual(result, 'tar czf /home/user/project/dist/app-1703772645.tar.gz .')


class TestSubstituteAll(unittest.TestCase):
    """Test substitute_all function."""

    def test_substitute_both_var_and_arg(self):
        """Test both variables and arguments are substituted."""
        text = "{{ var.server }} {{ arg.port }}"
        variables = {"server": "example.com"}
        args = {"port": 8080}
        result = substitute_all(text, variables, args)
        self.assertEqual(result, "example.com 8080")

    def test_variables_substituted_before_arguments(self):
        """Test variables are substituted first, then arguments."""
        # If a variable contains {{ arg.x }}, it should remain for arg substitution
        text = "{{ var.template }}"
        variables = {"template": "port={{ arg.port }}"}
        args = {"port": 9000}
        result = substitute_all(text, variables, args)
        self.assertEqual(result, "port=9000")

    def test_substitute_mixed_placeholders(self):
        """Test realistic case with both types."""
        text = 'echo "Deploy {{ arg.app }} to {{ var.server }}:{{ var.port }}"'
        variables = {"server": "prod.example.com", "port": "8080"}
        args = {"app": "myservice"}
        result = substitute_all(text, variables, args)
        self.assertEqual(result, 'echo "Deploy myservice to prod.example.com:8080"')

    def test_substitute_all_empty_dicts(self):
        """Test with no variables or arguments."""
        text = "No placeholders"
        result = substitute_all(text, {}, {})
        self.assertEqual(result, text)

    def test_substitute_all_three_types(self):
        """Test variables, arguments, and environment all work together."""
        os.environ['ENV_VAR'] = 'from_env'
        try:
            text = "{{ var.v }} {{ arg.a }} {{ env.ENV_VAR }}"
            variables = {"v": "from_var"}
            args = {"a": "from_arg"}
            result = substitute_all(text, variables, args)
            self.assertEqual(result, "from_var from_arg from_env")
        finally:
            del os.environ['ENV_VAR']

    def test_substitute_order_var_then_arg_then_env(self):
        """Test substitution happens in correct order."""
        os.environ['PORT'] = '9000'
        try:
            # Variable contains arg placeholder, which contains env placeholder
            text = "{{ var.template }}"
            variables = {"template": "server={{ arg.server }}"}
            args = {"server": "host:{{ env.PORT }}"}
            result = substitute_all(text, variables, args)
            self.assertEqual(result, "server=host:9000")
        finally:
            del os.environ['PORT']


class TestSubstituteGitVariables(unittest.TestCase):
    """Test substitute_git_variables function."""

    def setUp(self):
        """Create a temporary git repository for testing."""
        import tempfile
        import subprocess
        import shutil

        # Create temporary directory
        self.test_dir = tempfile.mkdtemp()

        # Initialize git repo
        subprocess.run(['git', 'init'], cwd=self.test_dir, check=True, capture_output=True)
        subprocess.run(['git', 'config', 'user.name', 'Test User'], cwd=self.test_dir, check=True, capture_output=True)
        subprocess.run(['git', 'config', 'user.email', 'test@example.com'], cwd=self.test_dir, check=True, capture_output=True)

        # Create initial commit
        test_file = os.path.join(self.test_dir, 'test.txt')
        with open(test_file, 'w') as f:
            f.write('test content')
        subprocess.run(['git', 'add', '.'], cwd=self.test_dir, check=True, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'Initial commit'], cwd=self.test_dir, check=True, capture_output=True)

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_substitute_git_commit(self):
        """Test {{ git.commit }} returns full commit SHA."""
        from tasktree.substitution import substitute_git_variables
        import subprocess

        # Get expected commit SHA
        result = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=self.test_dir, capture_output=True, text=True, check=True)
        expected_commit = result.stdout.strip()

        text = "Commit: {{ git.commit }}"
        output = substitute_git_variables(text, self.test_dir)
        self.assertEqual(output, f"Commit: {expected_commit}")
        self.assertEqual(len(expected_commit), 40)  # Full SHA is 40 chars

    def test_substitute_git_commit_short(self):
        """Test {{ git.commit_short }} returns short commit SHA."""
        from tasktree.substitution import substitute_git_variables
        import subprocess

        # Get expected short commit SHA
        result = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=self.test_dir, capture_output=True, text=True, check=True)
        expected_commit_short = result.stdout.strip()

        text = "Short: {{ git.commit_short }}"
        output = substitute_git_variables(text, self.test_dir)
        self.assertEqual(output, f"Short: {expected_commit_short}")
        self.assertEqual(len(expected_commit_short), 7)  # Short SHA is typically 7 chars

    def test_substitute_git_branch(self):
        """Test {{ git.branch }} returns current branch name."""
        from tasktree.substitution import substitute_git_variables

        text = "Branch: {{ git.branch }}"
        output = substitute_git_variables(text, self.test_dir)
        # Default branch is usually 'master' or 'main'
        self.assertRegex(output, r"Branch: (master|main)")

    def test_substitute_git_user_name(self):
        """Test {{ git.user_name }} returns git user name."""
        from tasktree.substitution import substitute_git_variables

        text = "User: {{ git.user_name }}"
        output = substitute_git_variables(text, self.test_dir)
        self.assertEqual(output, "User: Test User")

    def test_substitute_git_user_email(self):
        """Test {{ git.user_email }} returns git user email."""
        from tasktree.substitution import substitute_git_variables

        text = "Email: {{ git.user_email }}"
        output = substitute_git_variables(text, self.test_dir)
        self.assertEqual(output, "Email: test@example.com")

    def test_substitute_git_tag_with_tag(self):
        """Test {{ git.tag }} returns most recent tag."""
        from tasktree.substitution import substitute_git_variables
        import subprocess

        # Create a tag
        subprocess.run(['git', 'tag', 'v1.0.0'], cwd=self.test_dir, check=True, capture_output=True)

        text = "Tag: {{ git.tag }}"
        output = substitute_git_variables(text, self.test_dir)
        self.assertEqual(output, "Tag: v1.0.0")

    def test_substitute_git_tag_no_tags_raises_error(self):
        """Test {{ git.tag }} raises error when no tags exist."""
        from tasktree.substitution import substitute_git_variables

        text = "Tag: {{ git.tag }}"
        with self.assertRaises(ValueError) as cm:
            substitute_git_variables(text, self.test_dir)
        self.assertIn("git.tag", str(cm.exception))

    def test_substitute_git_describe_with_tag(self):
        """Test {{ git.describe }} with tags."""
        from tasktree.substitution import substitute_git_variables
        import subprocess

        # Create a tag
        subprocess.run(['git', 'tag', 'v1.2.3'], cwd=self.test_dir, check=True, capture_output=True)

        text = "Describe: {{ git.describe }}"
        output = substitute_git_variables(text, self.test_dir)
        self.assertEqual(output, "Describe: v1.2.3")

    def test_substitute_git_describe_with_commits_after_tag(self):
        """Test {{ git.describe }} with commits after tag."""
        from tasktree.substitution import substitute_git_variables
        import subprocess

        # Create a tag
        subprocess.run(['git', 'tag', 'v1.0.0'], cwd=self.test_dir, check=True, capture_output=True)

        # Create another commit
        test_file = os.path.join(self.test_dir, 'test2.txt')
        with open(test_file, 'w') as f:
            f.write('more content')
        subprocess.run(['git', 'add', '.'], cwd=self.test_dir, check=True, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'Second commit'], cwd=self.test_dir, check=True, capture_output=True)

        text = "Describe: {{ git.describe }}"
        output = substitute_git_variables(text, self.test_dir)
        # Should be like "v1.0.0-1-g<short-sha>"
        self.assertRegex(output, r"Describe: v1\.0\.0-1-g[a-f0-9]{7}")

    def test_substitute_git_is_dirty_clean(self):
        """Test {{ git.is_dirty }} returns false for clean repo."""
        from tasktree.substitution import substitute_git_variables

        text = "Dirty: {{ git.is_dirty }}"
        output = substitute_git_variables(text, self.test_dir)
        self.assertEqual(output, "Dirty: false")

    def test_substitute_git_is_dirty_with_changes(self):
        """Test {{ git.is_dirty }} returns true with uncommitted changes."""
        from tasktree.substitution import substitute_git_variables

        # Make uncommitted change
        test_file = os.path.join(self.test_dir, 'test.txt')
        with open(test_file, 'w') as f:
            f.write('modified content')

        text = "Dirty: {{ git.is_dirty }}"
        output = substitute_git_variables(text, self.test_dir)
        self.assertEqual(output, "Dirty: true")

    def test_substitute_git_is_dirty_with_staged_changes(self):
        """Test {{ git.is_dirty }} returns true with staged changes."""
        from tasktree.substitution import substitute_git_variables
        import subprocess

        # Make staged change
        test_file = os.path.join(self.test_dir, 'staged.txt')
        with open(test_file, 'w') as f:
            f.write('staged content')
        subprocess.run(['git', 'add', '.'], cwd=self.test_dir, check=True, capture_output=True)

        text = "Dirty: {{ git.is_dirty }}"
        output = substitute_git_variables(text, self.test_dir)
        self.assertEqual(output, "Dirty: true")

    def test_substitute_multiple_git_variables(self):
        """Test multiple git variables in same string."""
        from tasktree.substitution import substitute_git_variables

        text = "{{ git.user_name }} <{{ git.user_email }}> on {{ git.branch }}"
        output = substitute_git_variables(text, self.test_dir)
        self.assertRegex(output, r"Test User <test@example\.com> on (master|main)")

    def test_substitute_same_git_variable_multiple_times(self):
        """Test same git variable appears multiple times."""
        from tasktree.substitution import substitute_git_variables

        text = "{{ git.branch }} {{ git.branch }}"
        output = substitute_git_variables(text, self.test_dir)
        self.assertRegex(output, r"(master|main) (master|main)")

    def test_git_variables_use_cache(self):
        """Test that git variables are cached to avoid repeated subprocess calls."""
        from tasktree.substitution import substitute_git_variables

        cache = {}
        text1 = "Branch: {{ git.branch }}"
        text2 = "Branch again: {{ git.branch }}"

        # First call - should populate cache
        output1 = substitute_git_variables(text1, self.test_dir, cache)
        self.assertIn('branch', cache)

        # Second call - should use cache
        cached_value = cache['branch']
        output2 = substitute_git_variables(text2, self.test_dir, cache)

        # Cache should still have same value
        self.assertEqual(cache['branch'], cached_value)
        self.assertRegex(output1, r"Branch: (master|main)")
        self.assertRegex(output2, r"Branch again: (master|main)")

    def test_substitute_git_not_in_repo_raises_error(self):
        """Test git variables raise error when not in git repository."""
        from tasktree.substitution import substitute_git_variables
        import tempfile

        # Create non-git directory
        non_git_dir = tempfile.mkdtemp()
        try:
            text = "{{ git.commit }}"
            with self.assertRaises(ValueError) as cm:
                substitute_git_variables(text, non_git_dir)
            self.assertIn("git.commit", str(cm.exception))
        finally:
            import shutil
            shutil.rmtree(non_git_dir, ignore_errors=True)

    def test_substitute_git_undefined_variable_raises(self):
        """Test error for undefined git variable."""
        from tasktree.substitution import substitute_git_variables

        text = "{{ git.unknown }}"
        with self.assertRaises(ValueError) as cm:
            substitute_git_variables(text, self.test_dir)
        self.assertIn("unknown", str(cm.exception))
        self.assertIn("not defined", str(cm.exception))

    def test_substitute_git_ignores_other_prefixes(self):
        """Test {{ var.x }}, {{ arg.x }}, etc. are not substituted."""
        from tasktree.substitution import substitute_git_variables

        text = "{{ git.branch }} {{ var.foo }} {{ arg.bar }}"
        output = substitute_git_variables(text, self.test_dir)
        self.assertRegex(output, r"(master|main) \{\{ var\.foo \}\} \{\{ arg\.bar \}\}")

    def test_substitute_git_with_whitespace_variations(self):
        """Test whitespace handling in git placeholders."""
        from tasktree.substitution import substitute_git_variables

        test_cases = [
            "{{git.branch}}",
            "{{ git.branch }}",
            "{{  git  .  branch  }}",
        ]
        for text in test_cases:
            with self.subTest(text=text):
                output = substitute_git_variables(text, self.test_dir)
                self.assertRegex(output, r"(master|main)")

    def test_substitute_git_in_realistic_command(self):
        """Test git variables in realistic command string."""
        from tasktree.substitution import substitute_git_variables
        import subprocess

        # Create a tag
        subprocess.run(['git', 'tag', 'v2.0.0'], cwd=self.test_dir, check=True, capture_output=True)

        text = 'tar czf app-{{ git.describe }}.tar.gz . && echo "Built by {{ git.user_name }}"'
        output = substitute_git_variables(text, self.test_dir)
        self.assertEqual(output, 'tar czf app-v2.0.0.tar.gz . && echo "Built by Test User"')

    def test_substitute_git_detached_head(self):
        """Test {{ git.branch }} returns HEAD in detached HEAD state."""
        from tasktree.substitution import substitute_git_variables
        import subprocess

        # Get current commit SHA
        result = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=self.test_dir, capture_output=True, text=True, check=True)
        commit_sha = result.stdout.strip()

        # Checkout detached HEAD
        subprocess.run(['git', 'checkout', commit_sha], cwd=self.test_dir, check=True, capture_output=True)

        text = "Branch: {{ git.branch }}"
        output = substitute_git_variables(text, self.test_dir)
        self.assertEqual(output, "Branch: HEAD")


if __name__ == "__main__":
    unittest.main()
