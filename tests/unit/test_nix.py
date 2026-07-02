"""
Tests for the Nix integration module.
"""

import subprocess
import unittest
from unittest.mock import MagicMock, patch

from tasktree.nix import NixError, NixManager


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
    def test_config_show_failure_raises_with_config_hint(self, mock_run):
        # 'nix config show' fails outright when nix-command is disabled
        mock_run.side_effect = [
            _completed("nix (Nix) 2.18.1"),
            subprocess.CalledProcessError(1, ["nix", "config", "show"]),
        ]

        with self.assertRaises(NixError) as ctx:
            NixManager._check_nix_available()
        self.assertIn("experimental features", str(ctx.exception))
        self.assertIn("experimental-features = nix-command flakes", str(ctx.exception))

    @patch("tasktree.nix.subprocess.run")
    def test_missing_flakes_feature_raises(self, mock_run):
        mock_run.side_effect = [
            _completed("nix (Nix) 2.18.1"),
            _completed("nix-command"),
        ]

        with self.assertRaises(NixError) as ctx:
            NixManager._check_nix_available()
        self.assertIn("'flakes'", str(ctx.exception))
        self.assertIn("experimental-features = nix-command flakes", str(ctx.exception))

    @patch("tasktree.nix.subprocess.run")
    def test_both_features_enabled_passes(self, mock_run):
        mock_run.side_effect = [
            _completed("nix (Nix) 2.18.1"),
            _completed("nix-command flakes"),
        ]

        NixManager._check_nix_available()  # Must not raise

    @patch("tasktree.nix.subprocess.run")
    def test_extra_features_enabled_passes(self, mock_run):
        mock_run.side_effect = [
            _completed("nix (Nix) 2.18.1"),
            _completed("ca-derivations flakes nix-command recursive-nix"),
        ]

        NixManager._check_nix_available()  # Must not raise


if __name__ == "__main__":
    unittest.main()
