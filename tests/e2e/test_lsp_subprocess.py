"""End-to-end tests for LSP server subprocess."""

import json
import subprocess
import unittest
import sys
from pathlib import Path


class TestLSPSubprocess(unittest.TestCase):
    """E2E tests spawning tt-lsp as a subprocess."""

    def _send_request(self, proc, method, params):
        """Send an LSP request to the subprocess."""
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        }
        content = json.dumps(request)
        message = f"Content-Length: {len(content)}\r\n\r\n{content}"
        proc.stdin.write(message.encode())
        proc.stdin.flush()

    def _send_notification(self, proc, method, params):
        """Send an LSP notification to the subprocess."""
        notification = {"jsonrpc": "2.0", "method": method, "params": params}
        content = json.dumps(notification)
        message = f"Content-Length: {len(content)}\r\n\r\n{content}"
        proc.stdin.write(message.encode())
        proc.stdin.flush()

    def _read_response(self, proc):
        """Read an LSP response from the subprocess."""
        # Read headers
        headers = {}
        while True:
            line = proc.stdout.readline().decode().strip()
            if not line:
                break
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip()] = value.strip()

        # Read content
        content_length = int(headers.get("Content-Length", 0))
        if content_length > 0:
            content = proc.stdout.read(content_length).decode()
            return json.loads(content)

        return None

    def test_lsp_server_spawns_and_responds(self):
        """Test that tt-lsp subprocess can be spawned and responds to initialize."""
        # Find the tt-lsp entry point
        # In tests, we use 'uv run' to execute the entry point
        project_root = Path(__file__).parent.parent.parent

        # Spawn the server
        proc = subprocess.Popen(
            [sys.executable, "-m", "tasktree.lsp.server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=project_root,
        )

        try:
            # Send initialize request
            self._send_request(
                proc,
                "initialize",
                {
                    "processId": 12345,
                    "rootUri": "file:///test/project",
                    "capabilities": {},
                },
            )

            # Read response
            response = self._read_response(proc)

            # Verify response
            self.assertIsNotNone(response)
            self.assertEqual(response.get("id"), 1)
            self.assertIn("result", response)
            self.assertIn("capabilities", response["result"])
            self.assertIn("completionProvider", response["result"]["capabilities"])

            # Send shutdown
            self._send_request(proc, "shutdown", {})
            shutdown_response = self._read_response(proc)
            self.assertIsNotNone(shutdown_response)

            # Send exit notification
            self._send_notification(proc, "exit", {})

        finally:
            # Clean up
            proc.terminate()
            proc.wait(timeout=5)

    def test_lsp_completion_e2e(self):
        """Test end-to-end completion workflow via subprocess."""
        project_root = Path(__file__).parent.parent.parent

        # Spawn the server
        proc = subprocess.Popen(
            [sys.executable, "-m", "tasktree.lsp.server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=project_root,
        )

        try:
            # Initialize
            self._send_request(
                proc,
                "initialize",
                {
                    "processId": 12345,
                    "rootUri": "file:///test/project",
                    "capabilities": {},
                },
            )
            init_response = self._read_response(proc)
            self.assertIsNotNone(init_response)

            # Open document
            self._send_notification(
                proc,
                "textDocument/didOpen",
                {
                    "textDocument": {
                        "uri": "file:///test/tasktree.yaml",
                        "languageId": "yaml",
                        "version": 1,
                        "text": "tasks:\n  build:\n    cmd: echo {{ tt.",
                    }
                },
            )

            # Request completion
            self._send_request(
                proc,
                "textDocument/completion",
                {
                    "textDocument": {"uri": "file:///test/tasktree.yaml"},
                    "position": {"line": 2, "character": 25},
                },
            )

            # Read completion response
            completion_response = self._read_response(proc)

            # Verify completions
            self.assertIsNotNone(completion_response)
            self.assertIn("result", completion_response)
            result = completion_response["result"]

            # Should get 8 built-in variables
            self.assertEqual(len(result["items"]), 8)
            var_names = {item["label"] for item in result["items"]}
            expected = {
                "project_root",
                "recipe_dir",
                "task_name",
                "working_dir",
                "timestamp",
                "timestamp_unix",
                "user_home",
                "user_name",
            }
            self.assertEqual(var_names, expected)

            # Shutdown
            self._send_request(proc, "shutdown", {})
            self._read_response(proc)
            self._send_notification(proc, "exit", {})

        finally:
            proc.terminate()
            proc.wait(timeout=5)

    def test_lsp_var_completion_e2e(self):
        """Test end-to-end var.* completion workflow via subprocess."""
        project_root = Path(__file__).parent.parent.parent

        # Spawn the server
        proc = subprocess.Popen(
            [sys.executable, "-m", "tasktree.lsp.server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=project_root,
        )

        try:
            # Initialize
            self._send_request(
                proc,
                "initialize",
                {
                    "processId": 12345,
                    "rootUri": "file:///test/project",
                    "capabilities": {},
                },
            )
            init_response = self._read_response(proc)
            self.assertIsNotNone(init_response)

            # Open document with variables
            self._send_notification(
                proc,
                "textDocument/didOpen",
                {
                    "textDocument": {
                        "uri": "file:///test/tasktree.yaml",
                        "languageId": "yaml",
                        "version": 1,
                        "text": "variables:\n  my_var: value\n  another: test\ntasks:\n  build:\n    cmd: echo {{ var.",
                    }
                },
            )

            # Request completion
            self._send_request(
                proc,
                "textDocument/completion",
                {
                    "textDocument": {"uri": "file:///test/tasktree.yaml"},
                    "position": {"line": 4, "character": 26},
                },
            )

            # Read completion response
            completion_response = self._read_response(proc)

            # Verify completions
            self.assertIsNotNone(completion_response)
            self.assertIn("result", completion_response)
            result = completion_response["result"]

            # Should get both user variables
            self.assertEqual(len(result["items"]), 2)
            var_names = {item["label"] for item in result["items"]}
            self.assertEqual(var_names, {"my_var", "another"})

            # Shutdown
            self._send_request(proc, "shutdown", {})
            self._read_response(proc)
            self._send_notification(proc, "exit", {})

        finally:
            proc.terminate()
            proc.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
