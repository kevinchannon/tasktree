"""Filesystem freshness probing for incremental execution.

A :class:`FreshnessProbe` answers a single question: "which files match these
glob patterns, and what are their modification times?" relative to a base
directory.

The point of the abstraction is *where* that question is answered. For tasks
that run on the host, :class:`HostProbe` reads the local filesystem directly.
For tasks that run inside a container, the equivalent query must be evaluated in
the container's filesystem namespace (the runner implementation) so that the
declared input/output paths are resolved exactly as the task itself sees them --
otherwise a runner that remaps paths via volumes could make the host-side view
disagree with reality and cause a stale task to be skipped.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class FreshnessProbe(ABC):
    """
    Resolves glob patterns to matching files and their mtimes against some
    filesystem view (the host, or a container).
    """

    @abstractmethod
    def stat_patterns(self, patterns: list[str]) -> dict[str, dict[str, float]]:
        """
        Resolve each glob pattern against the probe's base directory.

        Args:
            patterns: Glob patterns, each interpreted relative to the base dir.

        Returns:
            A mapping of ``pattern -> {relative_path: mtime}`` containing every
            existing regular file matched by that pattern. ``relative_path`` is
            relative to the base directory (matching the keys used in task
            state). A pattern that matches nothing maps to an empty dict.
        """
        raise NotImplementedError


class HostProbe(FreshnessProbe):
    """
    A :class:`FreshnessProbe` that reads the host filesystem directly.
    """

    def __init__(self, base_dir: Path):
        """
        Args:
            base_dir: Directory that patterns are resolved relative to (typically
                ``project_root / task.working_dir``).
        """
        self._base_dir = base_dir

    def stat_patterns(self, patterns: list[str]) -> dict[str, dict[str, float]]:
        result: dict[str, dict[str, float]] = {}
        for pattern in patterns:
            matches: dict[str, float] = {}
            for match in self._base_dir.glob(pattern):
                if match.is_file():
                    rel_path = str(match.relative_to(self._base_dir))
                    matches[rel_path] = match.stat().st_mtime
            result[pattern] = matches
        return result
