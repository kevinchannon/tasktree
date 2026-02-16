"""
Unit tests for temp_script module.

Tests the TempScript context manager for creating, managing, and cleaning up
temporary shell script files.

"""

import os
import platform
import stat
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from helpers.logging import logger_stub
from tasktree.temp_script import TempScript


class TestTempScript(unittest.TestCase):
    """
    Test TempScript context manager.

    """

    def test_creates_temp_script_with_command_only(self):
        """
        Test TempScript creates a temporary script file with command only.

        """
        cmd = "echo hello"

        with TempScript(logger=logger_stub, cmd=cmd) as script_path:
            # Verify script file exists
            self.assertTrue(script_path.exists())
            self.assertTrue(script_path.is_file())

            # Verify file extension
            is_windows = platform.system() == "Windows"
            expected_ext = ".bat" if is_windows else ".sh"
            self.assertTrue(str(script_path).endswith(expected_ext))

            # Verify content
            content = script_path.read_text()
            self.assertIn(cmd, content)

            # On Unix/macOS, verify shebang is present
            if not is_windows:
                self.assertTrue(content.startswith("#!/usr/bin/env bash\n"))

        # Verify cleanup - script should be deleted after context exit
        self.assertFalse(script_path.exists())

    def test_creates_temp_script_with_preamble(self):
        """
        Test TempScript creates script with preamble prepended.

        """
        cmd = "echo hello"
        preamble = "set -e\n"

        with TempScript(logger=logger_stub, cmd=cmd, preamble=preamble) as script_path:
            content = script_path.read_text()

            # Verify preamble is in content
            self.assertIn(preamble, content)

            # Verify command is in content
            self.assertIn(cmd, content)

            # Verify preamble comes before command
            preamble_pos = content.index(preamble)
            cmd_pos = content.index(cmd)
            self.assertLess(preamble_pos, cmd_pos)

        self.assertFalse(script_path.exists())

    def test_preamble_without_trailing_newline(self):
        """
        Test TempScript adds newline after preamble if missing.

        """
        cmd = "echo hello"
        preamble = "set -e"  # No trailing newline

        with TempScript(logger=logger_stub, cmd=cmd, preamble=preamble) as script_path:
            content = script_path.read_text()

            # Verify newline was added after preamble
            self.assertIn("set -e\n", content)

        self.assertFalse(script_path.exists())

    def test_multiline_command(self):
        """
        Test TempScript handles multi-line commands correctly.

        """
        cmd = "echo hello\necho world\necho !"

        with TempScript(logger=logger_stub, cmd=cmd) as script_path:
            content = script_path.read_text()

            # Verify all lines are present
            self.assertIn("echo hello", content)
            self.assertIn("echo world", content)
            self.assertIn("echo !", content)

        self.assertFalse(script_path.exists())

    def test_custom_shell(self):
        """
        Test TempScript uses custom shell in shebang.

        """
        is_windows = platform.system() == "Windows"
        if is_windows:
            self.skipTest("Shebang test only applicable on Unix/macOS")

        cmd = "echo hello"
        shell = "zsh"

        with TempScript(logger=logger_stub, cmd=cmd, shell=shell) as script_path:
            content = script_path.read_text()

            # Verify custom shell in shebang
            self.assertTrue(content.startswith("#!/usr/bin/env zsh\n"))

        self.assertFalse(script_path.exists())

    def test_script_is_executable_on_unix(self):
        """
        Test TempScript makes script executable on Unix/macOS.

        """
        is_windows = platform.system() == "Windows"
        if is_windows:
            self.skipTest("Executable test only applicable on Unix/macOS")

        cmd = "echo hello"

        with TempScript(logger=logger_stub, cmd=cmd) as script_path:
            # Verify script is executable
            file_stat = os.stat(script_path)
            is_executable = bool(file_stat.st_mode & stat.S_IEXEC)
            self.assertTrue(is_executable)

        self.assertFalse(script_path.exists())

    def test_cleanup_on_exception(self):
        """
        Test TempScript cleans up script even when exception occurs.

        """
        cmd = "echo hello"
        script_path_ref = None

        try:
            with TempScript(logger=logger_stub, cmd=cmd) as script_path:
                script_path_ref = script_path
                # Verify script exists during context
                self.assertTrue(script_path.exists())
                # Raise exception to test cleanup
                raise ValueError("Test exception")
        except ValueError:
            pass

        # Verify cleanup happened despite exception
        self.assertIsNotNone(script_path_ref)
        self.assertFalse(script_path_ref.exists())

    def test_cleanup_ignores_os_errors(self):
        """
        Test TempScript cleanup ignores OSError during file deletion.

        """
        cmd = "echo hello"

        with patch("os.unlink", side_effect=OSError("Mock error")):
            # Should not raise exception even if unlink fails
            with TempScript(logger=logger_stub, cmd=cmd) as script_path:
                pass

        # Test passes if no exception was raised

    def test_command_with_existing_shebang(self):
        """
        Test TempScript does not add shebang if command already has one.

        """
        is_windows = platform.system() == "Windows"
        if is_windows:
            self.skipTest("Shebang test only applicable on Unix/macOS")

        cmd = "#!/bin/sh\necho hello"

        with TempScript(logger=logger_stub, cmd=cmd, shell="bash") as script_path:
            content = script_path.read_text()

            # Verify original shebang is preserved
            self.assertTrue(content.startswith("#!/bin/sh\n"))

            # Verify bash shebang was NOT added
            self.assertNotIn("#!/usr/bin/env bash", content)

        self.assertFalse(script_path.exists())

    def test_empty_command(self):
        """
        Test TempScript handles empty command string.

        """
        cmd = ""

        with TempScript(logger=logger_stub, cmd=cmd) as script_path:
            content = script_path.read_text()

            # On Unix/macOS, should have shebang even with empty command
            is_windows = platform.system() == "Windows"
            if not is_windows:
                self.assertTrue(content.startswith("#!/usr/bin/env bash\n"))

            self.assertTrue(script_path.exists())

        self.assertFalse(script_path.exists())

    def test_script_path_type(self):
        """
        Test TempScript returns Path object, not string.

        """
        cmd = "echo hello"

        with TempScript(logger=logger_stub, cmd=cmd) as script_path:
            # Verify return type is Path
            self.assertIsInstance(script_path, Path)

        self.assertFalse(script_path.exists())

    def test_windows_bat_extension(self):
        """
        Test TempScript uses .bat extension on Windows.

        """
        is_windows = platform.system() == "Windows"
        if not is_windows:
            self.skipTest("Windows-specific test")

        cmd = "echo hello"

        with TempScript(logger=logger_stub, cmd=cmd) as script_path:
            # Verify .bat extension
            self.assertTrue(str(script_path).endswith(".bat"))

            # Verify no shebang on Windows
            content = script_path.read_text()
            self.assertNotIn("#!/usr/bin/env", content)

        self.assertFalse(script_path.exists())

    def test_non_ascii_characters_in_command(self):
        """
        Test TempScript handles non-ASCII (UTF-8) characters in commands.

        """
        # Test with various Unicode characters
        cmd = "echo 'Hello 世界 🌍 Привет café'"

        with TempScript(logger=logger_stub, cmd=cmd) as script_path:
            # Read with explicit UTF-8 encoding
            content = script_path.read_text(encoding="utf-8")

            # Verify all Unicode characters are preserved
            self.assertIn("世界", content)
            self.assertIn("🌍", content)
            self.assertIn("Привет", content)
            self.assertIn("café", content)

        self.assertFalse(script_path.exists())


if __name__ == "__main__":
    unittest.main()
