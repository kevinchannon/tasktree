"""
Tests for parser module.
@athena: ce60354ebb27
"""

import os
import platform
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

from tasktree.parser import (
    ArgSpec,
    CircularImportError,
    Task,
    find_recipe_file,
    parse_arg_spec,
    parse_recipe,
)


class TestParseArgSpec(unittest.TestCase):
    """
    @athena: b4dcab139665
    """
    def test_parse_simple_arg(self):
        """
        Test parsing a simple argument name.
        @athena: 67499bbdd11a
        """
        spec = parse_arg_spec("environment")
        self.assertEqual(spec.name,"environment")
        self.assertEqual(spec.arg_type,"str")
        self.assertIsNone(spec.default)
        self.assertFalse(spec.is_exported)

    def test_parse_arg_with_default_raises_error(self):
        """
        Test that string format with default raises error.
        @athena: e67aec3c2b90
        """
        with self.assertRaises(ValueError) as context:
            parse_arg_spec("region=eu-west-1")
        self.assertIn("Invalid argument syntax", str(context.exception))

    def test_parse_arg_with_type_raises_error(self):
        """
        Test that string format with type raises error.
        @athena: a18eb1fe0840
        """
        with self.assertRaises(ValueError) as context:
            parse_arg_spec("port:int")
        self.assertIn("Invalid argument syntax", str(context.exception))

    def test_parse_arg_with_type_and_default_raises_error(self):
        """
        Test that string format with type and default raises error.
        @athena: 4fdb1b6d2f65
        """
        with self.assertRaises(ValueError) as context:
            parse_arg_spec("port:int=8080")
        self.assertIn("Invalid argument syntax", str(context.exception))

    def test_parse_exported_arg(self):
        """
        Test parsing exported argument ($ prefix).
        @athena: f83acb5c8911
        """
        spec = parse_arg_spec("$server")
        self.assertEqual(spec.name,"server")
        self.assertEqual(spec.arg_type,"str")
        self.assertIsNone(spec.default)
        self.assertTrue(spec.is_exported)

    def test_parse_exported_arg_with_default_raises_error(self):
        """
        Test that exported argument string format with default raises error.
        @athena: ec87bfd499c4
        """
        with self.assertRaises(ValueError) as context:
            parse_arg_spec("$user=admin")
        self.assertIn("Invalid argument syntax", str(context.exception))

    def test_parse_exported_arg_with_type_raises_error(self):
        """
        Test that exported arguments with type annotations raise error.
        @athena: d47849f02619
        """
        with self.assertRaises(ValueError) as context:
            parse_arg_spec("$server:str")
        self.assertIn("Invalid argument syntax", str(context.exception))

    def test_parse_exported_arg_with_type_and_default_raises_error(self):
        """
        Test that exported arguments with type and default raise error.
        @athena: 97fd3d7419e7
        """
        with self.assertRaises(ValueError) as context:
            parse_arg_spec("$port:int=8080")
        self.assertIn("Invalid argument syntax", str(context.exception))

    def test_yaml_parses_dollar_prefix_as_literal(self):
        """
        Test that PyYAML correctly parses $ prefix as literal text.
        @athena: 24f85fa51c90
        """
        yaml_text = """
args:
  - $server
  - environment
"""
        data = yaml.safe_load(yaml_text)
        self.assertEqual(data["args"][0], "$server")
        self.assertEqual(data["args"][1], "environment")


class TestParseArgSpecYAML(unittest.TestCase):
    """
    Tests for YAML-based argument syntax.
    @athena: 9cb3bbabc633
    """

    def test_parse_simple_string_arg(self):
        """
        Test parsing simple argument as string.
        @athena: 3536c7525ab1
        """
        spec = parse_arg_spec("key1")
        self.assertEqual(spec.name,"key1")
        self.assertEqual(spec.arg_type,"str")
        self.assertIsNone(spec.default)
        self.assertFalse(spec.is_exported)

    def test_parse_arg_with_default_only(self):
        """
        Test argument with default value, no explicit type.
        @athena: a48befc1fee0
        """
        spec = parse_arg_spec({"key2": {"default": "foo"}})
        self.assertEqual(spec.name,"key2")
        self.assertEqual(spec.arg_type,"str")
        self.assertEqual(spec.default,"foo")
        self.assertFalse(spec.is_exported)

    def test_parse_arg_with_type_only(self):
        """
        Test argument with type, no default.
        @athena: c9939f5f33cc
        """
        spec = parse_arg_spec({"port": {"type": "int"}})
        self.assertEqual(spec.name,"port")
        self.assertEqual(spec.arg_type,"int")
        self.assertIsNone(spec.default)
        self.assertFalse(spec.is_exported)

    def test_parse_arg_with_type_and_default(self):
        """
        Test argument with both type and default.
        @athena: 70ec1df550a8
        """
        spec = parse_arg_spec({"port": {"type": "int", "default": 8080}})
        self.assertEqual(spec.name,"port")
        self.assertEqual(spec.arg_type,"int")
        self.assertEqual(spec.default,"8080")
        self.assertFalse(spec.is_exported)

    def test_parse_exported_arg_dict_syntax(self):
        """
        Test exported argument using dictionary syntax.
        @athena: 6515e1439062
        """
        spec = parse_arg_spec({"$server": {"default": "localhost"}})
        self.assertEqual(spec.name,"server")
        self.assertEqual(spec.arg_type,"str")
        self.assertEqual(spec.default,"localhost")
        self.assertTrue(spec.is_exported)

    def test_infer_type_from_string_default(self):
        """
        Test type inference from string default value.
        @athena: a297dfbd435c
        """
        spec = parse_arg_spec({"name": {"default": "foo"}})
        self.assertEqual(spec.arg_type,"str")

    def test_infer_type_from_int_default(self):
        """
        Test type inference from int default value.
        @athena: a6c44b98e6b4
        """
        spec = parse_arg_spec({"count": {"default": 42}})
        self.assertEqual(spec.arg_type,"int")

    def test_infer_type_from_float_default(self):
        """
        Test type inference from float default value.
        @athena: 162f231b0e13
        """
        spec = parse_arg_spec({"pi": {"default": 3.14}})
        self.assertEqual(spec.arg_type,"float")

    def test_infer_type_from_bool_default(self):
        """
        Test type inference from bool default value.
        @athena: 5c71880b6cb5
        """
        spec = parse_arg_spec({"enabled": {"default": True}})
        self.assertEqual(spec.arg_type,"bool")

    def test_reject_unknown_type(self):
        """
        Test error on unsupported type name.
        @athena: 8ad88de3e14c
        """
        with self.assertRaises(ValueError) as cm:
            parse_arg_spec({"arg": {"type": "unknown"}})
        self.assertIn("Unknown type", str(cm.exception))
        self.assertIn("unknown", str(cm.exception))

    def test_reject_invalid_dict_keys(self):
        """
        Test error on unknown dictionary properties.
        @athena: fdb3645e5768
        """
        with self.assertRaises(ValueError) as cm:
            parse_arg_spec({"arg": {"type": "int", "invalid_key": "value"}})
        self.assertIn("Invalid keys", str(cm.exception))
        self.assertIn("invalid_key", str(cm.exception))

    def test_reject_empty_arg_name(self):
        """
        Test error on empty string argument name.
        @athena: 69290cb66c91
        """
        with self.assertRaises(ValueError) as cm:
            parse_arg_spec({"": {"default": "value"}})
        self.assertIn("non-empty string", str(cm.exception))

    def test_reject_exported_arg_with_type(self):
        """
        Test that exported args with type annotations raise error.
        @athena: f3078fe834c3
        """
        with self.assertRaises(ValueError) as cm:
            parse_arg_spec({"$server": {"type": "int"}})
        self.assertIn("Type annotations not allowed", str(cm.exception))
        self.assertIn("$server", str(cm.exception))

    def test_parse_inline_dict_syntax(self):
        """
        Test flow mapping syntax { type: int, default: 42 }.
        @athena: f9502ddbb360
        """
        # YAML parses inline dicts the same as block dicts
        spec = parse_arg_spec({"key": {"type": "int", "default": 42}})
        self.assertEqual(spec.name,"key")
        self.assertEqual(spec.arg_type,"int")
        self.assertEqual(spec.default,"42")

    def test_null_default_value(self):
        """
        Test explicit default: null or default: ~.
        @athena: 88d0ecd3f95a
        """
        spec = parse_arg_spec({"arg": {"default": None}})
        self.assertEqual(spec.name,"arg")
        self.assertEqual(spec.arg_type,"str")
        # None default remains as None (not converted to string)
        self.assertIsNone(spec.default)

    def test_reject_incompatible_default(self):
        """
        Test error when default doesn't match declared type.
        @athena: 753acf3566f6
        """
        with self.assertRaises(ValueError) as cm:
            parse_arg_spec({"port": {"type": "int", "default": "not_a_number"}})
        self.assertIn("incompatible", str(cm.exception).lower())

    def test_reject_multiple_keys_in_dict(self):
        """
        Test error when argument dict has multiple keys.
        @athena: b37f59d5c50a
        """
        with self.assertRaises(ValueError) as cm:
            parse_arg_spec({"arg1": {"default": "foo"}, "arg2": {"default": "bar"}})
        self.assertIn("exactly one key", str(cm.exception))

    def test_string_defaults_with_special_chars(self):
        """
        Test string defaults with quotes, newlines, etc.
        @athena: 7dace68cf12f
        """
        spec = parse_arg_spec({"msg": {"default": "hello\nworld"}})
        self.assertEqual(spec.default,"hello\nworld")

    def test_empty_config_dict(self):
        """
        Test empty config dict defaults to str type with no default.
        @athena: 1fe93328afcd
        """
        spec = parse_arg_spec({"arg": {}})
        self.assertEqual(spec.name,"arg")
        self.assertEqual(spec.arg_type,"str")
        self.assertIsNone(spec.default)
        self.assertFalse(spec.is_exported)

    def test_mixed_string_and_dict_formats(self):
        """
        Test mixing string and dict argument formats in same list.
        @athena: 08399e3294f5
        """
        # Parse different formats
        simple = parse_arg_spec("env")
        with_default = parse_arg_spec({"region": {"default": "us-east-1"}})
        with_type = parse_arg_spec({"port": {"type": "int", "default": 8080}})
        exported = parse_arg_spec("$server")

        # Verify simple string format
        self.assertEqual(simple.name, "env")
        self.assertEqual(simple.arg_type, "str")
        self.assertIsNone(simple.default)
        self.assertFalse(simple.is_exported)

        # Verify dict with default
        self.assertEqual(with_default.name, "region")
        self.assertEqual(with_default.arg_type, "str")
        self.assertEqual(with_default.default, "us-east-1")
        self.assertFalse(with_default.is_exported)

        # Verify dict with type and default
        self.assertEqual(with_type.name, "port")
        self.assertEqual(with_type.arg_type, "int")
        self.assertEqual(with_type.default, "8080")
        self.assertFalse(with_type.is_exported)

        # Verify exported string format
        self.assertEqual(exported.name, "server")
        self.assertEqual(exported.arg_type, "str")
        self.assertIsNone(exported.default)
        self.assertTrue(exported.is_exported)


class TestParseArgSpecChoices(unittest.TestCase):
    """
    Tests for choices validation in argument specifications.
    @athena: 73bd6c90540d
    """

    def test_valid_choices_with_explicit_type(self):
        """
        Test choices with explicit type match.
        @athena: caca0b064c10
        """
        spec = parse_arg_spec(
            {"environment": {"type": "str", "choices": ["dev", "staging", "prod"]}}
        )
        self.assertEqual(spec.name,"environment")
        self.assertEqual(spec.arg_type,"str")
        self.assertIsNone(spec.default)
        self.assertEqual(spec.choices,["dev", "staging", "prod"])

    def test_valid_choices_with_type_inference(self):
        """
        Test type inference from choices.
        @athena: 3ac3d802e75b
        """
        spec = parse_arg_spec(
            {"region": {"choices": ["us-east-1", "eu-west-1"]}}
        )
        self.assertEqual(spec.name,"region")
        self.assertEqual(spec.arg_type,"str")
        self.assertEqual(spec.choices,["us-east-1", "eu-west-1"])

    def test_int_choices_inferred(self):
        """
        Test type inference from integer choices.
        @athena: 1f8a31ab11f0
        """
        spec = parse_arg_spec(
            {"priority": {"choices": [1, 2, 3]}}
        )
        self.assertEqual(spec.name,"priority")
        self.assertEqual(spec.arg_type,"int")
        self.assertEqual(spec.choices,[1, 2, 3])

    def test_empty_choices_list_error(self):
        """
        Test that empty choices list produces error.
        @athena: 3724544e5fad
        """
        with self.assertRaises(ValueError) as cm:
            parse_arg_spec({"arg": {"choices": []}})
        self.assertIn("empty", str(cm.exception).lower())

    def test_mixed_types_in_choices_error(self):
        """
        Test that mixed types in choices produces error.
        @athena: a5ebe8540ce9
        """
        with self.assertRaises(ValueError) as cm:
            parse_arg_spec({"arg": {"choices": [1, "two", 3]}})
        self.assertIn("same type", str(cm.exception).lower())

    def test_boolean_type_with_choices_error(self):
        """
        Test that boolean type with choices produces error.
        @athena: f7ab084125ac
        """
        with self.assertRaises(ValueError) as cm:
            parse_arg_spec({"flag": {"type": "bool", "choices": [True, False]}})
        self.assertIn("boolean", str(cm.exception).lower())

    def test_choices_and_min_mutual_exclusivity(self):
        """
        Test that choices and min are mutually exclusive.
        @athena: 303da24a5e7e
        """
        with self.assertRaises(ValueError) as cm:
            parse_arg_spec({"arg": {"type": "int", "choices": [1, 2, 3], "min": 1}})
        self.assertIn("mutually exclusive", str(cm.exception).lower())

    def test_choices_and_max_mutual_exclusivity(self):
        """
        Test that choices and max are mutually exclusive.
        @athena: 6546db267941
        """
        with self.assertRaises(ValueError) as cm:
            parse_arg_spec({"arg": {"type": "int", "choices": [1, 2, 3], "max": 10}})
        self.assertIn("mutually exclusive", str(cm.exception).lower())

    def test_default_in_choices_valid(self):
        """
        Test that default value in choices passes.
        @athena: 9863e98b347e
        """
        spec = parse_arg_spec(
            {"env": {"choices": ["dev", "prod"], "default": "dev"}}
        )
        self.assertEqual(spec.default,"dev")
        self.assertEqual(spec.choices,["dev", "prod"])

    def test_default_not_in_choices_error(self):
        """
        Test that default value not in choices produces error.
        @athena: d12850bdf1ef
        """
        with self.assertRaises(ValueError) as cm:
            parse_arg_spec({"env": {"choices": ["dev", "prod"], "default": "staging"}})
        self.assertIn("not in the choices list", str(cm.exception))

    def test_choice_values_match_explicit_type(self):
        """
        Test that explicit type validation works with choices.
        @athena: 8b63b57d2eff
        """
        spec = parse_arg_spec(
            {"count": {"type": "int", "choices": [1, 2, 3]}}
        )
        self.assertEqual(spec.arg_type,"int")
        self.assertEqual(spec.choices,[1, 2, 3])

    def test_choice_values_dont_match_explicit_type_error(self):
        """
        Test that choice values not matching explicit type produces error.
        @athena: 0e77d77e640b
        """
        with self.assertRaises(ValueError) as cm:
            parse_arg_spec({"count": {"type": "int", "choices": ["one", "two"]}})
        self.assertIn("do not match explicit type", str(cm.exception))

    def test_string_choices_with_spaces(self):
        """
        Test that string choices with spaces parse correctly.
        @athena: d7bcbf7ec559
        """
        spec = parse_arg_spec(
            {"message": {"choices": ["hello world", "foo bar"]}}
        )
        self.assertEqual(spec.choices,["hello world", "foo bar"])

    def test_choices_not_a_list_error(self):
        """
        Test that non-list choices value produces error.
        @athena: 198108e32695
        """
        with self.assertRaises(ValueError) as cm:
            parse_arg_spec({"arg": {"choices": "not a list"}})
        self.assertIn("must be a list", str(cm.exception))

    def test_float_choices(self):
        """
        Test float choices.
        @athena: 88669b2c5736
        """
        spec = parse_arg_spec(
            {"ratio": {"type": "float", "choices": [0.5, 1.0, 1.5]}}
        )
        self.assertEqual(spec.arg_type,"float")
        self.assertEqual(spec.choices,[0.5, 1.0, 1.5])

    def test_type_inference_from_choices_and_default_consistent(self):
        """
        Test that type inferred from choices and default is consistent.
        @athena: 2113b93ff410
        """
        spec = parse_arg_spec(
            {"priority": {"choices": [1, 2, 3], "default": 2}}
        )
        self.assertEqual(spec.arg_type,"int")
        self.assertEqual(spec.default,"2")
        self.assertEqual(spec.choices,[1, 2, 3])

    def test_type_inference_from_choices_and_default_inconsistent_error(self):
        """
        Test that inconsistent types from choices and default produces error.
        @athena: f23f32b01091
        """
        with self.assertRaises(ValueError) as cm:
            parse_arg_spec({"arg": {"choices": [1, 2, 3], "default": "two"}})
        self.assertIn("inconsistent types", str(cm.exception).lower())


class TestParseRecipe(unittest.TestCase):
    """
    @athena: 695c25ca011d
    """
    def test_parse_simple_recipe(self):
        """
        Test parsing a simple recipe with one task.
        @athena: 147d77144398
        """
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
        """
        Test parsing task with all fields.
        @athena: d9f0453ac8b2
        """
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
    args:
      - environment
      - region: { default: eu-west-1 }
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
            self.assertEqual(len(task.args), 2)
            self.assertEqual(task.args[0], "environment")
            self.assertIsInstance(task.args[1], dict)
            self.assertEqual(task.cmd, "cargo build --release")

    def test_parse_with_imports(self):
        """
        Test parsing recipe with imports.
        @athena: 42fa38e28be2
        """
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
    """
    Test parsing of recipe imports with various edge cases.
    @athena: 319e48cf208f
    """

    def test_multiple_imports(self):
        """
        Test importing multiple files.
        @athena: 8c7fcdb3762d
        """
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
        """
        Test that imported files can also have imports (nested imports).
        @athena: 16ab982b2458
        """
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
        """
        Test deeply nested imports (A -> B -> C -> D).
        @athena: 3ba567205706
        """
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
        """
        Test diamond import pattern: A imports B and C, both import D.
        @athena: 7093af75b433
        """
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
        """
        Test that importing a non-existent file raises an error.
        @athena: 1df1f94b4188
        """
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
        """
        Test importing files from subdirectories.
        @athena: 5bd0de94c6a7
        """
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
        """
        Test that imported tasks preserve all their properties.
        @athena: c0bebc6e3520
        """
        with TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "import.yaml").write_text("""
tasks:
  build:
    desc: Build the project
    inputs: ["src/**/*.rs"]
    outputs: [target/release/bin]
    working_dir: subproject
    args:
      - environment
      - region: { default: eu-west-1 }
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
            self.assertEqual(task.args, ["environment", {"region": {"default": "eu-west-1"}}])
            self.assertEqual(task.cmd, "cargo build --release")

    def test_cross_import_dependencies(self):
        """
        Test tasks in one import depending on tasks from another import.
        @athena: 5ad884cf371b
        """
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
        """
        Test importing a file with no tasks.
        @athena: 38c0ebb26ea1
        """
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
        """
        Test importing a file that only contains whitespace/comments.
        @athena: 7317e9a25a05
        """
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
        """
        Test that a file importing itself raises CircularImportError.
        @athena: 290c9fa70ca6
        """
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
        """
        Test that A→B→A circular import is detected.
        @athena: 8b860af9e446
        """
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
        """
        Test that A→B→C→A circular import is detected.
        @athena: 63d0f9256966
        """
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
        """
        Test imports are resolved relative to importing file, not project root.
        @athena: 98c707dca92a
        """
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
        """
        Test clear error when nested import file doesn't exist.
        @athena: ca8b14aaef31
        """
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
    """
    Test parsing of different YAML multi-line command formats.
    @athena: f953809cf8ee
    """

    def test_parse_single_line_command(self):
        """
        Test parsing a single-line command (cmd: <string>).
        @athena: 2daac4587382
        """
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
        """
        Test parsing literal block scalar (cmd: |) which preserves newlines.
        @athena: 3abaca901bdf
        """
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
        """
        Test parsing folded block scalar (cmd: >) which folds newlines into spaces.
        @athena: b0605ec8c4d2
        """
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
        """
        Test parsing literal block with actual shell commands.
        @athena: 1742ea96d128
        """
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
        """
        Test parsing literal block that uses shell variables.
        @athena: ea06c6fabb01
        """
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
        """
        Test that literal block scalar (|-) strips final newlines.
        @athena: 9556310da2cb
        """
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
    """
    Tests for parser error conditions.
    @athena: e165b0c2f080
    """

    def test_parse_invalid_yaml_syntax(self):
        """
        Test yaml.YAMLError is raised for invalid YAML.
        @athena: 1b300b5a3645
        """
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
        """
        Test ValueError when task is not a dict.
        @athena: 73a2e28a87d1
        """
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
        """
        Test ValueError when task has no 'cmd' field.
        @athena: 5b5724de006d
        """
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
    """
    Tests for find_recipe_file() function.
    @athena: a3c317024b21
    """

    def test_find_recipe_file_current_dir_tasktree(self):
        """
        Test finds tasktree.yaml in current directory.
        @athena: 71e768948bda
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir).resolve()
            recipe_path = project_root / "tasktree.yaml"
            recipe_path.write_text("tasks:\n  build:\n    cmd: echo test")

            result = find_recipe_file(project_root)
            self.assertEqual(result, recipe_path)

    def test_find_recipe_file_current_dir_tt(self):
        """
        Test finds tt.yaml in current directory.
        @athena: b85370716d64
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir).resolve()
            recipe_path = project_root / "tt.yaml"
            recipe_path.write_text("tasks:\n  build:\n    cmd: echo test")

            result = find_recipe_file(project_root)
            self.assertEqual(result, recipe_path)

    def test_find_recipe_file_parent_directory(self):
        """
        Test searches parent directories.
        @athena: 2bfaafedc9da
        """
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
        """
        Test returns None when no recipe at root.
        @athena: 4d3bdb6ed817
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            result = find_recipe_file(project_root)
            self.assertIsNone(result)

    def test_find_recipe_file_multiple_files_raises_error(self):
        """
        Test raises error when multiple recipe files found.
        @athena: b0cee4bdc7e0
        """
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
        """
        Test finds tasktree.yml (with .yml extension).
        @athena: 786ee1ce1687
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir).resolve()
            recipe_path = project_root / "tasktree.yml"
            recipe_path.write_text("tasks:\n  build:\n    cmd: echo test")

            result = find_recipe_file(project_root)
            self.assertEqual(result, recipe_path)

    def test_find_recipe_file_tasks_extension(self):
        """
        Test finds *.tasks files.
        @athena: 4758dbb59056
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir).resolve()
            recipe_path = project_root / "build.tasks"
            recipe_path.write_text("tasks:\n  build:\n    cmd: echo test")

            result = find_recipe_file(project_root)
            self.assertEqual(result, recipe_path)

    def test_find_recipe_file_multiple_tasks_files_raises_error(self):
        """
        Test raises error when multiple *.tasks files found.
        @athena: c0cf7cd0a199
        """
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

    def test_find_recipe_file_prefers_standard_over_tasks(self):
        """
        Test that standard recipe files are preferred over *.tasks files.
        @athena: 60e103ff0f24
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir).resolve()
            standard_file = project_root / "tasktree.yaml"
            tasks_file = project_root / "build.tasks"

            # Create both files
            standard_file.write_text("tasks:\n  main:\n    cmd: echo from standard")
            tasks_file.write_text("tasks:\n  build:\n    cmd: echo from tasks")

            # Should prefer standard file
            result = find_recipe_file(project_root)
            self.assertEqual(result, standard_file)

    def test_find_recipe_file_uses_tasks_when_no_standard(self):
        """
        Test that *.tasks files are used when no standard files exist.
        @athena: 99175afa1f6d
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir).resolve()
            tasks_file = project_root / "build.tasks"

            # Create only *.tasks file
            tasks_file.write_text("tasks:\n  build:\n    cmd: echo test")

            # Should find and use the *.tasks file
            result = find_recipe_file(project_root)
            self.assertEqual(result, tasks_file)

    def test_find_recipe_file_standard_precedence_order(self):
        """
        Test that tasktree.yaml is preferred over tt.yaml.
        @athena: 6e8a0bedb48f
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir).resolve()
            tasktree_file = project_root / "tasktree.yaml"
            tt_file = project_root / "tt.yaml"

            # Create both standard files
            tasktree_file.write_text("tasks:\n  from_tasktree:\n    cmd: echo tasktree")
            tt_file.write_text("tasks:\n  from_tt:\n    cmd: echo tt")

            # Both exist, so should raise error about multiple files
            with self.assertRaises(ValueError) as cm:
                find_recipe_file(project_root)

            error_msg = str(cm.exception)
            self.assertIn("Multiple recipe files found", error_msg)

    def test_find_recipe_file_no_error_with_standard_and_tasks(self):
        """
        Test no error when both standard file and *.tasks file exist.
        @athena: 6c5ab1931206
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir).resolve()
            standard_file = project_root / "tasktree.yaml"
            tasks_file1 = project_root / "build.tasks"
            tasks_file2 = project_root / "deploy.tasks"

            # Create standard file and multiple *.tasks files
            standard_file.write_text("tasks:\n  main:\n    cmd: echo main")
            tasks_file1.write_text("tasks:\n  build:\n    cmd: echo build")
            tasks_file2.write_text("tasks:\n  deploy:\n    cmd: echo deploy")

            # Should use standard file without error (*.tasks files are imports)
            result = find_recipe_file(project_root)
            self.assertEqual(result, standard_file)


class TestEnvironmentParsing(unittest.TestCase):
    """
    Test parsing of environments section.
    @athena: d26d8e7985bc
    """

    def test_parse_environments_section(self):
        """
        Test parsing environments from YAML.
        @athena: 03e6cef6b608
        """
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
        """
        Test parsing recipe without environments section.
        @athena: 13063935f2aa
        """
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
        """
        Test error when environment doesn't specify shell.
        @athena: b5583ce5e1f3
        """
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
    """
    Tests for validating that tasks must be under 'tasks:' key.
    @athena: fefb526c31cb
    """

    def test_missing_tasks_key_with_task_definitions(self):
        """
        Test that root-level task definitions raise an error.
        @athena: 965522f31ff7
        """
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
        """
        Test that unknown top-level keys raise an error.
        @athena: 7d249a71c49e
        """
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
        """
        Test that an empty YAML file is valid (no tasks defined).
        @athena: ae6c49628fa9
        """
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("")

            recipe = parse_recipe(recipe_path)

            self.assertEqual(len(recipe.tasks), 0)

    def test_only_import_no_tasks(self):
        """
        Test that a file with only imports is valid.
        @athena: 3e1b4d7f2722
        """
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
        """
        Test that a file with only environments is valid.
        @athena: 142ca87d12f9
        """
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
        """
        Test that a task named 'tasks' is allowed under tasks: key.
        @athena: 086df041bd15
        """
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
        """
        Test that tasks: {} or tasks: with no value is valid.
        @athena: b92a0619bfe2
        """
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


class TestArgsValidation(unittest.TestCase):
    """
    Tests for validating task args must be a list, not a dict.
    @athena: b99a3a787009
    """

    def test_args_dict_syntax_raises_error(self):
        """
        Test that dictionary syntax for args raises a helpful error.
        @athena: 9806bb153694
        """
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
tasks:
  foo:
    args:
      x: {}
      y: { type: int, default: 10 }
    cmd: echo x = {{ arg.x }}, y = {{ arg.y }}
""")

            with self.assertRaises(ValueError) as cm:
                parse_recipe(recipe_path)

            error_msg = str(cm.exception)
            self.assertIn("invalid 'args' syntax", error_msg)
            self.assertIn("dictionary syntax", error_msg)
            self.assertIn("list format", error_msg)
            self.assertIn("with dashes", error_msg)
            # Should show the first key as an example
            self.assertIn("x", error_msg)

    def test_args_list_syntax_is_valid(self):
        """
        Test that list syntax for args works correctly.
        @athena: c034fd57e86d
        """
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
tasks:
  foo:
    args:
      - x
      - y: { type: int, default: 10 }
    cmd: echo x = {{ arg.x }}, y = {{ arg.y }}
""")

            # Should parse without error
            recipe = parse_recipe(recipe_path)

            # Verify the task was parsed correctly
            self.assertIn("foo", recipe.tasks)
            task = recipe.tasks["foo"]
            self.assertEqual(len(task.args), 2)

    def test_args_empty_dict_raises_error(self):
        """
        Test that even an empty dict for args raises an error.
        @athena: 142a261feb16
        """
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
tasks:
  foo:
    args: {}
    cmd: echo hello
""")

            with self.assertRaises(ValueError) as cm:
                parse_recipe(recipe_path)

            error_msg = str(cm.exception)
            self.assertIn("invalid 'args' syntax", error_msg)
            self.assertIn("dictionary syntax", error_msg)


class TestVariablesParsing(unittest.TestCase):
    """
    Test parsing of variables section with environment variable support.
    @athena: 814b65b0c54f
    """

    def test_parse_env_variable_basic(self):
        """
        Test basic environment variable reference.
        @athena: c6006cb83f84
        """
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
        """
        Test error when environment variable is not set.
        @athena: f07a58e4b9c4
        """
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
        """
        Test env variable used in other variable definitions.
        @athena: 0afdef2e4fc8
        """
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
        """
        Test env variable values are always strings.
        @athena: 41c08394af0a
        """
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
        """
        Test error for { env: VAR, other: value } syntax.
        @athena: e12c0211169a
        """
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
variables:
  my_var: { env: TEST_VAR, foo: "bar" }

tasks:
  test:
    cmd: echo test
""")

            with self.assertRaises(ValueError) as cm:
                parse_recipe(recipe_path)

            error_msg = str(cm.exception)
            self.assertIn("found invalid keys", error_msg.lower())
            self.assertIn("foo", error_msg)

    def test_parse_env_variable_invalid_name_empty(self):
        """
        Test error for { env: } with empty value.
        @athena: 166a5904b6f9
        """
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
        """
        Test error for invalid env var name format.
        @athena: 2ba4e2699acc
        """
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
        """
        Test multiple environment variables in same recipe.
        @athena: b30c27f69ce5
        """
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
        """
        Test mixing regular variables and env variables.
        @athena: 2134fba11048
        """
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
    """
    Test parsing of variables section with file read support.
    @athena: 402549e8335a
    """

    def test_file_read_basic(self):
        """
        Test basic file reading.
        @athena: 7c9157f47ccc
        """
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
        """
        Test trailing newline is stripped.
        @athena: dd6d01c7f588
        """
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
        """
        Test empty file returns empty string.
        @athena: 1424682aad7a
        """
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
        """
        Test file with only newline returns empty string.
        @athena: 9965d872e1f5
        """
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
        """
        Test multi-line content preserved.
        @athena: 8f00e89a47cb
        """
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
        """
        Test whitespace preserved except final newline.
        @athena: d99de0b57856
        """
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
        """
        Test relative path resolves from recipe file.
        @athena: 28a08e07173e
        """
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
        """
        Test nested relative path like secrets/api-key.txt.
        @athena: 8db028b6befd
        """
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
        """
        Test absolute paths work.
        @athena: 58ea16fcff26
        """
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
        """
        Test tilde expands to home directory.
        @athena: 70378a8685ee
        """
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
        """
        Test error when file doesn't exist.
        @athena: 3602fc4ceb32
        """
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
        """
        Test error for binary file.
        @athena: 15d54f6c6cb1
        """
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
        """
        Test file content used in other variables.
        @athena: 6fdd985e75db
        """
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
        """
        Test error for extra keys in file read reference.
        @athena: f6ec20bb75e0
        """
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
        """
        Test error for empty filepath.
        @athena: 13039bba9130
        """
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
        """
        Test all three variable types together.
        @athena: 121b485abf2d
        """
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
    """
    Tests for { eval: command } variable references.
    @athena: f3969144409f
    """

    def test_eval_basic_command(self):
        """
        Test basic command evaluation.
        @athena: 4d005f685091
        """
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
        """
        Test that trailing newline is stripped from command output.
        @athena: d114ad180bdb
        """
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
        """
        Test that internal newlines are preserved.
        @athena: d4c3c941e6c6
        """
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
        """
        Test command with empty output.
        @athena: ce452a6bf328
        """
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
        """
        Test that non-zero exit code raises error.
        @athena: 0f6561806aa6
        """
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
        """
        Test that nonexistent command produces helpful error.
        @athena: abd7cae3accc
        """
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
        """
        Test that command runs from recipe file directory.
        @athena: 3f2520b23031
        """
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
        """
        Test eval output can use variable substitution.
        @athena: e9955ba30e79
        """
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
        """
        Test that eval output itself can contain variable references.
        @athena: eeb98bc29c6c
        """
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
        """
        Test validation error when eval has no command.
        @athena: 2765fbf60ce4
        """
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
        """
        Test validation error when eval has extra keys.
        @athena: 999df61ae166
        """
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
        """
        Test validation error when command is not a string.
        @athena: 3c19e4866494
        """
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
        """
        Test that eval uses default environment if specified.
        @athena: 4121942be054
        """
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
        """
        Test that commands with pipes work correctly.
        @athena: 7b5b16b6cdce
        """
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
        """
        Test eval works alongside env and read variables.
        @athena: 46ebb6e2db91
        """
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


class TestArgMinMax(unittest.TestCase):
    """
    Tests for min/max range constraints on arguments.
    @athena: 20b694272427
    """

    def test_parse_int_with_min_and_max(self):
        """
        Test integer argument with both min and max constraints.
        @athena: aac03923122e
        """
        spec = parse_arg_spec(
            {"replicas": {"type": "int", "min": 1, "max": 100}}
        )
        self.assertEqual(spec.name,"replicas")
        self.assertEqual(spec.arg_type,"int")
        self.assertIsNone(spec.default)
        self.assertFalse(spec.is_exported)
        self.assertEqual(spec.min_val,1)
        self.assertEqual(spec.max_val,100)

    def test_parse_float_with_min_and_max(self):
        """
        Test float argument with both min and max constraints.
        @athena: 8e4d405797ac
        """
        spec = parse_arg_spec(
            {"timeout": {"type": "float", "min": 0.5, "max": 30.0}}
        )
        self.assertEqual(spec.name,"timeout")
        self.assertEqual(spec.arg_type,"float")
        self.assertIsNone(spec.default)
        self.assertFalse(spec.is_exported)
        self.assertEqual(spec.min_val,0.5)
        self.assertEqual(spec.max_val,30.0)

    def test_parse_int_with_min_only(self):
        """
        Test integer argument with only min constraint.
        @athena: e5313ad0d32c
        """
        spec = parse_arg_spec(
            {"port": {"type": "int", "min": 1024}}
        )
        self.assertEqual(spec.name,"port")
        self.assertEqual(spec.arg_type,"int")
        self.assertEqual(spec.min_val,1024)
        self.assertIsNone(spec.max_val)

    def test_parse_float_with_max_only(self):
        """
        Test float argument with only max constraint.
        @athena: 3efccf766d20
        """
        spec = parse_arg_spec(
            {"percentage": {"type": "float", "max": 100.0}}
        )
        self.assertEqual(spec.name,"percentage")
        self.assertEqual(spec.arg_type,"float")
        self.assertIsNone(spec.min_val)
        self.assertEqual(spec.max_val,100.0)

    def test_parse_int_with_min_max_and_default(self):
        """
        Test integer argument with min, max, and default value.
        @athena: 1cf32298c201
        """
        spec = parse_arg_spec(
            {"workers": {"type": "int", "min": 1, "max": 16, "default": 4}}
        )
        self.assertEqual(spec.name,"workers")
        self.assertEqual(spec.arg_type,"int")
        self.assertEqual(spec.default,"4")
        self.assertEqual(spec.min_val,1)
        self.assertEqual(spec.max_val,16)

    def test_min_max_only_on_numeric_types_int(self):
        """
        Test that min/max on string type raises error.
        @athena: 32c207456f3b
        """
        with self.assertRaises(ValueError) as cm:
            parse_arg_spec({"name": {"type": "str", "min": 1, "max": 10}})
        self.assertIn("min/max constraints are only supported for 'int' and 'float'", str(cm.exception))

    def test_min_max_only_on_numeric_types_bool(self):
        """
        Test that min/max on bool type raises error.
        @athena: a3933b099ff3
        """
        with self.assertRaises(ValueError) as cm:
            parse_arg_spec({"flag": {"type": "bool", "min": 0, "max": 1}})
        self.assertIn("min/max constraints are only supported for 'int' and 'float'", str(cm.exception))

    def test_min_max_only_on_numeric_types_path(self):
        """
        Test that min/max on path type raises error.
        @athena: 7af90499f011
        """
        with self.assertRaises(ValueError) as cm:
            parse_arg_spec({"file": {"type": "path", "min": 1}})
        self.assertIn("min/max constraints are only supported for 'int' and 'float'", str(cm.exception))

    def test_min_greater_than_max_raises_error(self):
        """
        Test that min > max raises error.
        @athena: 885aefce8339
        """
        with self.assertRaises(ValueError) as cm:
            parse_arg_spec({"value": {"type": "int", "min": 100, "max": 1}})
        self.assertIn("min (100) must be less than or equal to max (1)", str(cm.exception))

    def test_min_equals_max_allowed(self):
        """
        Test that min == max is allowed (edge case).
        @athena: afa6706fd7d4
        """
        spec = parse_arg_spec(
            {"fixed": {"type": "int", "min": 42, "max": 42}}
        )
        self.assertEqual(spec.min_val,42)
        self.assertEqual(spec.max_val,42)

    def test_default_less_than_min_raises_error(self):
        """
        Test that default < min raises error.
        @athena: 236a3349447a
        """
        with self.assertRaises(ValueError) as cm:
            parse_arg_spec({"value": {"type": "int", "min": 10, "default": 5}})
        self.assertIn("Default value", str(cm.exception))
        self.assertIn("less than min", str(cm.exception))

    def test_default_greater_than_max_raises_error(self):
        """
        Test that default > max raises error.
        @athena: 985cd4bf73f2
        """
        with self.assertRaises(ValueError) as cm:
            parse_arg_spec({"value": {"type": "int", "max": 10, "default": 15}})
        self.assertIn("Default value", str(cm.exception))
        self.assertIn("greater than max", str(cm.exception))

    def test_default_within_range(self):
        """
        Test that default within range is accepted.
        @athena: 87edcbf8b8c5
        """
        spec = parse_arg_spec(
            {"value": {"type": "int", "min": 1, "max": 100, "default": 50}}
        )
        self.assertEqual(spec.default,"50")

    def test_default_equals_min(self):
        """
        Test that default == min is accepted.
        @athena: e7a0ff2214a4
        """
        spec = parse_arg_spec(
            {"value": {"type": "int", "min": 10, "max": 100, "default": 10}}
        )
        self.assertEqual(spec.default,"10")

    def test_default_equals_max(self):
        """
        Test that default == max is accepted.
        @athena: 16a5bb78c520
        """
        spec = parse_arg_spec(
            {"value": {"type": "int", "min": 10, "max": 100, "default": 100}}
        )
        self.assertEqual(spec.default,"100")

    def test_float_range_with_precision(self):
        """
        Test float arguments with precision.
        @athena: 3635b664f1b5
        """
        spec = parse_arg_spec(
            {"ratio": {"type": "float", "min": 0.001, "max": 0.999, "default": 0.5}}
        )
        self.assertEqual(spec.min_val,0.001)
        self.assertEqual(spec.max_val,0.999)
        self.assertEqual(spec.default,"0.5")

    def test_negative_int_range(self):
        """
        Test integer range with negative values.
        @athena: 5eb44ecb8313
        """
        spec = parse_arg_spec(
            {"temperature": {"type": "int", "min": -100, "max": 100}}
        )
        self.assertEqual(spec.min_val,-100)
        self.assertEqual(spec.max_val,100)

    def test_negative_float_range(self):
        """
        Test float range with negative values.
        @athena: 60ebe43fcf72
        """
        spec = parse_arg_spec(
            {"offset": {"type": "float", "min": -1.0, "max": 1.0}}
        )
        self.assertEqual(spec.min_val,-1.0)
        self.assertEqual(spec.max_val,1.0)

    def test_string_format_args_have_no_min_max(self):
        """
        Test that string format args return None for min/max.
        @athena: acf122ccbb03
        """
        spec = parse_arg_spec("count")
        self.assertIsNone(spec.min_val)
        self.assertIsNone(spec.max_val)

    def test_inferred_type_with_min_max(self):
        """
        Test that min/max works with inferred int type from default.
        @athena: 0bcbaa60cc5e
        """
        spec = parse_arg_spec(
            {"count": {"default": 5, "min": 1, "max": 10}}
        )
        self.assertEqual(spec.arg_type,"int")
        self.assertEqual(spec.default,"5")
        self.assertEqual(spec.min_val,1)
        self.assertEqual(spec.max_val,10)

    def test_inferred_float_type_with_min_max(self):
        """
        Test that min/max works with inferred float type from default.
        @athena: 4dc1b4d3967c
        """
        spec = parse_arg_spec(
            {"ratio": {"default": 0.5, "min": 0.0, "max": 1.0}}
        )
        self.assertEqual(spec.arg_type,"float")
        self.assertEqual(spec.default,"0.5")
        self.assertEqual(spec.min_val,0.0)
        self.assertEqual(spec.max_val,1.0)


class TestArgTypeInference(unittest.TestCase):
    """
    Tests for type inference from min, max, and default values (Issue #26).
    @athena: ae0f5a6b7bce
    """

    def test_infer_int_from_min_only(self):
        """
        Test type inference from min value alone.
        @athena: 6c93f7f24d26
        """
        spec = parse_arg_spec(
            {"count": {"min": 1}}
        )
        self.assertEqual(spec.arg_type,"int")
        self.assertEqual(spec.min_val,1)
        self.assertIsNone(spec.max_val)
        self.assertIsNone(spec.default)

    def test_infer_int_from_max_only(self):
        """
        Test type inference from max value alone.
        @athena: 439d6583c06c
        """
        spec = parse_arg_spec(
            {"count": {"max": 100}}
        )
        self.assertEqual(spec.arg_type,"int")
        self.assertIsNone(spec.min_val)
        self.assertEqual(spec.max_val,100)
        self.assertIsNone(spec.default)

    def test_infer_float_from_min_only(self):
        """
        Test type inference from float min value.
        @athena: e44e907c17fb
        """
        spec = parse_arg_spec(
            {"ratio": {"min": 0.5}}
        )
        self.assertEqual(spec.arg_type,"float")
        self.assertEqual(spec.min_val,0.5)

    def test_infer_float_from_max_only(self):
        """
        Test type inference from float max value.
        @athena: 76275d56e75e
        """
        spec = parse_arg_spec(
            {"ratio": {"max": 1.0}}
        )
        self.assertEqual(spec.arg_type,"float")
        self.assertEqual(spec.max_val,1.0)

    def test_infer_from_min_and_max_consistent_int(self):
        """
        Test type inference when both min and max are int.
        @athena: 1671994b0cd0
        """
        spec = parse_arg_spec(
            {"port": {"min": 1024, "max": 65535}}
        )
        self.assertEqual(spec.arg_type,"int")
        self.assertEqual(spec.min_val,1024)
        self.assertEqual(spec.max_val,65535)

    def test_infer_from_min_and_max_consistent_float(self):
        """
        Test type inference when both min and max are float.
        @athena: b916dc134458
        """
        spec = parse_arg_spec(
            {"percentage": {"min": 0.0, "max": 100.0}}
        )
        self.assertEqual(spec.arg_type,"float")
        self.assertEqual(spec.min_val,0.0)
        self.assertEqual(spec.max_val,100.0)

    def test_infer_from_all_three_consistent(self):
        """
        Test type inference when default, min, and max are all present and consistent.
        @athena: d128bca223ed
        """
        spec = parse_arg_spec(
            {"workers": {"default": 4, "min": 1, "max": 16}}
        )
        self.assertEqual(spec.arg_type,"int")
        self.assertEqual(spec.default,"4")
        self.assertEqual(spec.min_val,1)
        self.assertEqual(spec.max_val,16)

    def test_error_on_inconsistent_min_max_types(self):
        """
        Test error when min is int but max is float.
        @athena: b673901819ab
        """
        with self.assertRaises(ValueError) as cm:
            parse_arg_spec({"bad": {"min": 1, "max": 10.0}})
        error_msg = str(cm.exception)
        self.assertIn("inconsistent types", error_msg)
        self.assertIn("min=int", error_msg)
        self.assertIn("max=float", error_msg)

    def test_error_on_inconsistent_default_min_types(self):
        """
        Test error when default is str but min is int.
        @athena: 39cfc780695b
        """
        with self.assertRaises(ValueError) as cm:
            parse_arg_spec({"bad": {"default": "hello", "min": 1}})
        error_msg = str(cm.exception)
        self.assertIn("inconsistent types", error_msg)
        self.assertIn("default=str", error_msg)
        self.assertIn("min=int", error_msg)

    def test_error_on_inconsistent_default_max_types(self):
        """
        Test error when default is int but max is float.
        @athena: 7f62544b1c7e
        """
        with self.assertRaises(ValueError) as cm:
            parse_arg_spec({"bad": {"default": 5, "max": 10.0}})
        error_msg = str(cm.exception)
        self.assertIn("inconsistent types", error_msg)
        self.assertIn("default=int", error_msg)
        self.assertIn("max=float", error_msg)

    def test_error_on_all_three_inconsistent(self):
        """
        Test error when default, min, and max have different types.
        @athena: e3f019c8c3a8
        """
        with self.assertRaises(ValueError) as cm:
            parse_arg_spec({"bad": {"default": "text", "min": 1, "max": 10.0}})
        error_msg = str(cm.exception)
        self.assertIn("inconsistent types", error_msg)

    def test_explicit_type_with_matching_default(self):
        """
        Test that explicit type with matching default value works.
        @athena: 7609e6038915
        """
        spec = parse_arg_spec(
            {"count": {"type": "int", "default": 42}}
        )
        self.assertEqual(spec.arg_type,"int")
        self.assertEqual(spec.default,"42")

    def test_explicit_type_with_matching_min_max(self):
        """
        Test that explicit type with matching min/max works.
        @athena: c85ee2745b1e
        """
        spec = parse_arg_spec(
            {"count": {"type": "int", "min": 1, "max": 100}}
        )
        self.assertEqual(spec.arg_type,"int")
        self.assertEqual(spec.min_val,1)
        self.assertEqual(spec.max_val,100)

    def test_error_explicit_type_mismatch_default(self):
        """
        Test error when explicit type doesn't match default type.
        @athena: 42fb2398b34a
        """
        with self.assertRaises(ValueError) as cm:
            parse_arg_spec({"bad": {"type": "int", "default": "text"}})
        error_msg = str(cm.exception)
        self.assertIn("incompatible with type 'int'", error_msg)
        self.assertIn("default has type 'str'", error_msg)

    def test_error_explicit_type_mismatch_min(self):
        """
        Test error when explicit type doesn't match min type.
        @athena: 09d7d24be539
        """
        with self.assertRaises(ValueError) as cm:
            parse_arg_spec({"bad": {"type": "float", "min": 1}})
        error_msg = str(cm.exception)
        self.assertIn("explicit type 'float'", error_msg)
        self.assertIn("min value has type 'int'", error_msg)

    def test_error_explicit_type_mismatch_max(self):
        """
        Test error when explicit type doesn't match max type.
        @athena: 7cee60c294f4
        """
        with self.assertRaises(ValueError) as cm:
            parse_arg_spec({"bad": {"type": "int", "max": 10.0}})
        error_msg = str(cm.exception)
        self.assertIn("explicit type 'int'", error_msg)
        self.assertIn("max value has type 'float'", error_msg)

    def test_error_explicit_type_mismatch_all_values(self):
        """
        Test error when explicit type doesn't match any of default/min/max.
        @athena: 5bc7c6b84ee9
        """
        with self.assertRaises(ValueError) as cm:
            parse_arg_spec({"bad": {"type": "str", "default": 5, "min": 1, "max": 10}})
        error_msg = str(cm.exception)
        # This will fail on default check first (before min/max)
        self.assertIn("incompatible with type 'str'", error_msg)
        self.assertIn("default has type 'int'", error_msg)

    def test_infer_bool_from_default_no_min_max(self):
        """
        Test that bool can be inferred from default (but bool doesn't support min/max).
        @athena: 53058355c260
        """
        spec = parse_arg_spec(
            {"enabled": {"default": True}}
        )
        self.assertEqual(spec.arg_type,"bool")
        self.assertEqual(spec.default,"True")

    def test_infer_str_from_default_no_min_max(self):
        """
        Test that str can be inferred from default.
        @athena: 097b98c688dd
        """
        spec = parse_arg_spec(
            {"name": {"default": "test"}}
        )
        self.assertEqual(spec.arg_type,"str")
        self.assertEqual(spec.default,"test")

    def test_negative_values_in_inference(self):
        """
        Test type inference with negative min/max values.
        @athena: be880882bcc9
        """
        spec = parse_arg_spec(
            {"temperature": {"min": -100, "max": 100, "default": -20}}
        )
        self.assertEqual(spec.arg_type,"int")
        self.assertEqual(spec.min_val,-100)
        self.assertEqual(spec.max_val,100)
        self.assertEqual(spec.default,"-20")

    def test_precedence_all_same_type(self):
        """
        Test that when all values are same type, any can be used for inference.
        @athena: d37e2f50c3fe
        """
        # This should work regardless of which value is checked first
        spec = parse_arg_spec(
            {"value": {"max": 100, "min": 1, "default": 50}}
        )
        self.assertEqual(spec.arg_type,"int")

    def test_float_inference_with_integer_default(self):
        """
        Test that float min/max with integer default causes error.
        @athena: 40e2ce4168cf
        """
        # Integer 5 has type 'int', float 1.0 has type 'float'
        with self.assertRaises(ValueError) as cm:
            parse_arg_spec({"bad": {"min": 1.0, "max": 10.0, "default": 5}})
        error_msg = str(cm.exception)
        self.assertIn("inconsistent types", error_msg)

    def test_inferred_type_default_less_than_min(self):
        """
        Test that default < min raises error with inferred type.
        @athena: a6e8c45c2d4e
        """
        with self.assertRaises(ValueError) as cm:
            parse_arg_spec({"count": {"min": 10, "max": 100, "default": 5}})
        error_msg = str(cm.exception)
        self.assertIn("Default value", error_msg)
        self.assertIn("less than min", error_msg)

    def test_inferred_type_default_greater_than_max(self):
        """
        Test that default > max raises error with inferred type.
        @athena: 61d779f4648d
        """
        with self.assertRaises(ValueError) as cm:
            parse_arg_spec({"count": {"min": 1, "max": 10, "default": 15}})
        error_msg = str(cm.exception)
        self.assertIn("Default value", error_msg)
        self.assertIn("greater than max", error_msg)


class TestNamedOutputs(unittest.TestCase):
    """
    Tests for named output functionality.
    @athena: 0fc04ffa643f
    """

    def test_parse_named_output(self):
        """
        Test parsing a task with named outputs.
        @athena: a457ab1c963f
        """
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
  build:
    outputs:
      - bundle: "dist/app.js"
      - sourcemap: "dist/app.js.map"
    cmd: webpack build
"""
            )

            recipe = parse_recipe(recipe_path)
            task = recipe.tasks["build"]
            self.assertEqual(len(task.outputs), 2)
            self.assertIn({"bundle": "dist/app.js"}, task.outputs)
            self.assertIn({"sourcemap": "dist/app.js.map"}, task.outputs)

            # Check internal maps
            self.assertEqual(task._output_map["bundle"], "dist/app.js")
            self.assertEqual(task._output_map["sourcemap"], "dist/app.js.map")
            self.assertEqual(len(task._anonymous_outputs), 0)

    def test_parse_mixed_outputs(self):
        """
        Test parsing task with both named and anonymous outputs.
        @athena: 2f5a10033f2a
        """
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
  compile:
    outputs:
      - binary: "build/app"
      - "build/app.debug"
      - symbols: "build/app.sym"
    cmd: gcc -o build/app src/*.c
"""
            )

            recipe = parse_recipe(recipe_path)
            task = recipe.tasks["compile"]
            self.assertEqual(len(task.outputs), 3)

            # Check named outputs
            self.assertEqual(task._output_map["binary"], "build/app")
            self.assertEqual(task._output_map["symbols"], "build/app.sym")

            # Check anonymous outputs
            self.assertEqual(len(task._anonymous_outputs), 1)
            self.assertIn("build/app.debug", task._anonymous_outputs)

    def test_parse_anonymous_outputs_only(self):
        """
        Test that existing anonymous-only outputs still work.
        @athena: 9b5b8eb47ff4
        """
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
  build:
    outputs: ["dist/bundle.js", "dist/bundle.css"]
    cmd: build.sh
"""
            )

            recipe = parse_recipe(recipe_path)
            task = recipe.tasks["build"]
            self.assertEqual(len(task.outputs), 2)
            self.assertEqual(task.outputs, ["dist/bundle.js", "dist/bundle.css"])

            # All should be anonymous
            self.assertEqual(len(task._output_map), 0)
            self.assertEqual(len(task._anonymous_outputs), 2)

    def test_named_output_invalid_identifier(self):
        """
        Test that invalid identifier names raise error.
        @athena: 8a0829a85462
        """
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
  build:
    outputs:
      - invalid-name: "dist/app.js"
    cmd: build.sh
"""
            )

            with self.assertRaises(ValueError) as cm:
                parse_recipe(recipe_path)
            error_msg = str(cm.exception)
            self.assertIn("invalid-name", error_msg)
            self.assertIn("valid identifier", error_msg)

    def test_named_output_starts_with_number(self):
        """
        Test that output names starting with numbers raise error.
        @athena: 283ed2005dca
        """
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
  build:
    outputs:
      - 1output: "dist/app.js"
    cmd: build.sh
"""
            )

            with self.assertRaises(ValueError) as cm:
                parse_recipe(recipe_path)
            error_msg = str(cm.exception)
            self.assertIn("1output", error_msg)
            self.assertIn("valid identifier", error_msg)

    def test_named_output_duplicate_names(self):
        """
        Test that duplicate output names raise error.
        @athena: d292b578e111
        """
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
  build:
    outputs:
      - bundle: "dist/app.js"
      - bundle: "dist/app.min.js"
    cmd: build.sh
"""
            )

            with self.assertRaises(ValueError) as cm:
                parse_recipe(recipe_path)
            error_msg = str(cm.exception)
            self.assertIn("Duplicate", error_msg)
            self.assertIn("bundle", error_msg)

    def test_named_output_multiple_keys(self):
        """
        Test that output dicts with multiple keys raise error.
        @athena: ee82d3ce64e7
        """
        task = Task(name="test", cmd="echo test")
        with self.assertRaises(ValueError) as cm:
            task.outputs = [{"key1": "path1", "key2": "path2"}]
            task.__post_init__()
        error_msg = str(cm.exception)
        self.assertIn("exactly one key-value pair", error_msg)

    def test_named_output_non_string_path(self):
        """
        Test that non-string output paths raise error.
        @athena: bc7e2183dac8
        """
        task = Task(name="test", cmd="echo test")
        with self.assertRaises(ValueError) as cm:
            task.outputs = [{"bundle": 123}]
            task.__post_init__()
        error_msg = str(cm.exception)
        self.assertIn("string path", error_msg)

    def test_output_invalid_type(self):
        """
        Test that invalid output types raise error.
        @athena: 40b8fa3c4f93
        """
        task = Task(name="test", cmd="echo test")
        with self.assertRaises(ValueError) as cm:
            task.outputs = [123]
            task.__post_init__()
        error_msg = str(cm.exception)
        self.assertIn("string or dict", error_msg)

    def test_named_output_valid_identifiers(self):
        """
        Test various valid identifier names.
        @athena: b5ac7215644e
        """
        valid_names = ["output", "output_1", "OUTPUT", "_private", "camelCase", "snake_case"]
        for name in valid_names:
            with TemporaryDirectory() as tmpdir:
                recipe_path = Path(tmpdir) / "tasktree.yaml"
                recipe_path.write_text(
                    f"""
tasks:
  build:
    outputs:
      - {name}: "dist/app.js"
    cmd: build.sh
"""
                )
                recipe = parse_recipe(recipe_path)
                task = recipe.tasks["build"]
                self.assertIn(name, task._output_map)

    def test_empty_outputs_list(self):
        """
        Test that empty outputs list works correctly.
        @athena: 48a002e19525
        """
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
  build:
    outputs: []
    cmd: build.sh
"""
            )

            recipe = parse_recipe(recipe_path)
            task = recipe.tasks["build"]
            self.assertEqual(len(task.outputs), 0)
            self.assertEqual(len(task._output_map), 0)
            self.assertEqual(len(task._anonymous_outputs), 0)


class TestNamedInputs(unittest.TestCase):
    """
    Tests for named input functionality.
    @athena: 63af170071dd
    """

    def test_parse_named_input(self):
        """
        Test parsing a task with named inputs.
        @athena: 89326afae047
        """
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
  build:
    inputs:
      - src: "src/app.js"
      - config: "config/app.json"
    cmd: build.sh
"""
            )

            recipe = parse_recipe(recipe_path)
            task = recipe.tasks["build"]
            self.assertEqual(len(task.inputs), 2)
            self.assertIn({"src": "src/app.js"}, task.inputs)
            self.assertIn({"config": "config/app.json"}, task.inputs)

            # Check internal maps
            self.assertEqual(task._input_map["src"], "src/app.js")
            self.assertEqual(task._input_map["config"], "config/app.json")
            self.assertEqual(len(task._anonymous_inputs), 0)

    def test_parse_mixed_inputs(self):
        """
        Test parsing task with both named and anonymous inputs.
        @athena: 82e23422b0b7
        """
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
  compile:
    inputs:
      - src: "src/main.c"
      - headers: "include/**/*.h"
      - "vendor/lib.a"
    cmd: gcc
"""
            )

            recipe = parse_recipe(recipe_path)
            task = recipe.tasks["compile"]
            self.assertEqual(len(task.inputs), 3)

            # Check named inputs
            self.assertEqual(task._input_map["src"], "src/main.c")
            self.assertEqual(task._input_map["headers"], "include/**/*.h")

            # Check anonymous inputs
            self.assertEqual(len(task._anonymous_inputs), 1)
            self.assertIn("vendor/lib.a", task._anonymous_inputs)

    def test_parse_anonymous_inputs(self):
        """
        Test parsing task with only anonymous inputs.
        @athena: 96d7edc86722
        """
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
  build:
    inputs:
      - "src/**/*.js"
      - "config/*.json"
    cmd: build.sh
"""
            )

            recipe = parse_recipe(recipe_path)
            task = recipe.tasks["build"]
            self.assertEqual(len(task.inputs), 2)
            self.assertEqual(task.inputs, ["src/**/*.js", "config/*.json"])

            # All should be anonymous
            self.assertEqual(len(task._input_map), 0)
            self.assertEqual(len(task._anonymous_inputs), 2)

    def test_named_input_invalid_identifier(self):
        """
        Test that invalid identifier names raise error.
        @athena: f8c87f8b3e14
        """
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
  build:
    inputs:
      - invalid-name: "src/app.js"
    cmd: build.sh
"""
            )
            with self.assertRaises(ValueError) as cm:
                parse_recipe(recipe_path)
            error_msg = str(cm.exception)
            self.assertIn("invalid-name", error_msg)
            self.assertIn("valid identifier", error_msg)

    def test_named_input_starts_with_number(self):
        """
        Test that input names starting with numbers raise error.
        @athena: b06b080b901c
        """
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
  build:
    inputs:
      - 1input: "src/app.js"
    cmd: build.sh
"""
            )
            with self.assertRaises(ValueError) as cm:
                parse_recipe(recipe_path)
            error_msg = str(cm.exception)
            self.assertIn("1input", error_msg)
            self.assertIn("valid identifier", error_msg)

    def test_named_input_duplicate_names(self):
        """
        Test that duplicate input names raise error.
        @athena: 3cc7d1a8e465
        """
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
  build:
    inputs:
      - src: "src/app.js"
      - src: "src/main.js"
    cmd: build.sh
"""
            )
            with self.assertRaises(ValueError) as cm:
                parse_recipe(recipe_path)
            error_msg = str(cm.exception)
            self.assertIn("Duplicate", error_msg)
            self.assertIn("src", error_msg)

    def test_named_input_multiple_keys(self):
        """
        Test that input dicts with multiple keys raise error.
        @athena: a567d3f4fb48
        """
        task = Task(name="test", cmd="echo test")
        with self.assertRaises(ValueError) as cm:
            task.inputs = [{"key1": "path1", "key2": "path2"}]
            task.__post_init__()
        error_msg = str(cm.exception)
        self.assertIn("exactly one key-value pair", error_msg)

    def test_named_input_non_string_path(self):
        """
        Test that non-string input paths raise error.
        @athena: d57fb5d2d10f
        """
        task = Task(name="test", cmd="echo test")
        with self.assertRaises(ValueError) as cm:
            task.inputs = [{"src": 123}]
            task.__post_init__()
        error_msg = str(cm.exception)
        self.assertIn("string path", error_msg)

    def test_invalid_input_type(self):
        """
        Test that invalid input types raise error.
        @athena: 21378c23b17f
        """
        task = Task(name="test", cmd="echo test")
        with self.assertRaises(ValueError) as cm:
            task.inputs = [123]
            task.__post_init__()
        error_msg = str(cm.exception)
        self.assertIn("string or dict", error_msg)

    def test_named_input_valid_identifiers(self):
        """
        Test various valid identifier names.
        @athena: 978d1cf60aeb
        """
        valid_names = ["input", "input_1", "INPUT", "_private", "camelCase", "snake_case"]
        for name in valid_names:
            with TemporaryDirectory() as tmpdir:
                recipe_path = Path(tmpdir) / "tasktree.yaml"
                recipe_path.write_text(
                    f"""
tasks:
  build:
    inputs:
      - {name}: "src/file.txt"
    cmd: build.sh
"""
                )
                recipe = parse_recipe(recipe_path)
                task = recipe.tasks["build"]
                self.assertIn(name, task._input_map)

    def test_empty_inputs_list(self):
        """
        Test that empty inputs list works correctly.
        @athena: ec0d7adb20e1
        """
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
  build:
    inputs: []
    cmd: build.sh
"""
            )

            recipe = parse_recipe(recipe_path)
            task = recipe.tasks["build"]
            self.assertEqual(len(task.inputs), 0)
            self.assertEqual(len(task._input_map), 0)
            self.assertEqual(len(task._anonymous_inputs), 0)


class TestIndexedInputsOutputs(unittest.TestCase):
    """
    Tests for indexed input/output lists used for positional access.
    """

    def test_indexed_outputs_maintain_yaml_order(self):
        """
        Test that _indexed_outputs maintains YAML declaration order.
        """
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
  build:
    outputs:
      - "first.txt"
      - bundle: "second.js"
      - "third.css"
      - map: "fourth.map"
    cmd: build.sh
"""
            )

            recipe = parse_recipe(recipe_path)
            task = recipe.tasks["build"]

            # Check YAML order is preserved
            self.assertEqual(len(task._indexed_outputs), 4)
            self.assertEqual(task._indexed_outputs[0], "first.txt")
            self.assertEqual(task._indexed_outputs[1], "second.js")
            self.assertEqual(task._indexed_outputs[2], "third.css")
            self.assertEqual(task._indexed_outputs[3], "fourth.map")

    def test_indexed_inputs_maintain_yaml_order(self):
        """
        Test that _indexed_inputs maintains YAML declaration order.
        """
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
  build:
    inputs:
      - src: "src/app.js"
      - "config.json"
      - headers: "include/*.h"
      - "*.txt"
    cmd: build.sh
"""
            )

            recipe = parse_recipe(recipe_path)
            task = recipe.tasks["build"]

            # Check YAML order is preserved
            self.assertEqual(len(task._indexed_inputs), 4)
            self.assertEqual(task._indexed_inputs[0], "src/app.js")
            self.assertEqual(task._indexed_inputs[1], "config.json")
            self.assertEqual(task._indexed_inputs[2], "include/*.h")
            self.assertEqual(task._indexed_inputs[3], "*.txt")

    def test_indexed_outputs_named_only(self):
        """
        Test indexed list with only named outputs.
        """
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
  build:
    outputs:
      - bundle: "dist/app.js"
      - sourcemap: "dist/app.js.map"
    cmd: build.sh
"""
            )

            recipe = parse_recipe(recipe_path)
            task = recipe.tasks["build"]

            self.assertEqual(len(task._indexed_outputs), 2)
            self.assertEqual(task._indexed_outputs[0], "dist/app.js")
            self.assertEqual(task._indexed_outputs[1], "dist/app.js.map")

    def test_indexed_inputs_anonymous_only(self):
        """
        Test indexed list with only anonymous inputs.
        """
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
  build:
    inputs: ["src/*.js", "config.json", "package.json"]
    cmd: build.sh
"""
            )

            recipe = parse_recipe(recipe_path)
            task = recipe.tasks["build"]

            self.assertEqual(len(task._indexed_inputs), 3)
            self.assertEqual(task._indexed_inputs[0], "src/*.js")
            self.assertEqual(task._indexed_inputs[1], "config.json")
            self.assertEqual(task._indexed_inputs[2], "package.json")

    def test_indexed_lists_empty_when_no_inputs_outputs(self):
        """
        Test that indexed lists are empty when no inputs/outputs defined.
        """
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
  build:
    cmd: echo "no inputs or outputs"
"""
            )

            recipe = parse_recipe(recipe_path)
            task = recipe.tasks["build"]

            self.assertEqual(len(task._indexed_inputs), 0)
            self.assertEqual(len(task._indexed_outputs), 0)


if __name__ == "__main__":
    unittest.main()
