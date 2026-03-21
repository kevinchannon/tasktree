"""Integration tests for Docker context-file and base-image-digest change detection."""

import os
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from typer.testing import CliRunner

from tasktree.cli import app


class TestDockerContextFileChangeTriggersRerun(unittest.TestCase):
    """Modifying a file inside the Docker build context causes the task to re-run."""

    def setUp(self):
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def _make_project(self, project_root: Path, output_file: Path) -> None:
        (project_root / "ctx").mkdir()
        (project_root / "ctx" / "app.py").write_text("version 1")
        (project_root / "Dockerfile").write_text("FROM scratch\n")
        (project_root / "tasktree.yaml").write_text(
            "runners:\n"
            "  builder:\n"
            "    dockerfile: Dockerfile\n"
            "    context: ctx\n"
            "tasks:\n"
            "  build:\n"
            "    run_in: builder\n"
            "    outputs: [output.txt]\n"
            "    cmd: echo done\n"
        )

    def _make_mock_docker_manager(self, output_file: Path) -> Mock:
        mock_dm = Mock()
        mock_dm.ensure_image_built.return_value = ("tt-runner-builder", "sha256:abc")
        mock_dm._built_images = {"builder": ("tt-runner-builder", "sha256:abc")}

        def fake_run(**kwargs):
            output_file.write_text("done")
            return Mock(returncode=0)

        mock_dm.run_in_container.side_effect = fake_run
        return mock_dm

    def test_context_file_change_triggers_rerun(self):
        """First run executes; unchanged context skips; modified file re-runs."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            output_file = project_root / "output.txt"
            self._make_project(project_root, output_file)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                with patch("tasktree.executor.docker_module.DockerManager") as MockDM:
                    MockDM.return_value = self._make_mock_docker_manager(output_file)

                    # First run — task executes (no prior state)
                    result = self.runner.invoke(app, ["build"], env=self.env)
                    self.assertEqual(result.exit_code, 0, result.stdout)
                    self.assertTrue(output_file.exists())
                    mtime_1 = output_file.stat().st_mtime

                    # Second run — task skips (nothing changed)
                    result = self.runner.invoke(app, ["build"], env=self.env)
                    self.assertEqual(result.exit_code, 0)
                    self.assertEqual(output_file.stat().st_mtime, mtime_1)

                    # Modify a context file
                    time.sleep(0.05)
                    (project_root / "ctx" / "app.py").write_text("version 2")

                    # Third run — task re-runs (context file changed)
                    result = self.runner.invoke(app, ["build"], env=self.env)
                    self.assertEqual(result.exit_code, 0)
                    self.assertGreater(output_file.stat().st_mtime, mtime_1)

            finally:
                os.chdir(original_cwd)

    def test_new_context_file_triggers_rerun(self):
        """Adding a new file to the context directory causes the task to re-run."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            output_file = project_root / "output.txt"
            self._make_project(project_root, output_file)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                with patch("tasktree.executor.docker_module.DockerManager") as MockDM:
                    MockDM.return_value = self._make_mock_docker_manager(output_file)

                    # First run
                    result = self.runner.invoke(app, ["build"], env=self.env)
                    self.assertEqual(result.exit_code, 0)
                    mtime_1 = output_file.stat().st_mtime

                    # Second run — skips
                    result = self.runner.invoke(app, ["build"], env=self.env)
                    self.assertEqual(output_file.stat().st_mtime, mtime_1)

                    # Add a new file to the context
                    time.sleep(0.05)
                    (project_root / "ctx" / "new_module.py").write_text("new code")

                    # Third run — re-runs (new context file)
                    result = self.runner.invoke(app, ["build"], env=self.env)
                    self.assertEqual(result.exit_code, 0)
                    self.assertGreater(output_file.stat().st_mtime, mtime_1)

            finally:
                os.chdir(original_cwd)


class TestBaseImageDigestChangeTriggersRerun(unittest.TestCase):
    """Pulling a new base image (digest changes locally) causes the task to re-run."""

    def setUp(self):
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def _make_project(self, project_root: Path) -> None:
        (project_root / "ctx").mkdir()
        (project_root / "Dockerfile").write_text("FROM python:3.11\n")
        (project_root / "tasktree.yaml").write_text(
            "runners:\n"
            "  builder:\n"
            "    dockerfile: Dockerfile\n"
            "    context: ctx\n"
            "tasks:\n"
            "  build:\n"
            "    run_in: builder\n"
            "    outputs: [output.txt]\n"
            "    cmd: echo done\n"
        )

    def _make_mock_docker_manager(self, output_file: Path) -> Mock:
        mock_dm = Mock()
        mock_dm.ensure_image_built.return_value = ("tt-runner-builder", "sha256:img-abc")
        mock_dm._built_images = {"builder": ("tt-runner-builder", "sha256:img-abc")}

        def fake_run(**kwargs):
            output_file.write_text("done")
            return Mock(returncode=0)

        mock_dm.run_in_container.side_effect = fake_run
        return mock_dm

    def test_base_image_digest_change_triggers_rerun(self):
        """First run stores digest; unchanged digest skips; changed digest re-runs."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            output_file = project_root / "output.txt"
            self._make_project(project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                with patch("tasktree.executor.docker_module.DockerManager") as MockDM:
                    MockDM.return_value = self._make_mock_docker_manager(output_file)

                    mock_digest = Mock(return_value="sha256:base-v1")
                    with patch(
                        "tasktree.executor.docker_module.get_local_base_image_digest",
                        mock_digest,
                    ):
                        # First run — task executes (no prior state)
                        result = self.runner.invoke(app, ["build"], env=self.env)
                        self.assertEqual(result.exit_code, 0, result.stdout)
                        self.assertTrue(output_file.exists())
                        mtime_1 = output_file.stat().st_mtime

                        # Second run — task skips (same digest)
                        result = self.runner.invoke(app, ["build"], env=self.env)
                        self.assertEqual(result.exit_code, 0)
                        self.assertEqual(output_file.stat().st_mtime, mtime_1)

                        # Third run — task re-runs (digest changed after docker pull)
                        mock_digest.return_value = "sha256:base-v2"
                        time.sleep(0.05)
                        result = self.runner.invoke(app, ["build"], env=self.env)
                        self.assertEqual(result.exit_code, 0)
                        self.assertGreater(output_file.stat().st_mtime, mtime_1)

            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
