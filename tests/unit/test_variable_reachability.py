"""
Behaviour tests for lazy variable evaluation after the walker cutover
(schema pipeline slice 5).

Self-contained (only v1.3.2-era symbols) so the whole file can be copied
into the reference worktree for the gate run - see docs/plans/
schema-validation-pipeline.md section 4.
"""

import tempfile
import unittest
from pathlib import Path

from tasktree.parser import parse_recipe


class VariableReachabilityTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def write_recipe(self, content: str) -> Path:
        path = self.root / "tasktree.yaml"
        path.write_text(content, encoding="utf-8")
        return path

    def marker(self, name: str) -> Path:
        return self.root / name


class TestLazyEvaluationParity(VariableReachabilityTestCase):
    def test_unreachable_tasks_variables_are_not_evaluated(self):
        recipe_path = self.write_recipe(
            "variables:\n"
            f"  used: {{ eval: 'touch {self.root}/marker_used && echo u' }}\n"
            f"  unused: {{ eval: 'touch {self.root}/marker_unused && echo x' }}\n"
            "tasks:\n"
            "  a:\n"
            "    cmd: echo {{ var.used }}\n"
            "  b:\n"
            "    cmd: echo {{ var.unused }}\n"
        )
        parse_recipe(recipe_path, root_task="a")
        self.assertTrue(self.marker("marker_used").exists())
        self.assertFalse(self.marker("marker_unused").exists())


class TestWalkerCoverageDivergence(VariableReachabilityTestCase):
    def test_var_in_inline_host_runner_is_evaluated_lazily(self):
        """
        Divergence from v1.3.2: reference discovery walks every string in a
        reachable task's definition. v1.3.2 enumerated fields and only
        looked inside Docker runner definitions, so a variable referenced
        by an inline host runner's working_dir was never evaluated under
        lazy (root-task) parsing.
        """
        recipe_path = self.write_recipe(
            "variables:\n"
            f"  wd: {{ eval: 'touch {self.root}/marker_wd && echo {self.root}' }}\n"
            "tasks:\n"
            "  a:\n"
            "    cmd: echo hi\n"
            "    runner:\n"
            "      working_dir: '{{ var.wd }}'\n"
        )
        recipe = parse_recipe(recipe_path, root_task="a")
        self.assertTrue(self.marker("marker_wd").exists())
        self.assertEqual(
            recipe.runners["a.__inline__"].working_dir, str(self.root)
        )


if __name__ == "__main__":
    unittest.main()
