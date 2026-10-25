"""
Behaviour tests for runner/interpreter construction from the merged raw tree
(schema pipeline slice 4 cutover).

Self-contained (only v1.3.2-era symbols) so the whole file can be copied into
the reference worktree for the gate run - see docs/plans/
schema-validation-pipeline.md section 4.
"""

import tempfile
import unittest
from pathlib import Path

from tasktree.parser import parse_recipe


class RunnerCutoverTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def write(self, relative_path: str, content: str) -> Path:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path


class TestImportedRunnerTolerance(RunnerCutoverTestCase):
    def test_broken_unreferenced_imported_runner_is_tolerated(self):
        """
        A non-pinned imported runner never comes into the merged tree, so
        its configuration is never validated. Expected divergence: v1.3.2
        eagerly built every imported runner and raised here.
        """
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: build.yaml\n"
            "    as: build\n"
            "tasks:\n"
            "  hello:\n"
            "    cmd: echo hello\n",
        )
        self.write(
            "build.yaml",
            "runners:\n"
            "  broken:\n"
            "    type: containerised\n"
            "    engine: docker\n"
            "    dockerfile: does/not/exist/Dockerfile\n"
            "tasks:\n"
            "  compile:\n"
            "    cmd: make\n",
        )
        recipe_obj = parse_recipe(recipe)  # Must not raise
        self.assertIn("hello", recipe_obj.tasks)

    def test_broken_root_runner_still_errors_at_parse(self):
        recipe = self.write(
            "tt.yaml",
            "runners:\n"
            "  broken:\n"
            "    type: containerised\n"
            "    engine: docker\n"
            "    dockerfile: does/not/exist/Dockerfile\n"
            "tasks:\n"
            "  hello:\n"
            "    cmd: echo hello\n",
        )
        with self.assertRaises(ValueError) as cm:
            parse_recipe(recipe)
        self.assertIn("Dockerfile not found", str(cm.exception))

    def test_broken_pinned_imported_runner_still_errors_at_parse(self):
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: build.yaml\n"
            "    as: build\n",
        )
        self.write(
            "build.yaml",
            "runners:\n"
            "  broken:\n"
            "    type: containerised\n"
            "    engine: docker\n"
            "    dockerfile: does/not/exist/Dockerfile\n"
            "tasks:\n"
            "  compile:\n"
            "    cmd: make\n"
            "    runner: broken\n"
            "    pin_runner: true\n",
        )
        with self.assertRaises(ValueError) as cm:
            parse_recipe(recipe)
        self.assertIn("Dockerfile not found", str(cm.exception))


class TestImportedRunnerParity(RunnerCutoverTestCase):
    def test_pinned_imported_runner_is_built_and_namespaced(self):
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: build.yaml\n"
            "    as: build\n",
        )
        self.write(
            "build.yaml",
            "runners:\n"
            "  special:\n"
            "    interpreter: bash\n"
            "tasks:\n"
            "  compile:\n"
            "    cmd: make\n"
            "    runner: special\n"
            "    pin_runner: true\n",
        )
        recipe_obj = parse_recipe(recipe)
        self.assertIn("build.special", recipe_obj.runners)
        self.assertEqual(recipe_obj.tasks["build.compile"].runner, "build.special")

    def test_run_in_blanket_with_pinned_exception(self):
        recipe = self.write(
            "tt.yaml",
            "runners:\n"
            "  docker_like:\n"
            "    interpreter: bash\n"
            "imports:\n"
            "  - file: build.yaml\n"
            "    as: build\n"
            "    run_in: docker_like\n",
        )
        self.write(
            "build.yaml",
            "runners:\n"
            "  special:\n"
            "    interpreter: bash\n"
            "tasks:\n"
            "  pinned:\n"
            "    cmd: make\n"
            "    runner: special\n"
            "    pin_runner: true\n"
            "  floating:\n"
            "    cmd: make\n",
        )
        recipe_obj = parse_recipe(recipe)
        self.assertEqual(recipe_obj.tasks["build.pinned"].runner, "build.special")
        self.assertEqual(recipe_obj.tasks["build.floating"].runner, "docker_like")
        self.assertIn("build.special", recipe_obj.runners)
        self.assertNotIn("build.docker_like", recipe_obj.runners)

    def test_imported_runner_var_refs_are_namespaced(self):
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: build.yaml\n"
            "    as: build\n",
        )
        self.write("docker/Dockerfile", "FROM alpine\n")
        self.write(
            "build.yaml",
            "variables:\n"
            "  cache: /tmp/cache\n"
            "runners:\n"
            "  special:\n"
            "    type: containerised\n"
            "    engine: docker\n"
            "    dockerfile: docker/Dockerfile\n"
            "    volumes:\n"
            "      - '{{ var.cache }}:/cache'\n"
            "tasks:\n"
            "  compile:\n"
            "    cmd: make\n"
            "    runner: special\n"
            "    pin_runner: true\n",
        )
        recipe_obj = parse_recipe(recipe)
        runner = recipe_obj.runners["build.special"]
        # Variables are substituted during parse_recipe's eager evaluation;
        # the namespaced reference must have resolved to the imported value
        self.assertEqual(runner.volumes, ["/tmp/cache:/cache"])


if __name__ == "__main__":
    unittest.main()
