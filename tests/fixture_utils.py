"""Utilities for loading test fixtures from the tests/fixtures/ directory.

Fixture directory structure:

    tests/fixtures/<name>/           # Base fixture files (all platforms)
    tests/fixtures/<name>/posix/     # POSIX-specific overrides (optional)
    tests/fixtures/<name>/windows/   # Windows-specific overrides (optional)

Usage:

    from tests.fixture_utils import copy_fixture_files
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        copy_fixture_files("my_fixture", Path(tmpdir))
        # tmpdir now contains all fixture files for the current platform

Platform resolution:
    1. All files (non-recursively) from tests/fixtures/<name>/ are copied.
    2. If tests/fixtures/<name>/posix/ or tests/fixtures/<name>/windows/ exists,
       those files are copied too, overwriting any with the same name.
"""

import sys
import shutil
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def _current_platform() -> str:
    return "windows" if sys.platform == "win32" else "posix"


def copy_fixture_files(name: str, target_dir: Path) -> None:
    """Copy fixture files for <name> to target_dir.

    Copies all non-directory files from tests/fixtures/<name>/ to target_dir,
    then copies platform-specific files from tests/fixtures/<name>/<platform>/,
    overwriting any existing files with the same name.

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

    _copy_files_only(fixture_base, target_dir)

    platform_dir = fixture_base / _current_platform()
    if platform_dir.exists():
        _copy_files_only(platform_dir, target_dir)


def _copy_files_only(src_dir: Path, target_dir: Path) -> None:
    for item in src_dir.iterdir():
        if item.is_file():
            shutil.copy2(item, target_dir / item.name)
