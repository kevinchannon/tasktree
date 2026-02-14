"""
Unit tests for substitution module.
@athena: 6d71fa7b1f77
"""

import os
import unittest

from tasktree.substitution import (
    DEP_OUTPUT_PATTERN,
    PLACEHOLDER_PATTERN,
    SELF_REFERENCE_PATTERN,
    substitute_arguments,
    substitute_all,
    substitute_builtin_variables,
    substitute_dependency_outputs,
    substitute_environment,
    substitute_self_references,
    substitute_variables,
)
from tasktree.parser import Task


class TestPlaceholderPattern(unittest.TestCase):
    """
    Test the regex pattern for matching placeholders.
    @athena: c578a483b231
    """

    def test_pattern_matches_var_prefix(self):
        """
        Test pattern matches {{ var.name }} syntax.
        @athena: 26a9f371610e
        """
        match = PLACEHOLDER_PATTERN.search("{{ var.foo }}")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "var")
        self.assertEqual(match.group(2), "foo")

    def test_pattern_matches_arg_prefix(self):
        """
        Test pattern matches {{ arg.name }} syntax.
        @athena: 0b1fe334a03d
        """
        match = PLACEHOLDER_PATTERN.search("{{ arg.bar }}")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "arg")
        self.assertEqual(match.group(2), "bar")

    def test_pattern_matches_env_prefix(self):
        """
        Test pattern matches {{ env.name }} syntax.
        @athena: 122170350687
        """
        match = PLACEHOLDER_PATTERN.search("{{ env.USER }}")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "env")
        self.assertEqual(match.group(2), "USER")

    def test_pattern_matches_tt_prefix(self):
        """
        Test pattern matches {{ tt.name }} syntax.
        @athena: e7b46d5cc217
        """
        match = PLACEHOLDER_PATTERN.search("{{ tt.project_root }}")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "tt")
        self.assertEqual(match.group(2), "project_root")

    def test_pattern_allows_whitespace(self):
        """
        Test pattern tolerates extra whitespace.
        @athena: 62f777d2169e
        """
        test_cases = [
            ("no_whitespace", "{{var.the_name}}"),
            ("standard_spacing", "{{ var.the_name }}"),
        ]
        for name, text in test_cases:
            match = PLACEHOLDER_PATTERN.search(text)
            self.assertIsNotNone(match)
            self.assertEqual(match.group(1), "var")
            self.assertEqual(match.group(2), "the_name")

    def test_pattern_requires_valid_identifier(self):
        """
        Test pattern matches arbitrary non-whitespace characters including emojis.
        @athena: 555df31aac2f
        """
        # Valid names (any non-whitespace, including dots for namespaces, emojis, etc.)
        valid = ["foo", "foo_bar", "foo123", "_private", "foo.bar", "a.b.c", "123foo", "foo-bar", "🎄🥶👊"]
        for name in valid:
            match = PLACEHOLDER_PATTERN.search(f"{{{{ var.{name} }}}}")
            self.assertIsNotNone(match, f"Expected '{name}' to match")

        # Invalid names (containing whitespace)
        invalid = ["foo bar", "foo\tbar", "foo\nbar"]
        for name in invalid:
            match = PLACEHOLDER_PATTERN.search(f"{{{{ var.{name} }}}}")
            self.assertIsNone(match, f"Expected '{name}' to NOT match")


class TestSubstituteVariables(unittest.TestCase):
    """
    Test substitute_variables function.
    @athena: 839a88d59a7a
    """

    def test_substitute_single_variable(self):
        """
        Test basic {{ var.x }} substitution.
        @athena: 6d9a612b30b0
        """
        result = substitute_variables("Hello {{ var.name }}!", {"name": "World"})
        self.assertEqual(result, "Hello World!")

    def test_substitute_multiple_variables(self):
        """
        Test multiple different variables in same string.
        @athena: 69809b197058
        """
        text = "{{ var.greeting }} {{ var.name }}!"
        variables = {"greeting": "Hello", "name": "World"}
        result = substitute_variables(text, variables)
        self.assertEqual(result, "Hello World!")

    def test_substitute_same_variable_multiple_times(self):
        """
        Test same variable appears multiple times.
        @athena: ef9618d351bf
        """
        text = "{{ var.name }} says hello to {{ var.name }}"
        variables = {"name": "Alice"}
        result = substitute_variables(text, variables)
        self.assertEqual(result, "Alice says hello to Alice")

    def test_substitute_no_placeholders(self):
        """
        Test string without placeholders returns unchanged.
        @athena: bf4f549bb8fa
        """
        text = "No placeholders here"
        result = substitute_variables(text, {"foo": "bar"})
        self.assertEqual(result, text)

    def test_substitute_ignores_arg_prefix(self):
        """
        Test {{ arg.name }} is not substituted.
        @athena: df90aed9bd1f
        """
        text = "{{ var.foo }} {{ arg.bar }}"
        variables = {"foo": "FOO", "bar": "BAR"}
        result = substitute_variables(text, variables)
        self.assertEqual(result, "FOO {{ arg.bar }}")

    def test_substitute_undefined_variable_raises(self):
        """
        Test error for undefined variable reference.
        @athena: 5351101b8697
        """
        with self.assertRaises(ValueError) as cm:
            substitute_variables("{{ var.missing }}", {})
        self.assertIn("missing", str(cm.exception))
        self.assertIn("not defined", str(cm.exception))

    def test_substitute_with_whitespace_variations(self):
        """
        Test whitespace handling in placeholders.
        @athena: 7fb804c17309
        """
        variables = {"name": "World"}
        test_cases = [
            ("{{var.name}}", "World"),
            ("{{ var.name }}", "World"),
        ]
        for text, expected in test_cases:
            result = substitute_variables(text, variables)
            self.assertEqual(result, expected)

    def test_substitute_empty_string_value(self):
        """
        Test variable with empty string value.
        @athena: 9ecef27e5aaa
        """
        result = substitute_variables("foo{{ var.x }}bar", {"x": ""})
        self.assertEqual(result, "foobar")

    def test_substitute_in_complex_text(self):
        """
        Test substitution in realistic command string.
        @athena: 531219a12307
        """
        text = 'echo "Deploying to {{ var.server }} on port {{ var.port }}"'
        variables = {"server": "production.example.com", "port": "8080"}
        result = substitute_variables(text, variables)
        self.assertEqual(
            result, 'echo "Deploying to production.example.com on port 8080"'
        )


class TestSubstituteArguments(unittest.TestCase):
    """
    Test substitute_arguments function.
    @athena: 9049f11dcbb3
    """

    def test_substitute_single_argument(self):
        """
        Test basic {{ arg.x }} substitution.
        @athena: bcc8ebd53cf4
        """
        result = substitute_arguments("Hello {{ arg.name }}!", {"name": "World"})
        self.assertEqual(result, "Hello World!")

    def test_substitute_multiple_arguments(self):
        """
        Test multiple different arguments in same string.
        @athena: 9a26af6a2f4f
        """
        text = "deploy {{ arg.app }} to {{ arg.region }}"
        args = {"app": "myapp", "region": "us-west-1"}
        result = substitute_arguments(text, args)
        self.assertEqual(result, "deploy myapp to us-west-1")

    def test_substitute_converts_types_to_strings(self):
        """
        Test int/bool/float values are converted to strings.
        @athena: a801ad9e99e8
        """
        text = "port={{ arg.port }} debug={{ arg.debug }} timeout={{ arg.timeout }}"
        args = {"port": 8080, "debug": True, "timeout": 30.5}
        result = substitute_arguments(text, args)
        self.assertEqual(result, "port=8080 debug=true timeout=30.5")

    def test_substitute_ignores_var_prefix(self):
        """
        Test {{ var.name }} is not substituted.
        @athena: fb1f73337112
        """
        text = "{{ arg.foo }} {{ var.bar }}"
        args = {"foo": "FOO", "bar": "BAR"}
        result = substitute_arguments(text, args)
        self.assertEqual(result, "FOO {{ var.bar }}")

    def test_substitute_undefined_argument_raises(self):
        """
        Test error for undefined argument reference.
        @athena: 7c4858e65a20
        """
        with self.assertRaises(ValueError) as cm:
            substitute_arguments("{{ arg.missing }}", {})
        self.assertIn("missing", str(cm.exception))
        self.assertIn("not defined", str(cm.exception))

    def test_substitute_none_value(self):
        """
        Test None value is converted to string.
        @athena: 0da0c2029e64
        """
        result = substitute_arguments("value={{ arg.x }}", {"x": None})
        self.assertEqual(result, "value=None")

    def test_exported_arg_raises_error_when_used_in_template(self):
        """
        Test that exported arguments cannot be used in template substitution.
        @athena: b56eda9eb334
        """
        exported_args = {"server"}
        args = {"port": 8080}  # Only non-exported args

        with self.assertRaises(ValueError) as cm:
            substitute_arguments("{{ arg.server }}", args, exported_args)

        self.assertIn("server", str(cm.exception))
        self.assertIn("exported", str(cm.exception))
        self.assertIn("$server", str(cm.exception))
        self.assertIn("environment variable", str(cm.exception))

    def test_regular_arg_works_with_exported_args_set(self):
        """
        Test that regular args still work when exported_args is provided.
        @athena: e3e11f021486
        """
        exported_args = {"server"}
        args = {"port": 8080}

        result = substitute_arguments("port={{ arg.port }}", args, exported_args)
        self.assertEqual(result, "port=8080")

    def test_mixed_exported_and_regular_args(self):
        """
        Test mixing exported and regular args in substitution.
        @athena: 3b0f2a7b7721
        """
        exported_args = {"server", "user"}
        args = {"port": 8080, "verbose": True}

        text = "port={{ arg.port }} debug={{ arg.verbose }}"
        result = substitute_arguments(text, args, exported_args)
        self.assertEqual(result, "port=8080 debug=true")

        # Exported arg should fail
        with self.assertRaises(ValueError):
            substitute_arguments("{{ arg.server }}", args, exported_args)


class TestSubstituteEnvironmentVariable(unittest.TestCase):
    """
    Test substitute_environment function for environment variables.
    @athena: 8b6b7f441d81
    """

    def test_substitute_single_env_var(self):
        """
        Test basic {{ env.VAR }} substitution for environment variables.
        @athena: 14c224625dc5
        """
        os.environ["TEST_VAR"] = "test_value"
        try:
            result = substitute_environment("Hello {{ env.TEST_VAR }}!")
            self.assertEqual(result, "Hello test_value!")
        finally:
            del os.environ["TEST_VAR"]

    def test_substitute_multiple_env_vars(self):
        """
        Test multiple different environment variables in same string.
        @athena: 893b52157e30
        """
        os.environ["VAR1"] = "value1"
        os.environ["VAR2"] = "value2"
        try:
            text = "{{ env.VAR1 }} and {{ env.VAR2 }}"
            result = substitute_environment(text)
            self.assertEqual(result, "value1 and value2")
        finally:
            del os.environ["VAR1"]
            del os.environ["VAR2"]

    def test_substitute_same_env_var_multiple_times(self):
        """
        Test same environment variable appears multiple times.
        @athena: 53d21a278e2a
        """
        os.environ["USER"] = "testuser"
        try:
            text = "{{ env.USER }} says hello to {{ env.USER }}"
            result = substitute_environment(text)
            self.assertEqual(result, "testuser says hello to testuser")
        finally:
            del os.environ["USER"]

    def test_substitute_no_placeholders(self):
        """
        Test string without placeholders returns unchanged.
        @athena: ad282889cbbc
        """
        text = "No placeholders here"
        result = substitute_environment(text)
        self.assertEqual(result, text)

    def test_substitute_ignores_var_prefix(self):
        """
        Test {{ var.name }} is not substituted.
        @athena: e663d9b809b3
        """
        os.environ["FOO"] = "env_foo"
        try:
            text = "{{ env.FOO }} {{ var.bar }}"
            result = substitute_environment(text)
            self.assertEqual(result, "env_foo {{ var.bar }}")
        finally:
            del os.environ["FOO"]

    def test_substitute_ignores_arg_prefix(self):
        """
        Test {{ arg.name }} is not substituted.
        @athena: 8f722ed8bf4c
        """
        os.environ["FOO"] = "env_foo"
        try:
            text = "{{ env.FOO }} {{ arg.bar }}"
            result = substitute_environment(text)
            self.assertEqual(result, "env_foo {{ arg.bar }}")
        finally:
            del os.environ["FOO"]

    def test_substitute_undefined_env_var_raises(self):
        """
        Test error for undefined environment variable.
        @athena: a31ae899f042
        """
        # Make sure var is not set
        if "DEFINITELY_NOT_SET_VAR" in os.environ:
            del os.environ["DEFINITELY_NOT_SET_VAR"]

        with self.assertRaises(ValueError) as cm:
            substitute_environment("{{ env.DEFINITELY_NOT_SET_VAR }}")
        self.assertIn("DEFINITELY_NOT_SET_VAR", str(cm.exception))
        self.assertIn("not set", str(cm.exception))

    def test_substitute_with_whitespace_variations(self):
        """
        Test whitespace handling in placeholders.
        @athena: 465a44e5e078
        """
        os.environ["TEST_VAR"] = "value"
        try:
            test_cases = [
                ("{{env.TEST_VAR}}", "value"),
                ("{{ env.TEST_VAR }}", "value"),
            ]
            for text, expected in test_cases:
                result = substitute_environment(text)
                self.assertEqual(result, expected)
        finally:
            del os.environ["TEST_VAR"]

    def test_substitute_empty_string_value(self):
        """
        Test env var with empty string value.
        @athena: 58efa8a86b72
        """
        os.environ["EMPTY_VAR"] = ""
        try:
            result = substitute_environment("foo{{ env.EMPTY_VAR }}bar")
            self.assertEqual(result, "foobar")
        finally:
            del os.environ["EMPTY_VAR"]

    def test_substitute_in_complex_command(self):
        """
        Test substitution in realistic command string.
        @athena: 923ce7df0885
        """
        os.environ["DEPLOY_USER"] = "admin"
        os.environ["DEPLOY_HOST"] = "prod.example.com"
        try:
            text = (
                "scp package.tar.gz {{ env.DEPLOY_USER }}@{{ env.DEPLOY_HOST }}:/opt/"
            )
            result = substitute_environment(text)
            self.assertEqual(result, "scp package.tar.gz admin@prod.example.com:/opt/")
        finally:
            del os.environ["DEPLOY_USER"]
            del os.environ["DEPLOY_HOST"]


class TestSubstituteBuiltinVariables(unittest.TestCase):
    """
    Test substitute_builtin_variables function.
    @athena: 1c9cfba3ca00
    """

    def test_substitute_single_builtin_var(self):
        """
        Test basic {{ tt.x }} substitution.
        @athena: a2c34f2094b9
        """
        builtin_vars = {"project_root": "/home/user/project"}
        result = substitute_builtin_variables(
            "Root: {{ tt.project_root }}", builtin_vars
        )
        self.assertEqual(result, "Root: /home/user/project")

    def test_substitute_multiple_builtin_vars(self):
        """
        Test multiple different built-in vars in same string.
        @athena: 5bbddcbd1305
        """
        builtin_vars = {
            "project_root": "/home/user/project",
            "task_name": "build",
        }
        text = "Task {{ tt.task_name }} in {{ tt.project_root }}"
        result = substitute_builtin_variables(text, builtin_vars)
        self.assertEqual(result, "Task build in /home/user/project")

    def test_substitute_all_builtin_vars(self):
        """
        Test all 8 built-in variables.
        @athena: 569abe1b5861
        """
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
        """
        Test same built-in var appears multiple times.
        @athena: 6e2a553b375b
        """
        builtin_vars = {"task_name": "build"}
        text = "{{ tt.task_name }} depends on {{ tt.task_name }}"
        result = substitute_builtin_variables(text, builtin_vars)
        self.assertEqual(result, "build depends on build")

    def test_substitute_no_placeholders(self):
        """
        Test string without placeholders returns unchanged.
        @athena: a91f2ab890d9
        """
        builtin_vars = {"project_root": "/home/user/project"}
        text = "No placeholders here"
        result = substitute_builtin_variables(text, builtin_vars)
        self.assertEqual(result, text)

    def test_substitute_ignores_var_prefix(self):
        """
        Test {{ var.name }} is not substituted.
        @athena: 60f157862197
        """
        builtin_vars = {"project_root": "/home/user/project"}
        text = "{{ tt.project_root }} {{ var.foo }}"
        result = substitute_builtin_variables(text, builtin_vars)
        self.assertEqual(result, "/home/user/project {{ var.foo }}")

    def test_substitute_ignores_arg_prefix(self):
        """
        Test {{ arg.name }} is not substituted.
        @athena: 9d2f1259f58c
        """
        builtin_vars = {"project_root": "/home/user/project"}
        text = "{{ tt.project_root }} {{ arg.foo }}"
        result = substitute_builtin_variables(text, builtin_vars)
        self.assertEqual(result, "/home/user/project {{ arg.foo }}")

    def test_substitute_ignores_env_prefix(self):
        """
        Test {{ env.NAME }} is not substituted.
        @athena: 185fea66c636
        """
        builtin_vars = {"project_root": "/home/user/project"}
        text = "{{ tt.project_root }} {{ env.USER }}"
        result = substitute_builtin_variables(text, builtin_vars)
        self.assertEqual(result, "/home/user/project {{ env.USER }}")

    def test_substitute_undefined_builtin_var_raises(self):
        """
        Test error for undefined built-in variable.
        @athena: cdb21f2219f1
        """
        builtin_vars = {"project_root": "/home/user/project"}
        with self.assertRaises(ValueError) as cm:
            substitute_builtin_variables("{{ tt.missing }}", builtin_vars)
        self.assertIn("missing", str(cm.exception))
        self.assertIn("not defined", str(cm.exception))

    def test_substitute_with_whitespace_variations(self):
        """
        Test whitespace handling in placeholders.
        @athena: fca5f1c67072
        """
        builtin_vars = {"task_name": "build"}
        test_cases = [
            ("{{tt.task_name}}", "build"),
            ("{{ tt.task_name }}", "build"),
        ]
        for text, expected in test_cases:
            result = substitute_builtin_variables(text, builtin_vars)
            self.assertEqual(result, expected)

    def test_substitute_in_realistic_command(self):
        """
        Test substitution in realistic command string.
        @athena: aafc0df7159f
        """
        builtin_vars = {
            "project_root": "/home/user/project",
            "timestamp_unix": "1703772645",
        }
        text = "tar czf {{ tt.project_root }}/dist/app-{{ tt.timestamp_unix }}.tar.gz ."
        result = substitute_builtin_variables(text, builtin_vars)
        self.assertEqual(
            result, "tar czf /home/user/project/dist/app-1703772645.tar.gz ."
        )


class TestSubstituteAll(unittest.TestCase):
    """
    Test substitute_all function.
    @athena: 3bba88c9beb9
    """

    def test_substitute_both_var_and_arg(self):
        """
        Test both variables and arguments are substituted.
        @athena: 05f6138e23d7
        """
        text = "{{ var.server }} {{ arg.port }}"
        variables = {"server": "example.com"}
        args = {"port": 8080}
        result = substitute_all(text, variables, args)
        self.assertEqual(result, "example.com 8080")

    def test_variables_substituted_before_arguments(self):
        """
        Test variables are substituted first, then arguments.
        @athena: 628f7673d6a9
        """
        # If a variable contains {{ arg.x }}, it should remain for arg substitution
        text = "{{ var.template }}"
        variables = {"template": "port={{ arg.port }}"}
        args = {"port": 9000}
        result = substitute_all(text, variables, args)
        self.assertEqual(result, "port=9000")

    def test_substitute_mixed_placeholders(self):
        """
        Test realistic case with both types.
        @athena: 8d75ca68ae1e
        """
        text = 'echo "Deploy {{ arg.app }} to {{ var.server }}:{{ var.port }}"'
        variables = {"server": "prod.example.com", "port": "8080"}
        args = {"app": "myservice"}
        result = substitute_all(text, variables, args)
        self.assertEqual(result, 'echo "Deploy myservice to prod.example.com:8080"')

    def test_substitute_all_empty_dicts(self):
        """
        Test with no variables or arguments.
        @athena: 6640c5811547
        """
        text = "No placeholders"
        result = substitute_all(text, {}, {})
        self.assertEqual(result, text)

    def test_substitute_all_three_types(self):
        """
        Test variables, arguments, and environment all work together.
        @athena: 4c994f354858
        """
        os.environ["ENV_VAR"] = "from_env"
        try:
            text = "{{ var.v }} {{ arg.a }} {{ env.ENV_VAR }}"
            variables = {"v": "from_var"}
            args = {"a": "from_arg"}
            result = substitute_all(text, variables, args)
            self.assertEqual(result, "from_var from_arg from_env")
        finally:
            del os.environ["ENV_VAR"]

    def test_substitute_order_var_then_arg_then_env(self):
        """
        Test substitution happens in correct order.
        @athena: 45df2446bc4e
        """
        os.environ["PORT"] = "9000"
        try:
            # Variable contains arg placeholder, which contains env placeholder
            text = "{{ var.template }}"
            variables = {"template": "server={{ arg.server }}"}
            args = {"server": "host:{{ env.PORT }}"}
            result = substitute_all(text, variables, args)
            self.assertEqual(result, "server=host:9000")
        finally:
            del os.environ["PORT"]


class TestDepOutputPattern(unittest.TestCase):
    """
    Test the regex pattern for matching dependency output references.
    @athena: 3b6aba512b3d
    """

    def test_pattern_matches_basic_syntax(self):
        """
        Test pattern matches {{ dep.task.outputs.name }} syntax.
        @athena: 40a0770b7cce
        """
        match = DEP_OUTPUT_PATTERN.search("{{ dep.build.outputs.bundle }}")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "build")
        self.assertEqual(match.group(2), "bundle")

    def test_pattern_matches_with_whitespace(self):
        """
        Test pattern allows whitespace variations.
        @athena: 940bc0bececf
        """
        patterns = [
            "{{dep.build.outputs.bundle}}",
            "{{ dep.build.outputs.bundle }}",
            "{{  dep.build.outputs.bundle  }}",
        ]
        for pattern in patterns:
            match = DEP_OUTPUT_PATTERN.search(pattern)
            self.assertIsNotNone(match, f"Failed to match: {pattern}")
            self.assertEqual(match.group(1), "build")
            self.assertEqual(match.group(2), "bundle")

    def test_pattern_matches_namespaced_task(self):
        """
        Test pattern matches namespaced tasks with dots.
        @athena: 31e80d794517
        """
        match = DEP_OUTPUT_PATTERN.search("{{ dep.external.build.outputs.artifact }}")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "external.build")
        self.assertEqual(match.group(2), "artifact")

    def test_pattern_matches_underscores(self):
        """
        Test pattern matches names with underscores.
        @athena: d2bbda779f56
        """
        match = DEP_OUTPUT_PATTERN.search("{{ dep.build_app.outputs.my_output }}")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "build_app")
        self.assertEqual(match.group(2), "my_output")

    def test_pattern_does_not_match_other_prefixes(self):
        """
        Test pattern doesn't match var/arg/env/tt prefixes.
        @athena: 3a19de3eb05f
        """
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
        """
        Test pattern finds all references in text.
        @athena: ddeb3a2f8d5d
        """
        text = (
            "Deploy {{ dep.build.outputs.bundle }} and {{ dep.compile.outputs.binary }}"
        )
        matches = list(DEP_OUTPUT_PATTERN.finditer(text))
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].group(1), "build")
        self.assertEqual(matches[0].group(2), "bundle")
        self.assertEqual(matches[1].group(1), "compile")
        self.assertEqual(matches[1].group(2), "binary")


class TestSubstituteDependencyOutputs(unittest.TestCase):
    """
    Test dependency output substitution function.
    @athena: d765e0973a6f
    """

    def test_substitute_basic_output(self):
        """
        Test basic output reference substitution.
        @athena: 1d0c6d0a8171
        """
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
        """
        Test multiple output references in same text.
        @athena: 6953ac13543b
        """
        build_task = Task(name="build", cmd="build.sh")
        build_task.outputs = [
            {"bundle": "dist/app.js"},
            {"sourcemap": "dist/app.js.map"},
        ]
        build_task.__post_init__()

        resolved_tasks = {"build": build_task}

        text = (
            "Copy {{ dep.build.outputs.bundle }} and {{ dep.build.outputs.sourcemap }}"
        )
        result = substitute_dependency_outputs(
            text, "deploy", ["build"], resolved_tasks
        )
        self.assertEqual(result, "Copy dist/app.js and dist/app.js.map")

    def test_substitute_from_multiple_tasks(self):
        """
        Test references from multiple dependency tasks.
        @athena: 78f7479eca65
        """
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
        """
        Test text without placeholders returns unchanged.
        @athena: 906249c2dd9c
        """
        resolved_tasks = {}
        text = "No placeholders here"
        result = substitute_dependency_outputs(text, "task", [], resolved_tasks)
        self.assertEqual(result, text)

    def test_error_on_unknown_task(self):
        """
        Test error when referencing unknown task.
        @athena: af2af69299db
        """
        resolved_tasks = {}

        text = "Deploy {{ dep.unknown.outputs.bundle }}"
        with self.assertRaises(ValueError) as cm:
            substitute_dependency_outputs(text, "deploy", ["build"], resolved_tasks)

        error_msg = str(cm.exception)
        self.assertIn("unknown task 'unknown'", error_msg)
        self.assertIn("deploy", error_msg)

    def test_error_on_task_not_in_deps(self):
        """
        Test error when task not listed as dependency.
        @athena: fa1665a8d367
        """
        build_task = Task(name="build", cmd="build.sh")
        build_task.outputs = [{"bundle": "dist/app.js"}]
        build_task.__post_init__()

        resolved_tasks = {"build": build_task}

        text = "Deploy {{ dep.build.outputs.bundle }}"
        with self.assertRaises(ValueError) as cm:
            substitute_dependency_outputs(
                text,
                "deploy",
                ["other"],
                resolved_tasks,  # build not in deps
            )

        error_msg = str(cm.exception)
        self.assertIn("not list it as a dependency", error_msg)
        self.assertIn("build", error_msg)
        self.assertIn("deploy", error_msg)

    def test_error_on_missing_output_name(self):
        """
        Test error when output name doesn't exist.
        @athena: 8c0068e47bfb
        """
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
        """
        Test error message when task has no named outputs.
        @athena: 31324bbcbae3
        """
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
        """
        Test that other placeholder types are not affected.
        @athena: 2634f308abc2
        """
        build_task = Task(name="build", cmd="build.sh")
        build_task.outputs = [{"bundle": "dist/app.js"}]
        build_task.__post_init__()

        resolved_tasks = {"build": build_task}

        # Text with both dep and other placeholders
        text = "Deploy {{ dep.build.outputs.bundle }} to {{ env.SERVER }}"
        result = substitute_dependency_outputs(
            text, "deploy", ["build"], resolved_tasks
        )

        # Only dep placeholder should be substituted
        self.assertEqual(result, "Deploy dist/app.js to {{ env.SERVER }}")


class TestSelfReferencePattern(unittest.TestCase):
    """
    Test the regex pattern for matching self-reference placeholders.
    @athena: f782f128e72f
    """

    def test_pattern_matches_self_inputs(self):
        """
        Test pattern matches {{ self.inputs.name }} syntax.
        @athena: 00703c56a0f7
        """
        match = SELF_REFERENCE_PATTERN.search("{{ self.inputs.src }}")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "inputs")
        self.assertEqual(match.group(2), "src")

    def test_pattern_matches_self_outputs(self):
        """
        Test pattern matches {{ self.outputs.name }} syntax.
        @athena: d36fb8e83fc2
        """
        match = SELF_REFERENCE_PATTERN.search("{{ self.outputs.dest }}")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "outputs")
        self.assertEqual(match.group(2), "dest")

    def test_pattern_with_whitespace(self):
        """
        Test pattern allows various whitespace configurations.
        @athena: 72c79076b744
        """
        patterns = [
            "{{self.inputs.foo}}",
            "{{ self.inputs.foo }}",
            "{{  self.inputs.foo  }}",
            "{{ self.outputs.bar }}",
        ]
        for pattern in patterns:
            match = SELF_REFERENCE_PATTERN.search(pattern)
            self.assertIsNotNone(match, f"Failed to match: {pattern}")

    def test_pattern_captures_field_and_name(self):
        """
        Test pattern correctly captures field (inputs/outputs) and name.
        @athena: ff880c048f72
        """
        match_input = SELF_REFERENCE_PATTERN.search("{{ self.inputs.config }}")
        self.assertEqual(match_input.group(1), "inputs")
        self.assertEqual(match_input.group(2), "config")

        match_output = SELF_REFERENCE_PATTERN.search("{{ self.outputs.bundle }}")
        self.assertEqual(match_output.group(1), "outputs")
        self.assertEqual(match_output.group(2), "bundle")

    def test_pattern_requires_valid_identifier(self):
        """
        Test pattern only matches valid identifier names.
        @athena: f032a0b3c956
        """
        # Valid identifiers should match
        valid = [
            "{{ self.inputs.foo }}",
            "{{ self.inputs.foo_bar }}",
            "{{ self.inputs._private }}",
            "{{ self.inputs.FOO }}",
            "{{ self.inputs.foo123 }}",
        ]
        for text in valid:
            match = SELF_REFERENCE_PATTERN.search(text)
            self.assertIsNotNone(match, f"Should match: {text}")

        # Invalid identifiers should not match
        invalid = [
            "{{ self.inputs.123foo }}",  # Starts with number
            "{{ self.inputs.foo-bar }}",  # Contains hyphen
            "{{ self.inputs.foo.bar }}",  # Contains dot
        ]
        for text in invalid:
            match = SELF_REFERENCE_PATTERN.search(text)
            self.assertIsNone(match, f"Should not match: {text}")

    def test_pattern_does_not_match_other_prefixes(self):
        """
        Test pattern does not match non-self prefixes.
        @athena: ade039f40952
        """
        non_matches = [
            "{{ var.foo }}",
            "{{ arg.bar }}",
            "{{ env.BAZ }}",
            "{{ tt.qux }}",
            "{{ dep.task.outputs.name }}",
        ]
        for text in non_matches:
            match = SELF_REFERENCE_PATTERN.search(text)
            self.assertIsNone(match, f"Should not match: {text}")

    def test_pattern_finds_multiple_references(self):
        """
        Test pattern finds all self-references in text.
        @athena: a06d4d939c84
        """
        text = "cp {{ self.inputs.src }} {{ self.outputs.dest }}"
        matches = list(SELF_REFERENCE_PATTERN.finditer(text))
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].group(1), "inputs")
        self.assertEqual(matches[0].group(2), "src")
        self.assertEqual(matches[1].group(1), "outputs")
        self.assertEqual(matches[1].group(2), "dest")

    def test_pattern_matches_underscores(self):
        """
        Test pattern matches names with underscores.
        @athena: 90e473c0bba6
        """
        match = SELF_REFERENCE_PATTERN.search("{{ self.inputs.my_input_file }}")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(2), "my_input_file")

    def test_pattern_case_sensitive(self):
        """
        Test pattern is case-sensitive for field names.
        @athena: 8b1b3f0e010d
        """
        # 'inputs' and 'outputs' are lowercase
        match_inputs = SELF_REFERENCE_PATTERN.search("{{ self.inputs.foo }}")
        self.assertIsNotNone(match_inputs)

        # Capital letters should not match the field
        match_inputs_caps = SELF_REFERENCE_PATTERN.search("{{ self.INPUTS.foo }}")
        self.assertIsNone(match_inputs_caps)

    def test_pattern_mixed_in_text(self):
        """
        Test pattern works when mixed with other text and placeholders.
        @athena: 6be8b342f622
        """
        text = "Build {{ self.inputs.src }} using {{ var.compiler }} to {{ self.outputs.bin }}"
        matches = list(SELF_REFERENCE_PATTERN.finditer(text))
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].group(2), "src")
        self.assertEqual(matches[1].group(2), "bin")

    def test_pattern_matches_numeric_index(self):
        """
        Test pattern matches {{ self.inputs.0 }} syntax.
        @athena: 17f767495483
        """
        match = SELF_REFERENCE_PATTERN.search("{{ self.inputs.0 }}")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "inputs")
        self.assertEqual(match.group(2), "0")

    def test_pattern_matches_multidigit_index(self):
        """
        Test pattern matches multi-digit indices.
        @athena: 0e6c5bac2ab5
        """
        test_cases = [
            ("{{ self.inputs.42 }}", "42"),
            ("{{ self.outputs.123 }}", "123"),
            ("{{ self.inputs.999 }}", "999"),
        ]
        for text, expected_index in test_cases:
            match = SELF_REFERENCE_PATTERN.search(text)
            self.assertIsNotNone(match, f"Failed to match: {text}")
            self.assertEqual(match.group(2), expected_index)

    def test_pattern_rejects_negative_indices(self):
        """
        Test pattern does not match negative indices.
        @athena: fbee773da2fe
        """
        invalid = [
            "{{ self.inputs.-1 }}",
            "{{ self.outputs.-42 }}",
        ]
        for text in invalid:
            match = SELF_REFERENCE_PATTERN.search(text)
            self.assertIsNone(match, f"Should not match: {text}")

    def test_pattern_rejects_float_indices(self):
        """
        Test pattern does not match floating point indices.
        @athena: d2ecfcc42ea8
        """
        invalid = [
            "{{ self.inputs.1.5 }}",
            "{{ self.outputs.0.0 }}",
        ]
        for text in invalid:
            match = SELF_REFERENCE_PATTERN.search(text)
            self.assertIsNone(match, f"Should not match: {text}")


class TestSubstituteSelfReferences(unittest.TestCase):
    """
    Test substitute_self_references function.
    @athena: a75c47a1b237
    """

    def test_substitute_single_input(self):
        """
        Test substituting a single input reference.
        @athena: f5aa8b4425d6
        """
        input_map = {"src": "src/app.js"}
        output_map = {}
        text = "cat {{ self.inputs.src }}"
        result = substitute_self_references(
            text, "build", input_map, output_map, [], []
        )
        self.assertEqual(result, "cat src/app.js")

    def test_substitute_single_output(self):
        """
        Test substituting a single output reference.
        @athena: 7a9312269af1
        """
        input_map = {}
        output_map = {"dest": "dist/app.js"}
        text = "echo {{ self.outputs.dest }}"
        result = substitute_self_references(
            text, "build", input_map, output_map, [], []
        )
        self.assertEqual(result, "echo dist/app.js")

    def test_substitute_multiple_references(self):
        """
        Test substituting multiple self-references in same text.
        @athena: 642fd8b4df2f
        """
        input_map = {"src": "src/main.c", "headers": "include/*.h"}
        output_map = {"binary": "build/app"}
        text = "gcc {{ self.inputs.src }} -I {{ self.inputs.headers }} -o {{ self.outputs.binary }}"
        result = substitute_self_references(
            text, "compile", input_map, output_map, [], []
        )
        self.assertEqual(result, "gcc src/main.c -I include/*.h -o build/app")

    def test_substitute_mixed_inputs_and_outputs(self):
        """
        Test substituting both inputs and outputs in same command.
        @athena: a8c4b4693397
        """
        input_map = {"config": "config.json"}
        output_map = {"log": "build.log"}
        text = "build --config {{ self.inputs.config }} --log {{ self.outputs.log }}"
        result = substitute_self_references(
            text, "build", input_map, output_map, [], []
        )
        self.assertEqual(result, "build --config config.json --log build.log")

    def test_substitute_glob_pattern_verbatim(self):
        """
        Test that glob patterns are substituted as-is without expansion.
        @athena: 6f1555a6e38d
        """
        input_map = {"sources": "src/**/*.js"}
        output_map = {"bundle": "dist/*.min.js"}
        text = "bundle {{ self.inputs.sources }} to {{ self.outputs.bundle }}"
        result = substitute_self_references(
            text, "bundle", input_map, output_map, [], []
        )
        # Glob patterns should be substituted verbatim, not expanded
        self.assertEqual(result, "bundle src/**/*.js to dist/*.min.js")

    def test_substitute_no_placeholders(self):
        """
        Test that text without placeholders is unchanged.
        @athena: 31af1437d1be
        """
        input_map = {"src": "file.txt"}
        output_map = {"dest": "out.txt"}
        text = "echo hello world"
        result = substitute_self_references(text, "test", input_map, output_map, [], [])
        self.assertEqual(result, "echo hello world")

    def test_error_on_missing_input_name(self):
        """
        Test that referencing non-existent input raises error with available names.
        @athena: 6206dde09c5a
        """
        input_map = {"src": "file.txt", "config": "config.json"}
        output_map = {}
        text = "cat {{ self.inputs.missing }}"
        with self.assertRaises(ValueError) as cm:
            substitute_self_references(text, "build", input_map, output_map, [], [])
        error_msg = str(cm.exception)
        self.assertIn("build", error_msg)
        self.assertIn("missing", error_msg)
        self.assertIn("src", error_msg)
        self.assertIn("config", error_msg)
        self.assertIn("input", error_msg)

    def test_error_on_missing_output_name(self):
        """
        Test that referencing non-existent output raises error with available names.
        @athena: 8c7525c15305
        """
        input_map = {}
        output_map = {"bundle": "dist/app.js", "sourcemap": "dist/app.js.map"}
        text = "deploy {{ self.outputs.missing }}"
        with self.assertRaises(ValueError) as cm:
            substitute_self_references(text, "deploy", input_map, output_map, [], [])
        error_msg = str(cm.exception)
        self.assertIn("deploy", error_msg)
        self.assertIn("missing", error_msg)
        self.assertIn("bundle", error_msg)
        self.assertIn("sourcemap", error_msg)
        self.assertIn("output", error_msg)

    def test_error_with_empty_input_map(self):
        """
        Test error message when all inputs are anonymous.
        @athena: 982070c53bb3
        """
        input_map = {}
        output_map = {}
        text = "cat {{ self.inputs.src }}"
        with self.assertRaises(ValueError) as cm:
            substitute_self_references(text, "build", input_map, output_map, [], [])
        error_msg = str(cm.exception)
        self.assertIn("build", error_msg)
        self.assertIn("src", error_msg)
        self.assertIn("anonymous", error_msg)

    def test_error_with_empty_output_map(self):
        """
        Test error message when all outputs are anonymous.
        @athena: 0f14b88b5156
        """
        input_map = {}
        output_map = {}
        text = "echo {{ self.outputs.dest }}"
        with self.assertRaises(ValueError) as cm:
            substitute_self_references(text, "build", input_map, output_map, [], [])
        error_msg = str(cm.exception)
        self.assertIn("build", error_msg)
        self.assertIn("dest", error_msg)
        self.assertIn("anonymous", error_msg)

    def test_substitute_ignores_other_placeholders(self):
        """
        Test that other placeholder types are not touched.
        @athena: d6102023946f
        """
        input_map = {"src": "file.txt"}
        output_map = {"dest": "out.txt"}
        text = "cp {{ self.inputs.src }} {{ var.temp }} {{ arg.mode }} {{ env.USER }} {{ self.outputs.dest }}"
        result = substitute_self_references(text, "copy", input_map, output_map, [], [])
        # Only self references should be substituted
        self.assertEqual(
            result, "cp file.txt {{ var.temp }} {{ arg.mode }} {{ env.USER }} out.txt"
        )

    def test_substitute_same_reference_multiple_times(self):
        """
        Test substituting the same reference multiple times.
        @athena: 4b88c1d3cbd4
        """
        input_map = {"config": "app.json"}
        output_map = {}
        text = "validate {{ self.inputs.config }} && deploy {{ self.inputs.config }}"
        result = substitute_self_references(text, "task", input_map, output_map, [], [])
        self.assertEqual(result, "validate app.json && deploy app.json")

    def test_substitute_with_underscores(self):
        """
        Test that names with underscores work correctly.
        @athena: 32da29013926
        """
        input_map = {"source_file": "src/main.c", "header_files": "include/*.h"}
        output_map = {"output_binary": "bin/app"}
        text = "gcc {{ self.inputs.source_file }} -I {{ self.inputs.header_files }} -o {{ self.outputs.output_binary }}"
        result = substitute_self_references(
            text, "compile", input_map, output_map, [], []
        )
        self.assertEqual(result, "gcc src/main.c -I include/*.h -o bin/app")

    def test_substitute_empty_string(self):
        """
        Test that empty string is handled correctly.
        @athena: eff5e22f5a6e
        """
        input_map = {"src": "file.txt"}
        output_map = {}
        text = ""
        result = substitute_self_references(text, "task", input_map, output_map, [], [])
        self.assertEqual(result, "")

    def test_substitute_positional_input(self):
        """
        Test basic positional input access.
        @athena: cd6b985862bf
        """
        input_map = {}
        output_map = {}
        indexed_inputs = ["src/app.js", "config.json"]
        indexed_outputs = []
        text = "cat {{ self.inputs.0 }}"
        result = substitute_self_references(
            text, "build", input_map, output_map, indexed_inputs, indexed_outputs
        )
        self.assertEqual(result, "cat src/app.js")

    def test_substitute_positional_output(self):
        """
        Test basic positional output access.
        @athena: d22906dd4714
        """
        input_map = {}
        output_map = {}
        indexed_inputs = []
        indexed_outputs = ["dist/bundle.js", "dist/bundle.css"]
        text = "echo {{ self.outputs.0 }}"
        result = substitute_self_references(
            text, "build", input_map, output_map, indexed_inputs, indexed_outputs
        )
        self.assertEqual(result, "echo dist/bundle.js")

    def test_substitute_multiple_positional_references(self):
        """
        Test multiple positional references in same text.
        @athena: c615e1c19418
        """
        input_map = {}
        output_map = {}
        indexed_inputs = ["src/main.c", "src/util.c", "include/*.h"]
        indexed_outputs = ["build/app", "build/app.debug"]
        text = "gcc {{ self.inputs.0 }} {{ self.inputs.1 }} -I {{ self.inputs.2 }} -o {{ self.outputs.0 }}"
        result = substitute_self_references(
            text, "compile", input_map, output_map, indexed_inputs, indexed_outputs
        )
        self.assertEqual(
            result, "gcc src/main.c src/util.c -I include/*.h -o build/app"
        )

    def test_substitute_mixed_named_and_positional(self):
        """
        Test mixing named and positional access in same text.
        @athena: 626f1b67e8db
        """
        input_map = {"config": "app.json"}
        output_map = {"log": "build.log"}
        indexed_inputs = ["src/main.js", "app.json"]
        indexed_outputs = ["dist/bundle.js", "build.log"]
        text = "build {{ self.inputs.0 }} --config {{ self.inputs.config }} --log {{ self.outputs.1 }}"
        result = substitute_self_references(
            text, "build", input_map, output_map, indexed_inputs, indexed_outputs
        )
        self.assertEqual(result, "build src/main.js --config app.json --log build.log")

    def test_substitute_same_item_by_name_and_index(self):
        """
        Test accessing same item by both name and positional index.
        @athena: 313e1c3198da
        """
        input_map = {"src": "src/app.js"}
        output_map = {}
        indexed_inputs = ["src/app.js"]
        indexed_outputs = []
        text = "cat {{ self.inputs.src }} > copy && cat {{ self.inputs.0 }} > copy2"
        result = substitute_self_references(
            text, "copy", input_map, output_map, indexed_inputs, indexed_outputs
        )
        self.assertEqual(result, "cat src/app.js > copy && cat src/app.js > copy2")

    def test_error_on_out_of_bounds_input_index(self):
        """
        Test error when input index is out of bounds.
        @athena: 252c60951baa
        """
        input_map = {}
        output_map = {}
        indexed_inputs = ["file1.txt", "file2.txt"]
        indexed_outputs = []
        text = "cat {{ self.inputs.5 }}"
        with self.assertRaises(ValueError) as cm:
            substitute_self_references(
                text, "build", input_map, output_map, indexed_inputs, indexed_outputs
            )
        error_msg = str(cm.exception)
        self.assertIn("build", error_msg)
        self.assertIn("input index '5'", error_msg)
        self.assertIn("only has 2 inputs", error_msg)
        self.assertIn("indices 0-1", error_msg)

    def test_error_on_out_of_bounds_output_index(self):
        """
        Test error when output index is out of bounds.
        @athena: 7391f6ffcaee
        """
        input_map = {}
        output_map = {}
        indexed_inputs = []
        indexed_outputs = ["out.txt"]
        text = "echo {{ self.outputs.3 }}"
        with self.assertRaises(ValueError) as cm:
            substitute_self_references(
                text, "task", input_map, output_map, indexed_inputs, indexed_outputs
            )
        error_msg = str(cm.exception)
        self.assertIn("task", error_msg)
        self.assertIn("output index '3'", error_msg)
        self.assertIn("only has 1 outputs", error_msg)
        self.assertIn("indices 0-0", error_msg)

    def test_error_on_empty_inputs_with_index(self):
        """
        Test error when referencing index on empty inputs list.
        @athena: 123459084e84
        """
        input_map = {}
        output_map = {}
        indexed_inputs = []
        indexed_outputs = []
        text = "cat {{ self.inputs.0 }}"
        with self.assertRaises(ValueError) as cm:
            substitute_self_references(
                text, "build", input_map, output_map, indexed_inputs, indexed_outputs
            )
        error_msg = str(cm.exception)
        self.assertIn("build", error_msg)
        self.assertIn("input index '0'", error_msg)
        self.assertIn("no inputs defined", error_msg)

    def test_error_on_empty_outputs_with_index(self):
        """
        Test error when referencing index on empty outputs list.
        @athena: 38ef4134d8f8
        """
        input_map = {}
        output_map = {}
        indexed_inputs = []
        indexed_outputs = []
        text = "echo {{ self.outputs.0 }}"
        with self.assertRaises(ValueError) as cm:
            substitute_self_references(
                text, "task", input_map, output_map, indexed_inputs, indexed_outputs
            )
        error_msg = str(cm.exception)
        self.assertIn("task", error_msg)
        self.assertIn("output index '0'", error_msg)
        self.assertIn("no outputs defined", error_msg)

    def test_substitute_positional_with_glob_patterns(self):
        """
        Test positional access with glob patterns (substituted as-is).
        @athena: a65e3f4936eb
        """
        input_map = {}
        output_map = {}
        indexed_inputs = ["src/**/*.js", "*.json"]
        indexed_outputs = ["dist/*.min.js"]
        text = "bundle {{ self.inputs.0 }} {{ self.inputs.1 }} to {{ self.outputs.0 }}"
        result = substitute_self_references(
            text, "bundle", input_map, output_map, indexed_inputs, indexed_outputs
        )
        # Globs should be substituted verbatim, not expanded
        self.assertEqual(result, "bundle src/**/*.js *.json to dist/*.min.js")


if __name__ == "__main__":
    unittest.main()
