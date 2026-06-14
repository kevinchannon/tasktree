"""Unit tests for the filesystem freshness probe abstraction."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tasktree.freshness import HostProbe, RunnerProbe


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


class TestRunnerProbe(unittest.TestCase):
    """
    Test the container freshness probe (parsing + invocation), with a stub runner
    standing in for the actual container execution.
    """

    def test_passes_base_dir_and_patterns_to_runner(self):
        """The probe invokes the runner with the base dir and each pattern as args."""
        captured = {}

        def fake_run(argv):
            captured["argv"] = argv
            return ""

        RunnerProbe("/work", fake_run).stat_patterns(["a.txt", "build/*.bin"])

        argv = captured["argv"]
        self.assertEqual(argv[0], "sh")
        self.assertEqual(argv[1], "-c")
        # After the script and the "sh" argv[0] sentinel come the base dir + patterns.
        self.assertEqual(argv[3:], ["sh", "/work", "a.txt", "build/*.bin"])

    def test_parses_output_into_per_pattern_mtimes(self):
        """Tab-separated 'pattern\\trelpath\\tmtime' lines parse into the result map."""
        def fake_run(argv):
            return (
                "build/*.bin\tbuild/a.bin\t1000\n"
                "build/*.bin\tbuild/b.bin\t1001\n"
                "a.txt\ta.txt\t1002\n"
            )

        result = RunnerProbe("/work", fake_run).stat_patterns(
            ["a.txt", "build/*.bin", "absent/*"]
        )

        self.assertEqual(result["a.txt"], {"a.txt": 1002.0})
        self.assertEqual(
            result["build/*.bin"], {"build/a.bin": 1000.0, "build/b.bin": 1001.0}
        )
        # A pattern with no output line maps to an empty dict (not missing).
        self.assertEqual(result["absent/*"], {})

    def test_empty_patterns_short_circuits(self):
        """No patterns means no container call and an empty result."""
        called = False

        def fake_run(argv):
            nonlocal called
            called = True
            return ""

        result = RunnerProbe("/work", fake_run).stat_patterns([])

        self.assertEqual(result, {})
        self.assertFalse(called, "runner should not be invoked for empty patterns")

    def test_ignores_malformed_lines(self):
        """Lines that are not 3 tab-separated fields are skipped."""
        def fake_run(argv):
            return "garbage line\na.txt\ta.txt\t1002\n\n"

        result = RunnerProbe("/work", fake_run).stat_patterns(["a.txt"])

        self.assertEqual(result["a.txt"], {"a.txt": 1002.0})


if __name__ == "__main__":
    unittest.main()
