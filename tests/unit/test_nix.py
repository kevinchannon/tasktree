"""
Tests for the Nix integration module.
"""

import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tasktree.nix import NixError, NixManager
from tasktree.parser import NixRunner


def _completed(stdout: str = "") -> MagicMock:
    result = MagicMock()
    result.stdout = stdout
    return result


class TestCheckNixAvailable(unittest.TestCase):
    """
    Tests for NixManager._check_nix_available.
    """

    @patch("tasktree.nix.subprocess.run")
    def test_nix_not_installed_raises(self, mock_run):
        mock_run.side_effect = FileNotFoundError()

        with self.assertRaises(NixError) as ctx:
            NixManager._check_nix_available()
        self.assertIn("Nix is not available", str(ctx.exception))
        self.assertIn("https://nixos.org/download", str(ctx.exception))

    @patch("tasktree.nix.subprocess.run")
    def test_nix_version_failure_raises(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(1, ["nix", "--version"])

        with self.assertRaises(NixError) as ctx:
            NixManager._check_nix_available()
        self.assertIn("Nix is not available", str(ctx.exception))

    @patch("tasktree.nix.subprocess.run")
    def test_nix_command_disabled_raises_with_config_hint(self, mock_run):
        # 'nix eval' fails outright when nix-command is disabled
        mock_run.side_effect = [
            _completed("nix (Nix) 2.18.1"),
            subprocess.CalledProcessError(1, ["nix", "eval"]),
        ]

        with self.assertRaises(NixError) as ctx:
            NixManager._check_nix_available()
        self.assertIn("'nix-command'", str(ctx.exception))
        self.assertIn("experimental-features = nix-command flakes", str(ctx.exception))

    @patch("tasktree.nix.subprocess.run")
    def test_flakes_disabled_raises(self, mock_run):
        # builtins.getFlake only exists when the flakes feature is usable
        mock_run.side_effect = [
            _completed("nix (Nix) 2.18.1"),
            _completed("false\n"),
        ]

        with self.assertRaises(NixError) as ctx:
            NixManager._check_nix_available()
        self.assertIn("'flakes'", str(ctx.exception))
        self.assertIn("experimental-features = nix-command flakes", str(ctx.exception))

    @patch("tasktree.nix.subprocess.run")
    def test_flakes_usable_passes(self, mock_run):
        mock_run.side_effect = [
            _completed("nix (Nix) 2.18.1"),
            _completed("true\n"),
        ]

        NixManager._check_nix_available()  # Must not raise


class TestRealiseEnv(unittest.TestCase):
    """
    Tests for NixManager.realise_env (no caching, no shellHook yet).
    """

    PAYLOAD = {
        "variables": {
            "PATH": {"type": "exported", "value": "/nix/store/abc/bin:/usr/bin"},
            "CARGO_HOME": {"type": "exported", "value": "/home/user/.cargo"},
            "shellHook": {"type": "var", "value": "echo hi"},
            "buildInputs": {"type": "array", "value": ["/nix/store/abc"]},
        },
        "bashFunctions": {},
    }

    def setUp(self):
        self.manager = NixManager(Path("/project"), MagicMock())
        self.runner = NixRunner(name="nix", flake=".", devshell="ci")
        self.process_runner = MagicMock()
        self.process_runner.run.return_value = _completed(json.dumps(self.PAYLOAD))

        check_patch = patch.object(NixManager, "_check_nix_available")
        self.mock_check = check_patch.start()
        self.addCleanup(check_patch.stop)

    def test_returns_only_exported_string_variables(self):
        env = self.manager.realise_env(self.runner, self.process_runner)

        self.assertEqual(
            env,
            {
                "PATH": "/nix/store/abc/bin:/usr/bin",
                "CARGO_HOME": "/home/user/.cargo",
            },
        )

    def test_runs_print_dev_env_with_expected_arguments(self):
        self.manager.realise_env(self.runner, self.process_runner)

        args, kwargs = self.process_runner.run.call_args
        self.assertEqual(
            args[0],
            ["nix", "print-dev-env", "--json", "--no-write-lock-file", ".#ci"],
        )
        self.assertEqual(kwargs["cwd"], Path("/project"))

    def test_checks_nix_availability_first(self):
        self.mock_check.side_effect = NixError("nix missing")

        with self.assertRaises(NixError):
            self.manager.realise_env(self.runner, self.process_runner)
        self.process_runner.run.assert_not_called()

    def test_print_dev_env_failure_raises(self):
        self.process_runner.run.side_effect = subprocess.CalledProcessError(
            1, ["nix"], stderr="error: flake 'path:.' does not provide attribute"
        )

        with self.assertRaises(NixError) as ctx:
            self.manager.realise_env(self.runner, self.process_runner)
        self.assertIn("runner 'nix'", str(ctx.exception))
        self.assertIn("does not provide attribute", str(ctx.exception))

    def test_invalid_json_raises(self):
        self.process_runner.run.return_value = _completed("not json {")

        with self.assertRaises(NixError) as ctx:
            self.manager.realise_env(self.runner, self.process_runner)
        self.assertIn("invalid JSON", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
