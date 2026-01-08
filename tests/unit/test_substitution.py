"""Unit tests for substitution module."""

import os
import unittest

from tasktree.substitution import (
    DEP_OUTPUT_PATTERN,
    PLACEHOLDER_PATTERN,
    substitute_arguments,
    substitute_all,
    substitute_builtin_variables,
    substitute_dependency_outputs,
    substitute_environment,
    substitute_variables,
)
from tasktree.parser import Task


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
        self.assertEqual(result, "port=8080 debug=true timeout=30.5")

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
        self.assertEqual(result, "port=8080 debug=true")

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


class TestDepOutputPattern(unittest.TestCase):
    """Test the regex pattern for matching dependency output references."""

    def test_pattern_matches_basic_syntax(self):
        """Test pattern matches {{ dep.task.outputs.name }} syntax."""
        match = DEP_OUTPUT_PATTERN.search("{{ dep.build.outputs.bundle }}")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "build")
        self.assertEqual(match.group(2), "bundle")

    def test_pattern_matches_with_whitespace(self):
        """Test pattern allows whitespace variations."""
        patterns = [
            "{{dep.build.outputs.bundle}}",
            "{{ dep.build.outputs.bundle }}",
            "{{  dep.build.outputs.bundle  }}",
            "{{ dep . build . outputs . bundle }}",
        ]
        for pattern in patterns:
            match = DEP_OUTPUT_PATTERN.search(pattern)
            self.assertIsNotNone(match, f"Failed to match: {pattern}")
            self.assertEqual(match.group(1), "build")
            self.assertEqual(match.group(2), "bundle")

    def test_pattern_matches_namespaced_task(self):
        """Test pattern matches namespaced tasks with dots."""
        match = DEP_OUTPUT_PATTERN.search("{{ dep.external.build.outputs.artifact }}")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "external.build")
        self.assertEqual(match.group(2), "artifact")

    def test_pattern_matches_underscores(self):
        """Test pattern matches names with underscores."""
        match = DEP_OUTPUT_PATTERN.search("{{ dep.build_app.outputs.my_output }}")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "build_app")
        self.assertEqual(match.group(2), "my_output")

    def test_pattern_does_not_match_other_prefixes(self):
        """Test pattern doesn't match var/arg/env/tt prefixes."""
        non_matches = [
            "{{ var.foo }}",
            "{{ arg.bar }}",
            "{{ env.BAZ }}",
            "{{ tt.qux }}",
        ]
        for text in non_matches:
            match = DEP_OUTPUT_PATTERN.search(text)
            self.assertIsNone(match, f"Should not match: {text}")

    def test_pattern_finds_multiple_references(self):
        """Test pattern finds all references in text."""
        text = "Deploy {{ dep.build.outputs.bundle }} and {{ dep.compile.outputs.binary }}"
        matches = list(DEP_OUTPUT_PATTERN.finditer(text))
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].group(1), "build")
        self.assertEqual(matches[0].group(2), "bundle")
        self.assertEqual(matches[1].group(1), "compile")
        self.assertEqual(matches[1].group(2), "binary")


class TestSubstituteDependencyOutputs(unittest.TestCase):
    """Test dependency output substitution function."""

    def test_substitute_basic_output(self):
        """Test basic output reference substitution."""
        build_task = Task(name="build", cmd="build.sh")
        build_task.outputs = [{"bundle": "dist/app.js"}]
        build_task.__post_init__()

        resolved_tasks = {"build": build_task}

        text = "Deploy {{ dep.build.outputs.bundle }}"
        result = substitute_dependency_outputs(
            text, "deploy", ["build"], resolved_tasks
        )
        self.assertEqual(result, "Deploy dist/app.js")

    def test_substitute_multiple_outputs(self):
        """Test multiple output references in same text."""
        build_task = Task(name="build", cmd="build.sh")
        build_task.outputs = [
            {"bundle": "dist/app.js"},
            {"sourcemap": "dist/app.js.map"}
        ]
        build_task.__post_init__()

        resolved_tasks = {"build": build_task}

        text = "Copy {{ dep.build.outputs.bundle }} and {{ dep.build.outputs.sourcemap }}"
        result = substitute_dependency_outputs(
            text, "deploy", ["build"], resolved_tasks
        )
        self.assertEqual(result, "Copy dist/app.js and dist/app.js.map")

    def test_substitute_from_multiple_tasks(self):
        """Test references from multiple dependency tasks."""
        build_task = Task(name="build", cmd="build.sh")
        build_task.outputs = [{"bundle": "dist/app.js"}]
        build_task.__post_init__()

        compile_task = Task(name="compile", cmd="compile.sh")
        compile_task.outputs = [{"binary": "bin/app"}]
        compile_task.__post_init__()

        resolved_tasks = {"build": build_task, "compile": compile_task}

        text = "Package {{ dep.build.outputs.bundle }} {{ dep.compile.outputs.binary }}"
        result = substitute_dependency_outputs(
            text, "package", ["build", "compile"], resolved_tasks
        )
        self.assertEqual(result, "Package dist/app.js bin/app")

    def test_substitute_no_placeholders(self):
        """Test text without placeholders returns unchanged."""
        resolved_tasks = {}
        text = "No placeholders here"
        result = substitute_dependency_outputs(text, "task", [], resolved_tasks)
        self.assertEqual(result, text)

    def test_error_on_unknown_task(self):
        """Test error when referencing unknown task."""
        resolved_tasks = {}

        text = "Deploy {{ dep.unknown.outputs.bundle }}"
        with self.assertRaises(ValueError) as cm:
            substitute_dependency_outputs(text, "deploy", ["build"], resolved_tasks)

        error_msg = str(cm.exception)
        self.assertIn("unknown task 'unknown'", error_msg)
        self.assertIn("deploy", error_msg)

    def test_error_on_task_not_in_deps(self):
        """Test error when task not listed as dependency."""
        build_task = Task(name="build", cmd="build.sh")
        build_task.outputs = [{"bundle": "dist/app.js"}]
        build_task.__post_init__()

        resolved_tasks = {"build": build_task}

        text = "Deploy {{ dep.build.outputs.bundle }}"
        with self.assertRaises(ValueError) as cm:
            substitute_dependency_outputs(
                text, "deploy", ["other"], resolved_tasks  # build not in deps
            )

        error_msg = str(cm.exception)
        self.assertIn("not list it as a dependency", error_msg)
        self.assertIn("build", error_msg)
        self.assertIn("deploy", error_msg)

    def test_error_on_missing_output_name(self):
        """Test error when output name doesn't exist."""
        build_task = Task(name="build", cmd="build.sh")
        build_task.outputs = [{"bundle": "dist/app.js"}]
        build_task.__post_init__()

        resolved_tasks = {"build": build_task}

        text = "Deploy {{ dep.build.outputs.missing }}"
        with self.assertRaises(ValueError) as cm:
            substitute_dependency_outputs(text, "deploy", ["build"], resolved_tasks)

        error_msg = str(cm.exception)
        self.assertIn("no output named 'missing'", error_msg)
        self.assertIn("Available named outputs", error_msg)
        self.assertIn("bundle", error_msg)

    def test_error_message_for_anonymous_outputs(self):
        """Test error message when task has no named outputs."""
        build_task = Task(name="build", cmd="build.sh")
        build_task.outputs = ["dist/app.js"]  # Anonymous output
        build_task.__post_init__()

        resolved_tasks = {"build": build_task}

        text = "Deploy {{ dep.build.outputs.bundle }}"
        with self.assertRaises(ValueError) as cm:
            substitute_dependency_outputs(text, "deploy", ["build"], resolved_tasks)

        error_msg = str(cm.exception)
        self.assertIn("no output named 'bundle'", error_msg)
        self.assertIn("(none - all outputs are anonymous)", error_msg)

    def test_substitute_with_other_placeholders(self):
        """Test that other placeholder types are not affected."""
        build_task = Task(name="build", cmd="build.sh")
        build_task.outputs = [{"bundle": "dist/app.js"}]
        build_task.__post_init__()

        resolved_tasks = {"build": build_task}

        # Text with both dep and other placeholders
        text = "Deploy {{ dep.build.outputs.bundle }} to {{ env.SERVER }}"
        result = substitute_dependency_outputs(text, "deploy", ["build"], resolved_tasks)

        # Only dep placeholder should be substituted
        self.assertEqual(result, "Deploy dist/app.js to {{ env.SERVER }}")


if __name__ == "__main__":
    unittest.main()
