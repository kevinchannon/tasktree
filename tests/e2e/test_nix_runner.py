"""
E2E tests for the Nix runner: run a task inside a real fixture flake's
devShell and assert the devShell environment is visible to the task.

Requires Nix with flakes usable; skipped otherwise (CI installs Nix on the
Linux and macOS legs, so the skip condition is exercised there).
"""

import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from helpers.nix import is_nix_available

from . import run_tasktree_cli

FIXTURE_FLAKE_DIR = Path(__file__).parent / "fixtures" / "nix_flake"


@unittest.skipUnless(is_nix_available(), "Nix with flakes not available")
class TestNixRunnerE2E(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.project = Path(tmp.name)
        shutil.copytree(FIXTURE_FLAKE_DIR, self.project / "flake")
        (self.project / "tasktree.yaml").write_text("""
runners:
  nix:
    type: nix
    flake: path:./flake

tasks:
  probe:
    runner: nix
    cmd: |
      echo "$TT_NIX_FIXTURE_VAR" > result.txt
      command -v hello >> result.txt
      echo "$HOST_CANARY" >> result.txt
""")

    def test_task_runs_in_devshell(self):
        result = run_tasktree_cli(
            ["probe"],
            cwd=self.project,
            env={"HOST_CANARY": "host-env-inherited"},
            timeout=300,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        fixture_var, hello_path, host_canary = (
            (self.project / "result.txt").read_text().splitlines()
        )
        # devShell env vars are visible to the task
        self.assertEqual(fixture_var, "from-the-flake")
        # devShell-provided tools are on PATH, from the nix store
        self.assertIn("/nix/store/", hello_path)
        self.assertTrue(hello_path.endswith("/hello"))
        # host environment is inherited (non-isolation is by design)
        self.assertEqual(host_canary, "host-env-inherited")

    def test_flake_lock_is_never_rewritten(self):
        lock_path = self.project / "flake" / "flake.lock"
        lock_before = lock_path.read_bytes()

        result = run_tasktree_cli(["probe"], cwd=self.project, timeout=300)

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(lock_path.read_bytes(), lock_before)


if __name__ == "__main__":
    unittest.main()
