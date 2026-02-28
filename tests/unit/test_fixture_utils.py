import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.fixture_utils import copy_fixture_files, FIXTURES


class TestCopyFixtureFiles(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.target = Path(self._tmpdir) / "target"
        self.fixtures_root = Path(self._tmpdir) / "fixtures"

    def tearDown(self):
        shutil.rmtree(self._tmpdir)

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    def test_raises_file_not_found_when_fixture_missing(self):
        with patch("tests.fixture_utils.FIXTURES", self.fixtures_root):
            with self.assertRaises(FileNotFoundError):
                copy_fixture_files("nonexistent", self.target)

    def test_error_message_includes_fixture_name(self):
        with patch("tests.fixture_utils.FIXTURES", self.fixtures_root):
            with self.assertRaises(FileNotFoundError) as ctx:
                copy_fixture_files("my_fixture", self.target)
        self.assertIn("my_fixture", str(ctx.exception))

    # ------------------------------------------------------------------
    # Base fixture copying
    # ------------------------------------------------------------------

    def test_copies_base_files_to_target(self):
        fixture_dir = self.fixtures_root / "my_fixture"
        fixture_dir.mkdir(parents=True)
        (fixture_dir / "recipe.yaml").write_text("tasks: {}")

        with patch("tests.fixture_utils.FIXTURES", self.fixtures_root):
            copy_fixture_files("my_fixture", self.target)

        self.assertTrue((self.target / "recipe.yaml").exists())

    def test_base_file_content_is_preserved(self):
        fixture_dir = self.fixtures_root / "my_fixture"
        fixture_dir.mkdir(parents=True)
        (fixture_dir / "recipe.yaml").write_text("tasks: {}\n")

        with patch("tests.fixture_utils.FIXTURES", self.fixtures_root):
            copy_fixture_files("my_fixture", self.target)

        self.assertEqual("tasks: {}\n", (self.target / "recipe.yaml").read_text())

    def test_multiple_base_files_all_copied(self):
        fixture_dir = self.fixtures_root / "my_fixture"
        fixture_dir.mkdir(parents=True)
        (fixture_dir / "a.yaml").write_text("a")
        (fixture_dir / "b.yaml").write_text("b")

        with patch("tests.fixture_utils.FIXTURES", self.fixtures_root):
            copy_fixture_files("my_fixture", self.target)

        self.assertTrue((self.target / "a.yaml").exists())
        self.assertTrue((self.target / "b.yaml").exists())

    def test_subdirectories_are_not_copied(self):
        fixture_dir = self.fixtures_root / "my_fixture"
        subdir = fixture_dir / "some_subdir"
        subdir.mkdir(parents=True)
        (subdir / "nested.yaml").write_text("nested")

        with patch("tests.fixture_utils.FIXTURES", self.fixtures_root):
            copy_fixture_files("my_fixture", self.target)

        self.assertFalse((self.target / "some_subdir").exists())
        self.assertFalse((self.target / "nested.yaml").exists())

    # ------------------------------------------------------------------
    # Target directory creation
    # ------------------------------------------------------------------

    def test_creates_target_directory_if_missing(self):
        fixture_dir = self.fixtures_root / "my_fixture"
        fixture_dir.mkdir(parents=True)
        (fixture_dir / "recipe.yaml").write_text("tasks: {}")

        non_existent = self.target / "deep" / "nested"
        with patch("tests.fixture_utils.FIXTURES", self.fixtures_root):
            copy_fixture_files("my_fixture", non_existent)

        self.assertTrue(non_existent.exists())

    # ------------------------------------------------------------------
    # Platform-specific overrides
    # ------------------------------------------------------------------

    def test_posix_files_override_base_files(self):
        fixture_dir = self.fixtures_root / "my_fixture"
        posix_dir = fixture_dir / "posix"
        posix_dir.mkdir(parents=True)
        (fixture_dir / "recipe.yaml").write_text("base content")
        (posix_dir / "recipe.yaml").write_text("posix content")

        with patch("tests.fixture_utils.FIXTURES", self.fixtures_root):
            with patch("tests.fixture_utils._current_platform", return_value="posix"):
                copy_fixture_files("my_fixture", self.target)

        self.assertEqual("posix content", (self.target / "recipe.yaml").read_text())

    def test_windows_files_override_base_files(self):
        fixture_dir = self.fixtures_root / "my_fixture"
        windows_dir = fixture_dir / "windows"
        windows_dir.mkdir(parents=True)
        (fixture_dir / "recipe.yaml").write_text("base content")
        (windows_dir / "recipe.yaml").write_text("windows content")

        with patch("tests.fixture_utils.FIXTURES", self.fixtures_root):
            with patch("tests.fixture_utils._current_platform", return_value="windows"):
                copy_fixture_files("my_fixture", self.target)

        self.assertEqual("windows content", (self.target / "recipe.yaml").read_text())

    def test_platform_specific_files_added_without_conflict(self):
        fixture_dir = self.fixtures_root / "my_fixture"
        posix_dir = fixture_dir / "posix"
        posix_dir.mkdir(parents=True)
        (fixture_dir / "shared.yaml").write_text("shared")
        (posix_dir / "platform_only.yaml").write_text("posix only")

        with patch("tests.fixture_utils.FIXTURES", self.fixtures_root):
            with patch("tests.fixture_utils._current_platform", return_value="posix"):
                copy_fixture_files("my_fixture", self.target)

        self.assertTrue((self.target / "shared.yaml").exists())
        self.assertTrue((self.target / "platform_only.yaml").exists())

    def test_no_platform_override_when_platform_dir_absent(self):
        fixture_dir = self.fixtures_root / "my_fixture"
        fixture_dir.mkdir(parents=True)
        (fixture_dir / "recipe.yaml").write_text("base content")

        with patch("tests.fixture_utils.FIXTURES", self.fixtures_root):
            with patch("tests.fixture_utils._current_platform", return_value="posix"):
                copy_fixture_files("my_fixture", self.target)

        self.assertEqual("base content", (self.target / "recipe.yaml").read_text())

    def test_posix_dir_ignored_on_windows_platform(self):
        fixture_dir = self.fixtures_root / "my_fixture"
        posix_dir = fixture_dir / "posix"
        posix_dir.mkdir(parents=True)
        (fixture_dir / "recipe.yaml").write_text("base content")
        (posix_dir / "recipe.yaml").write_text("posix content")

        with patch("tests.fixture_utils.FIXTURES", self.fixtures_root):
            with patch("tests.fixture_utils._current_platform", return_value="windows"):
                copy_fixture_files("my_fixture", self.target)

        self.assertEqual("base content", (self.target / "recipe.yaml").read_text())

    def test_windows_dir_ignored_on_posix_platform(self):
        fixture_dir = self.fixtures_root / "my_fixture"
        windows_dir = fixture_dir / "windows"
        windows_dir.mkdir(parents=True)
        (fixture_dir / "recipe.yaml").write_text("base content")
        (windows_dir / "recipe.yaml").write_text("windows content")

        with patch("tests.fixture_utils.FIXTURES", self.fixtures_root):
            with patch("tests.fixture_utils._current_platform", return_value="posix"):
                copy_fixture_files("my_fixture", self.target)

        self.assertEqual("base content", (self.target / "recipe.yaml").read_text())

    # ------------------------------------------------------------------
    # FIXTURES constant
    # ------------------------------------------------------------------

    def test_fixtures_constant_points_to_tests_fixtures_directory(self):
        self.assertTrue(FIXTURES.name == "fixtures")
        self.assertTrue(FIXTURES.parent.name == "tests")


if __name__ == "__main__":
    unittest.main()
