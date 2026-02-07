"""End-to-end tests for recursion detection in nested task invocations."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.e2e import run_tasktree_cli


class TestRealSubprocessRecursion(unittest.TestCase):
    """E2E tests for recursion detection via real subprocess execution."""

    def test_real_subprocess_recursion_error(self):
        """Test that real subprocess execution detects recursion and shows error."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
  recursive-task:
    cmd: |
      echo "Before recursive call"
      tt recursive-task
      echo "After recursive call (should never reach here)"
"""
            )

            # Run tt via subprocess
            result = run_tasktree_cli(["recursive-task"], cwd=Path(tmpdir))

            # Should fail with non-zero exit code
            self.assertNotEqual(result.returncode, 0)

            # Error message should be in stderr or stdout
            combined_output = result.stdout + result.stderr
            self.assertIn("Recursion detected", combined_output)
            self.assertIn("recursive-task", combined_output)

    def test_real_subprocess_deep_chain_no_cycle(self):
        """Test that real deep chain without cycle succeeds."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            output_dir = Path(tmpdir) / "outputs"
            Path(output_dir).mkdir()

            recipe_path.write_text(
                """
tasks:
  chain-1:
    outputs: [outputs/chain1.txt]
    cmd: |
      echo "Chain 1" > outputs/chain1.txt
      tt chain-2

  chain-2:
    outputs: [outputs/chain2.txt]
    cmd: |
      echo "Chain 2" > outputs/chain2.txt
      tt chain-3

  chain-3:
    outputs: [outputs/chain3.txt]
    cmd: |
      echo "Chain 3" > outputs/chain3.txt
      tt chain-4

  chain-4:
    outputs: [outputs/chain4.txt]
    cmd: echo "Chain 4" > outputs/chain4.txt
"""
            )

            # Run tt via subprocess
            result = run_tasktree_cli(["chain-1"], cwd=Path(tmpdir))

            # Should succeed
            self.assertEqual(
                result.returncode,
                0,
                f"stdout: {result.stdout}\nstderr: {result.stderr}",
            )

            # Verify all outputs were created
            for i in range(1, 5):
                output_file = Path(output_dir) / f"chain{i}.txt"
                self.assertTrue(output_file.exists())

    @unittest.skip("Requires Docker runtime")
    def test_real_subprocess_cycle_in_docker(self):
        """Test that recursion detection works inside Docker container."""
        with TemporaryDirectory() as tmpdir:
            # Create Dockerfile
            dockerfile_path = Path(tmpdir) / "Dockerfile"
            dockerfile_path.write_text(
                """
FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -e .
"""
            )

            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
runners:
  docker-env:
    dockerfile: Dockerfile

tasks:
  docker-recursive:
    run_in: docker-env
    cmd: |
      echo "In Docker, before recursive call"
      tt docker-recursive
      echo "After recursive call (should never reach here)"
"""
            )

            # Run tt via subprocess
            result = subprocess.run(
                ["python3", "main.py", "docker-recursive"],
                cwd=tmpdir,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONPATH": str(Path.cwd())},
            )

            # Should fail with recursion error
            self.assertNotEqual(result.returncode, 0)

            combined_output = result.stdout + result.stderr
            self.assertIn("Recursion detected", combined_output)
            self.assertIn("docker-recursive", combined_output)


if __name__ == "__main__":
    unittest.main()
