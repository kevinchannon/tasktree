"""Nix integration for Task Tree.

Realises Nix flake devShell environments for tasks using a Nix runner. Nix is
an environment provider, not a sandbox: tasks run on the host with the
devShell's environment merged in.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tasktree.logging import Logger
    from tasktree.parser import NixRunner
    from tasktree.process_runner import ProcessRunner

REQUIRED_EXPERIMENTAL_FEATURES = frozenset({"nix-command", "flakes"})

_ENABLE_FEATURES_HINT = (
    "Enable them by adding this line to ~/.config/nix/nix.conf "
    "(or /etc/nix/nix.conf):\n"
    "  experimental-features = nix-command flakes"
)


class NixError(Exception):
    """
    Raised when Nix operations fail.
    """

    pass


def _exported_variables(print_dev_env_payload: dict) -> dict[str, str]:
    """
    Extract the exported string variables from a 'nix print-dev-env --json'
    payload. Non-exported variables (e.g. shellHook, type 'var') and
    structured values (type 'array') are not part of the child environment.
    """
    variables = print_dev_env_payload.get("variables", {})
    return {
        var_name: spec["value"]
        for var_name, spec in variables.items()
        if spec.get("type") == "exported" and isinstance(spec.get("value"), str)
    }


class NixManager:
    """
    Manages realisation of Nix flake devShell environments.
    """

    def __init__(self, project_root: Path, logger: Logger):
        """
        Initialize Nix manager.

        Args:
            project_root: Root directory of the project (where tasktree.yaml is located)
            logger: Logger instance for debug/trace messages
        """
        self._project_root = project_root
        self._logger = logger

    def realise_env(
        self, runner: NixRunner, process_runner: ProcessRunner
    ) -> dict[str, str]:
        """
        Realise the devShell environment for a Nix runner.

        Runs 'nix print-dev-env --json' for the runner's flake/devshell and
        returns the exported variables as a plain environment dict. The flake
        lock file is never rewritten. shellHook is not yet honoured (planned).

        Args:
        runner: The NixRunner whose devShell to realise
        process_runner: ProcessRunner instance for subprocess execution

        Raises:
        NixError: If nix is unavailable, evaluation fails or emits invalid JSON
        """
        self._check_nix_available()

        installable = f"{runner.flake}#{runner.devshell}"
        cmd = ["nix", "print-dev-env", "--json", "--no-write-lock-file", installable]
        self._logger.debug(
            f"Realising Nix devShell for runner '{runner.name}': {' '.join(cmd)}"
        )
        try:
            result = process_runner.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                cwd=self._project_root,
            )
        except subprocess.CalledProcessError as e:
            raise NixError(
                f"Failed to realise Nix devShell for runner '{runner.name}': "
                f"nix print-dev-env exited with code {e.returncode}\n{e.stderr}"
            ) from e

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            raise NixError(
                f"Failed to realise Nix devShell for runner '{runner.name}': "
                f"nix print-dev-env emitted invalid JSON"
            ) from e

        return _exported_variables(payload)

    @staticmethod
    def _check_nix_available() -> None:
        """
        Check that the nix command is available and that the 'nix-command' and
        'flakes' experimental features are enabled.

        Raises:
        NixError: If nix is not installed or the required features are disabled
        """
        try:
            subprocess.run(
                ["nix", "--version"],
                check=True,
                capture_output=True,
                text=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise NixError(
                "Nix is not available. Please install Nix.\n"
                "Visit https://nixos.org/download/ for installation instructions."
            )

        try:
            result = subprocess.run(
                ["nix", "config", "show", "experimental-features"],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError:
            # 'nix config show' is itself a new-style command, so it fails
            # outright when nix-command is disabled.
            raise NixError(
                "The Nix runner requires the 'nix-command' and 'flakes' "
                f"experimental features, which are not enabled.\n{_ENABLE_FEATURES_HINT}"
            )

        enabled_features = set(result.stdout.split())
        missing_features = sorted(REQUIRED_EXPERIMENTAL_FEATURES - enabled_features)
        if missing_features:
            raise NixError(
                f"The Nix runner requires the {missing_features} experimental "
                f"feature(s), which are not enabled.\n{_ENABLE_FEATURES_HINT}"
            )
