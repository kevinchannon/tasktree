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
from typing import Callable


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


class RunnerProbe(FreshnessProbe):
    """
    A :class:`FreshnessProbe` that resolves patterns inside a container.

    It runs a small portable shell snippet in the runner (via an injected
    callable) that, for each pattern, expands the glob relative to the base
    directory and prints the matching regular files with their mtimes. This means
    paths are resolved in the container's filesystem view -- correct even when a
    runner remaps the working directory to a non-project-root volume.

    Limitations (by design):
    - Uses the container shell's globbing, which does NOT expand ``**``
      recursively (``sh`` treats it as a single ``*``).
    - Mtimes come from ``stat -c %Y`` (whole seconds), so a file rewritten within
      the same second as the previous capture may not be detected. This is
      internally consistent: a task's state never mixes host and runner mtimes
      because the runner is part of the task's cache key.
    """

    # Reads "$1" as the base dir, then treats the remaining args as glob patterns.
    # Unmatched globs stay literal in sh, and the "-f" test then skips them, so a
    # pattern with no matches simply produces no output.
    _SCRIPT = (
        'cd "$1" 2>/dev/null || exit 0\n'
        "shift\n"
        'for pat in "$@"; do\n'
        "  for f in $pat; do\n"
        '    [ -f "$f" ] && printf \'%s\\t%s\\t%s\\n\' "$pat" "$f" "$(stat -c %Y "$f")"\n'
        "  done\n"
        "done\n"
    )

    def __init__(self, base_dir: str, run: Callable[[list[str]], str]):
        """
        Args:
            base_dir: Container path that patterns are resolved relative to (the
                task's container working directory).
            run: Callable that executes an argv inside the container and returns
                its stdout.
        """
        self._base_dir = base_dir
        self._run = run

    def stat_patterns(self, patterns: list[str]) -> dict[str, dict[str, float]]:
        result: dict[str, dict[str, float]] = {pattern: {} for pattern in patterns}
        if not patterns:
            return result

        argv = ["sh", "-c", self._SCRIPT, "sh", self._base_dir, *patterns]
        output = self._run(argv)

        for line in output.splitlines():
            parts = line.split("\t")
            if len(parts) != 3:
                continue
            pattern, rel_path, mtime = parts
            if pattern not in result:
                continue
            try:
                result[pattern][rel_path] = float(mtime)
            except ValueError:
                continue

        return result
