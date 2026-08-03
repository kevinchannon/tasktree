"""
Tests for the merged-tree schema: the file schema rewritten to describe a
recipe after imports have been merged away.
"""

import json
import unittest
from pathlib import Path

import jsonschema
import yaml

from tasktree.raw_merge import CircularImportError, merge_recipe_files
from tasktree.recipe_schema import merged_tree_schema

REPO_ROOT = Path(__file__).parents[2]
SCHEMA_PATH = REPO_ROOT / "schema" / "tasktree-schema.json"
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures"


def _file_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def _validate_merged(tree: dict) -> None:
    jsonschema.validate(instance=tree, schema=merged_tree_schema(_file_schema()))


def _validate_file(recipe: dict) -> None:
    jsonschema.validate(instance=recipe, schema=_file_schema())


class TestNamespacedNames(unittest.TestCase):
    """
    Imported definitions arrive namespaced ('build.compile'), so the merged
    tree must accept dotted names everywhere the file schema forbids them.
    """

    def test_dotted_task_name_valid(self):
        _validate_merged({"tasks": {"build.compile": {"cmd": "make"}}})

    def test_deeply_dotted_task_name_valid(self):
        _validate_merged({"tasks": {"a.b.c.compile": {"cmd": "make"}}})

    def test_dotted_variable_name_valid(self):
        _validate_merged({"variables": {"build.root": "/src"}})

    def test_dotted_runner_name_valid(self):
        _validate_merged({"runners": {"build.docker": {"interpreter": "bash"}}})

    def test_dotted_interpreter_name_valid(self):
        _validate_merged({"interpreters": {"build.py": {"cmd": "python3"}}})

    def test_undotted_names_still_valid(self):
        _validate_merged(
            {
                "tasks": {"compile": {"cmd": "make"}},
                "variables": {"root": "/src"},
                "runners": {"docker": {"interpreter": "bash"}},
                "interpreters": {"py": {"cmd": "python3"}},
            }
        )

    def test_default_key_still_reserved_in_runners(self):
        """'default' names the default runner, so it is not a runner name."""
        with self.assertRaises(jsonschema.ValidationError):
            _validate_merged({"runners": {"default": {"interpreter": "bash"}}})

    def test_default_declaration_survives(self):
        _validate_merged(
            {"runners": {"default": "build.docker", "build.docker": {"interpreter": "bash"}}}
        )

    def test_file_schema_still_rejects_dotted_names(self):
        """The transform must not mutate the file schema it is given."""
        with self.assertRaises(jsonschema.ValidationError):
            _validate_file({"tasks": {"build.compile": {"cmd": "make"}}})


class TestImportsAreConsumed(unittest.TestCase):
    """
    The merge consumes 'imports'; one surviving in the tree means the merge
    left work undone, so the merged-tree schema rejects the key outright.
    """

    def test_imports_key_invalid(self):
        with self.assertRaises(jsonschema.ValidationError):
            _validate_merged(
                {
                    "imports": [{"file": "build.tasks", "as": "build"}],
                    "tasks": {"compile": {"cmd": "make"}},
                }
            )

    def test_file_schema_still_accepts_imports(self):
        _validate_file(
            {
                "imports": [{"file": "build.tasks", "as": "build"}],
                "tasks": {"compile": {"cmd": "make"}},
            }
        )

    def test_imports_only_tree_invalid(self):
        """A merged tree can never consist solely of imports."""
        with self.assertRaises(jsonschema.ValidationError):
            _validate_merged({"imports": [{"file": "build.tasks", "as": "build"}]})


class TestRealMergedTrees(unittest.TestCase):
    """
    The generated schema checked against what the merge actually produces.

    Every fixture project that imports something is merged and validated, so
    a namespacing rule the transform doesn't cover shows up here rather than
    when validation goes live at parse time.
    """

    def test_merged_fixture_trees_validate(self):
        validator = jsonschema.Draft7Validator(merged_tree_schema(_file_schema()))

        checked = 0
        for recipe_path in _importing_fixture_recipes():
            try:
                merged = merge_recipe_files(recipe_path).data
            except (ValueError, CircularImportError, FileNotFoundError):
                continue  # fixtures for tt's own merge-error handling
            error = jsonschema.exceptions.best_match(validator.iter_errors(merged))
            self.assertIsNone(
                error,
                f"{recipe_path} merged to a tree the schema rejects: {error}",
            )
            checked += 1

        self.assertGreater(checked, 20, "fixture discovery found almost nothing")


def _importing_fixture_recipes() -> list[Path]:
    """
    Root recipes of fixture projects that use imports and whose files are all
    valid on their own -- the merge's job is to preserve that validity, not to
    rescue a broken file.
    """
    file_validator = jsonschema.Draft7Validator(_file_schema())
    roots = []
    for path in sorted(FIXTURE_ROOT.rglob("*")):
        if path.name not in {"tasktree.yaml", "tt.yaml"} or not path.is_file():
            continue
        recipes = _project_recipes(path.parent)
        if recipes is None or not any("imports" in r for r in recipes):
            continue
        if all(not list(file_validator.iter_errors(r)) for r in recipes):
            roots.append(path)
    return roots


def _project_recipes(project_dir: Path) -> list[dict] | None:
    """Every parseable recipe in a fixture project, or None if any is malformed."""
    recipes = []
    for path in sorted(project_dir.rglob("*")):
        if path.suffix not in {".yaml", ".yml", ".tasks"} or not path.is_file():
            continue
        try:
            data = yaml.safe_load(path.read_text())
        except yaml.YAMLError:
            return None
        if isinstance(data, dict):
            recipes.append(data)
    return recipes


class TestTransformCoverage(unittest.TestCase):
    """
    Guards against the file schema growing a name-keyed section the transform
    doesn't know about, which would silently reject valid imported names.
    """

    def test_every_name_pattern_is_rewritten(self):
        merged_patterns = _pattern_property_keys(merged_tree_schema(_file_schema()))
        self.assertEqual(set(merged_patterns), _EXPECTED_MERGED_PATTERNS)
        self.assertEqual(len(merged_patterns), _NAME_KEYED_SECTIONS)

    def test_file_schema_pattern_count_unchanged(self):
        """If this fails, the schema grew or lost a name-keyed section."""
        self.assertEqual(len(_pattern_property_keys(_file_schema())), _NAME_KEYED_SECTIONS)

    def test_unknown_name_pattern_rejected(self):
        schema = _file_schema()
        schema["properties"]["gadgets"] = {"patternProperties": {"^g_.+$": {}}}
        with self.assertRaises(ValueError) as cm:
            merged_tree_schema(schema)
        self.assertIn("^g_.+$", str(cm.exception))


_EXPECTED_MERGED_PATTERNS = {
    r"^[^.]+(\.[^.]+)*$",
    r"^(?!default$)[^.]+(\.[^.]+)*$",
}

# tasks, variables, runners, interpreters
_NAME_KEYED_SECTIONS = 4


def _pattern_property_keys(node, found=None) -> list[str]:
    """Every patternProperties key anywhere in a schema, one entry per section."""
    found = [] if found is None else found
    if isinstance(node, dict):
        found.extend(node.get("patternProperties", {}))
        for value in node.values():
            _pattern_property_keys(value, found)
    elif isinstance(node, list):
        for item in node:
            _pattern_property_keys(item, found)
    return found


if __name__ == "__main__":
    unittest.main()
