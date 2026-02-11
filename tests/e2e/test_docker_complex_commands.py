"""E2E tests for Docker execution with complex multi-line commands."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from . import is_docker_available, run_tasktree_cli


class TestDockerComplexCommands(unittest.TestCase):
    """
    Test Docker container execution with complex multi-line commands and special characters.
    """

    @classmethod
    def setUpClass(cls):
        """Ensure Docker is available before running tests."""
        if not is_docker_available():
            raise RuntimeError(
                "Docker is not available or not running. "
                "E2E tests require Docker to be installed and the daemon to be running."
            )

    def test_multiline_command_with_special_characters(self):
        """
        Test complex multi-line command with special characters, quotes, and variables.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create Dockerfile
            (project_root / "Dockerfile").write_text(
                "FROM alpine:latest\nWORKDIR /workspace\n"
            )

            # Create output directory
            (project_root / "output").mkdir()

            # Create recipe with complex multi-line command
            (project_root / "tasktree.yaml").write_text("""
runners:
  alpine:
    dockerfile: ./Dockerfile
    context: .
    volumes: ["./output:/workspace/output"]

tasks:
  complex:
    run_in: alpine
    outputs: [output/result.txt]
    cmd: |
      # Test various shell features
      MSG="Hello from 'Docker'"
      echo "$MSG" > /workspace/output/result.txt

      # Test special characters
      echo "Special chars: !@#$%^&*()" >> /workspace/output/result.txt

      # Test quotes and escaping
      echo 'Single quotes: $MSG' >> /workspace/output/result.txt
      echo "Double quotes: $MSG" >> /workspace/output/result.txt

      # Test command substitution
      echo "Date: $(date +%Y-%m-%d)" >> /workspace/output/result.txt

      # Test multi-line string
      cat <<EOF >> /workspace/output/result.txt
      Multi-line
      heredoc
      content
      EOF
""")

            # Execute
            result = run_tasktree_cli(["complex"], cwd=project_root)

            # Assert success
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )

            # Verify output
            output_file = project_root / "output" / "result.txt"
            self.assertTrue(output_file.exists(), "Output file not created")

            content = output_file.read_text()
            self.assertIn("Hello from 'Docker'", content)
            self.assertIn("Special chars: !@#$%^&*()", content)
            self.assertIn("Single quotes: $MSG", content)  # Literal $MSG
            self.assertIn("Double quotes: Hello from 'Docker'", content)  # Expanded $MSG
            self.assertIn("Date:", content)
            self.assertIn("Multi-line", content)
            self.assertIn("heredoc", content)

    def test_command_with_pipes_and_redirects(self):
        """
        Test command with pipes, redirects, and command chaining.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create Dockerfile
            (project_root / "Dockerfile").write_text(
                "FROM alpine:latest\nWORKDIR /workspace\n"
            )

            # Create output directory
            (project_root / "output").mkdir()

            # Create recipe
            (project_root / "tasktree.yaml").write_text("""
runners:
  alpine:
    dockerfile: ./Dockerfile
    context: .
    volumes: ["./output:/workspace/output"]

tasks:
  pipes:
    run_in: alpine
    outputs: [output/filtered.txt, output/count.txt]
    cmd: |
      # Generate some data
      echo -e "apple\\nbanana\\napple\\ncherry\\napple" > /tmp/fruits.txt

      # Use pipes and redirects
      cat /tmp/fruits.txt | grep "apple" | wc -l > /workspace/output/count.txt
      cat /tmp/fruits.txt | sort | uniq > /workspace/output/filtered.txt

      # Command chaining
      echo "Step 1" && echo "Step 2" && echo "Step 3" >> /workspace/output/filtered.txt
""")

            # Execute
            result = run_tasktree_cli(["pipes"], cwd=project_root)

            # Assert success
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )

            # Verify count output (should be 3 apples)
            count_file = project_root / "output" / "count.txt"
            self.assertTrue(count_file.exists(), "Count file not created")
            self.assertEqual(count_file.read_text().strip(), "3")

            # Verify filtered output
            filtered_file = project_root / "output" / "filtered.txt"
            self.assertTrue(filtered_file.exists(), "Filtered file not created")
            content = filtered_file.read_text()
            self.assertIn("apple", content)
            self.assertIn("banana", content)
            self.assertIn("cherry", content)
            self.assertIn("Step 3", content)

    def test_command_with_error_handling(self):
        """
        Test command with error handling and conditional execution.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create Dockerfile
            (project_root / "Dockerfile").write_text(
                "FROM alpine:latest\nWORKDIR /workspace\n"
            )

            # Create output directory
            (project_root / "output").mkdir()

            # Create recipe
            (project_root / "tasktree.yaml").write_text("""
runners:
  alpine:
    dockerfile: ./Dockerfile
    context: .
    preamble: set -e  # Exit on error
    volumes: ["./output:/workspace/output"]

tasks:
  conditional:
    run_in: alpine
    outputs: [output/result.txt]
    cmd: |
      # Test conditional execution
      if [ -f /workspace/output/nonexistent.txt ]; then
        echo "File exists" > /workspace/output/result.txt
      else
        echo "File does not exist" > /workspace/output/result.txt
      fi

      # Test || operator (should not execute second part)
      echo "Success" >> /workspace/output/result.txt || echo "Failure"

      # Test && operator
      [ 1 -eq 1 ] && echo "Math works" >> /workspace/output/result.txt
""")

            # Execute
            result = run_tasktree_cli(["conditional"], cwd=project_root)

            # Assert success
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )

            # Verify output
            output_file = project_root / "output" / "result.txt"
            self.assertTrue(output_file.exists(), "Output file not created")

            content = output_file.read_text()
            self.assertIn("File does not exist", content)
            self.assertIn("Success", content)
            self.assertIn("Math works", content)


if __name__ == "__main__":
    unittest.main()
