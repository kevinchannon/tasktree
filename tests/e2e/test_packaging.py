"""E2E test for what the built wheel actually contains."""

import shutil
import subprocess
import unittest
import tarfile
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).parents[2]
PACKAGED_SCHEMA = "tasktree/schema/tasktree-schema.json"


@unittest.skipIf(shutil.which("uv") is None, "wheel build needs the uv CLI")
class TestWheelContents(unittest.TestCase):
    """
    The recipe schema is authored at the repo root, outside the package, and
    force-included into the wheel (pyproject.toml). Since tasktree reads it at
    runtime, an installed tasktree without it cannot validate anything -- and
    nothing in a source checkout would notice, because there the loader falls
    back to the authored copy.
    """

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = TemporaryDirectory()
        result = subprocess.run(
            ["uv", "build", "--wheel", "--out-dir", cls._tmpdir.name, str(REPO_ROOT)],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            cls._tmpdir.cleanup()
            raise RuntimeError(f"wheel build failed: {result.stderr}")
        cls.wheel = next(Path(cls._tmpdir.name).glob("*.whl"))

    @classmethod
    def tearDownClass(cls):
        cls._tmpdir.cleanup()

    def test_wheel_carries_the_recipe_schema(self):
        with zipfile.ZipFile(self.wheel) as wheel:
            self.assertIn(PACKAGED_SCHEMA, wheel.namelist())

    def test_packaged_schema_matches_the_authored_one(self):
        authored = (REPO_ROOT / "schema" / "tasktree-schema.json").read_bytes()
        with zipfile.ZipFile(self.wheel) as wheel:
            self.assertEqual(wheel.read(PACKAGED_SCHEMA), authored)

    def test_packaged_schema_is_where_the_loader_looks(self):
        """The wheel path must match recipe_schema's packaged candidate."""
        from tasktree.recipe_schema import schema_candidates

        packaged_candidate = schema_candidates()[0]
        relative = packaged_candidate.relative_to(packaged_candidate.parents[2])
        self.assertEqual(relative.as_posix(), PACKAGED_SCHEMA)


@unittest.skipIf(shutil.which("uv") is None, "sdist build needs the uv CLI")
class TestSdistContents(unittest.TestCase):
    """
    Installing from an sdist builds a wheel from it, and that build applies
    the force-include -- but only if the sdist carries the authored schema in
    the first place. Nothing configures the sdist explicitly, so this rests
    on hatch's defaults, which is exactly the kind of thing that changes
    quietly (PR #212 review noted the wheel was covered and the sdist was
    not).
    """

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = TemporaryDirectory()
        result = subprocess.run(
            ["uv", "build", "--sdist", "--out-dir", cls._tmpdir.name, str(REPO_ROOT)],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            cls._tmpdir.cleanup()
            raise RuntimeError(f"sdist build failed: {result.stderr}")
        cls.sdist = next(Path(cls._tmpdir.name).glob("*.tar.gz"))

    @classmethod
    def tearDownClass(cls):
        cls._tmpdir.cleanup()

    def test_sdist_carries_the_authored_schema(self):
        with tarfile.open(self.sdist) as sdist:
            schema_entries = [
                name
                for name in sdist.getnames()
                if name.endswith("schema/tasktree-schema.json")
            ]
        self.assertEqual(
            len(schema_entries),
            1,
            "the sdist must carry the authored schema, or a wheel built from "
            "it has nothing to force-include",
        )


if __name__ == "__main__":
    unittest.main()
