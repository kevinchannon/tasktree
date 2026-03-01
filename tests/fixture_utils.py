"""Utilities for loading test fixtures from the tests/fixtures/ directory.

Fixture directory structure:

    tests/fixtures/<name>/           # Base fixture files (all platforms)
    tests/fixtures/<name>/posix/     # POSIX-specific overrides (optional)
    tests/fixtures/<name>/windows/   # Windows-specific overrides (optional)

The base directory is copied recursively to the target. Any subdirectory
named "posix" or "windows" at the root of the fixture is treated as a
platform override directory and is NOT copied as part of the base tree.
After copying the base tree, the platform-specific directory (if present)
is merged into the target, overwriting any files with matching names.

Usage:

    from fixture_utils import copy_fixture_files
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        copy_fixture_files("my_fixture", Path(tmpdir))
        # tmpdir now contains all fixture files for the current platform
"""

import sys
import shutil
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"

_PLATFORM_DIRS = frozenset({"posix", "windows"})


def _current_platform() -> str:
    return "windows" if sys.platform == "win32" else "posix"


def copy_fixture_files(name: str, target_dir: Path) -> None:
    """Copy fixture files for <name> to target_dir.

    Recursively copies everything from tests/fixtures/<name>/ to target_dir,
    skipping the platform override subdirectories ("posix" and "windows").
    Then recursively copies files from tests/fixtures/<name>/<platform>/
    into target_dir, overwriting any existing files with the same relative path.

    Args:
        name: The fixture directory name under tests/fixtures/
        target_dir: The destination directory to copy files into

    Raises:
        FileNotFoundError: If the fixture directory does not exist
    """
    fixture_base = FIXTURES / name
    if not fixture_base.exists():
        raise FileNotFoundError(
            f"No fixture directory '{name}' found. Expected: {fixture_base}"
        )

    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    shutil.copytree(
        fixture_base,
        target_dir,
        ignore=shutil.ignore_patterns(*_PLATFORM_DIRS),
        dirs_exist_ok=True,
    )

    platform_dir = fixture_base / _current_platform()
    if platform_dir.exists():
        shutil.copytree(platform_dir, target_dir, dirs_exist_ok=True)
