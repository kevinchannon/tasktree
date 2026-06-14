"""Unit tests for the filesystem freshness probe abstraction."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tasktree.freshness import HostProbe


class TestHostProbe(unittest.TestCase):
    """
    Test the host-filesystem freshness probe.
    """

    def test_literal_path_returns_mtime(self):
        """A literal (non-glob) pattern returns the file's mtime."""
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            (base / "out.txt").write_text("hi")

            result = HostProbe(base).stat_patterns(["out.txt"])

            self.assertIn("out.txt", result["out.txt"])
            self.assertEqual(
                result["out.txt"]["out.txt"], (base / "out.txt").stat().st_mtime
            )

    def test_glob_expands_to_relative_paths(self):
        """A glob returns matched files keyed by path relative to the base dir."""
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            (base / "build").mkdir()
            (base / "build" / "a.bin").write_text("a")
            (base / "build" / "b.bin").write_text("b")

            result = HostProbe(base).stat_patterns(["build/*.bin"])

            self.assertEqual(
                set(result["build/*.bin"].keys()),
                {"build/a.bin", "build/b.bin"},
            )

    def test_non_matching_pattern_maps_to_empty(self):
        """A pattern that matches nothing maps to an empty dict (not missing)."""
        with TemporaryDirectory() as tmpdir:
            result = HostProbe(Path(tmpdir)).stat_patterns(["nope/*.txt"])
            self.assertEqual(result, {"nope/*.txt": {}})

    def test_directories_are_excluded(self):
        """Only regular files are reported; directories matched by a glob are skipped."""
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            (base / "sub").mkdir()
            (base / "sub" / "file.txt").write_text("x")

            # The glob "*" matches the directory "sub" too, but it must be excluded.
            result = HostProbe(base).stat_patterns(["*"])

            self.assertNotIn("sub", result["*"])

    def test_each_pattern_keyed_separately(self):
        """Results are grouped per pattern so callers can detect a pattern with no match."""
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            (base / "present.txt").write_text("x")

            result = HostProbe(base).stat_patterns(["present.txt", "absent.txt"])

            self.assertEqual(set(result["present.txt"].keys()), {"present.txt"})
            self.assertEqual(result["absent.txt"], {})

    def test_missing_base_dir_yields_empty_matches(self):
        """A non-existent base directory yields empty matches rather than erroring."""
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "does-not-exist"
            result = HostProbe(base).stat_patterns(["*.txt"])
            self.assertEqual(result, {"*.txt": {}})


if __name__ == "__main__":
    unittest.main()
