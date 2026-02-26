"""Unit tests for ShellConfig dataclass, SHELL_LOOKUP table, and parse_shell_config."""

import unittest

from tasktree.parser import SHELL_LOOKUP, ShellConfig, parse_shell_config


class TestShellLookup(unittest.TestCase):
    """Tests for the SHELL_LOOKUP table."""

    def test_lookup_table_contains_expected_shells(self):
        """Test that all specified shells are present in SHELL_LOOKUP."""
        expected_shells = {"bash", "sh", "zsh", "fish", "cmd.exe", "powershell"}
        self.assertEqual(set(SHELL_LOOKUP.keys()), expected_shells)

    def test_all_entries_are_lists(self):
        """Test that all SHELL_LOOKUP values are lists of strings."""
        for name, cmd in SHELL_LOOKUP.items():
            with self.subTest(shell=name):
                self.assertIsInstance(cmd, list)
                self.assertTrue(all(isinstance(s, str) for s in cmd))

    def test_bash_maps_to_bash_dash_c(self):
        """Test that 'bash' maps to ['bash', '-c']."""
        self.assertEqual(SHELL_LOOKUP["bash"], ["bash", "-c"])

    def test_sh_maps_to_sh_dash_c(self):
        """Test that 'sh' maps to ['sh', '-c']."""
        self.assertEqual(SHELL_LOOKUP["sh"], ["sh", "-c"])

    def test_zsh_maps_to_zsh_dash_c(self):
        """Test that 'zsh' maps to ['zsh', '-c']."""
        self.assertEqual(SHELL_LOOKUP["zsh"], ["zsh", "-c"])

    def test_fish_maps_to_fish_dash_c(self):
        """Test that 'fish' maps to ['fish', '-c']."""
        self.assertEqual(SHELL_LOOKUP["fish"], ["fish", "-c"])

    def test_cmd_exe_maps_to_cmd_slash_c(self):
        """Test that 'cmd.exe' maps to ['cmd.exe', '/c']."""
        self.assertEqual(SHELL_LOOKUP["cmd.exe"], ["cmd.exe", "/c"])

    def test_powershell_maps_to_powershell_command(self):
        """Test that 'powershell' maps to ['powershell', '-Command']."""
        self.assertEqual(SHELL_LOOKUP["powershell"], ["powershell", "-Command"])


class TestShellConfig(unittest.TestCase):
    """Tests for the ShellConfig dataclass."""

    def test_shell_config_creation_with_cmd_and_preamble(self):
        """Test creating ShellConfig with cmd and preamble."""
        config = ShellConfig(cmd=["bash", "-c"], preamble="set -euo pipefail")
        self.assertEqual(config.cmd, ["bash", "-c"])
        self.assertEqual(config.preamble, "set -euo pipefail")

    def test_shell_config_creation_with_cmd_only(self):
        """Test creating ShellConfig with only cmd (preamble defaults to empty string)."""
        config = ShellConfig(cmd=["sh", "-c"])
        self.assertEqual(config.cmd, ["sh", "-c"])
        self.assertEqual(config.preamble, "")

    def test_shell_config_preamble_defaults_to_empty_string(self):
        """Test that preamble defaults to empty string when not specified."""
        config = ShellConfig(cmd=["bash", "-c"])
        self.assertEqual(config.preamble, "")

    def test_shell_config_cmd_is_list(self):
        """Test that cmd is stored as a list."""
        config = ShellConfig(cmd=["powershell", "-Command"])
        self.assertIsInstance(config.cmd, list)

    def test_shell_config_equality(self):
        """Test that two ShellConfigs with same values are equal."""
        config1 = ShellConfig(cmd=["bash", "-c"], preamble="set -e")
        config2 = ShellConfig(cmd=["bash", "-c"], preamble="set -e")
        self.assertEqual(config1, config2)

    def test_shell_config_inequality_on_cmd(self):
        """Test that ShellConfigs with different cmd are not equal."""
        config1 = ShellConfig(cmd=["bash", "-c"])
        config2 = ShellConfig(cmd=["sh", "-c"])
        self.assertNotEqual(config1, config2)

    def test_shell_config_inequality_on_preamble(self):
        """Test that ShellConfigs with different preamble are not equal."""
        config1 = ShellConfig(cmd=["bash", "-c"], preamble="set -e")
        config2 = ShellConfig(cmd=["bash", "-c"], preamble="set -euo pipefail")
        self.assertNotEqual(config1, config2)


class TestParseShellConfig(unittest.TestCase):
    """Tests for the parse_shell_config function."""

    def test_bare_string_shorthand_looks_up_shell_lookup(self):
        """Test that a bare string shell name is resolved via SHELL_LOOKUP."""
        config = parse_shell_config("bash", "test-runner")
        self.assertEqual(config.cmd, ["bash", "-c"])
        self.assertEqual(config.preamble, "")

    def test_bare_string_shorthand_returns_independent_copy(self):
        """Test that the returned cmd list is a copy, not the SHELL_LOOKUP entry."""
        config = parse_shell_config("bash", "test-runner")
        config.cmd.append("--extra")
        # SHELL_LOOKUP must not be mutated
        self.assertEqual(SHELL_LOOKUP["bash"], ["bash", "-c"])

    def test_cmd_as_string_shorthand(self):
        """Test that shell: {cmd: zsh} is resolved via SHELL_LOOKUP."""
        config = parse_shell_config({"cmd": "zsh"}, "test-runner")
        self.assertEqual(config.cmd, ["zsh", "-c"])

    def test_cmd_as_string_returns_independent_copy(self):
        """Test that cmd-as-string returns a copy, not the SHELL_LOOKUP entry."""
        config = parse_shell_config({"cmd": "sh"}, "test-runner")
        config.cmd.append("--extra")
        self.assertEqual(SHELL_LOOKUP["sh"], ["sh", "-c"])

    def test_cmd_as_list_verbatim(self):
        """Test that shell: {cmd: [/usr/local/bin/bash, -c]} is passed through as-is."""
        config = parse_shell_config({"cmd": ["/usr/local/bin/bash", "-c"]}, "test-runner")
        self.assertEqual(config.cmd, ["/usr/local/bin/bash", "-c"])

    def test_cmd_as_list_with_preamble(self):
        """Test that preamble is parsed alongside cmd list."""
        config = parse_shell_config({"cmd": ["bash", "-c"], "preamble": "set -euo pipefail"}, "test-runner")
        self.assertEqual(config.cmd, ["bash", "-c"])
        self.assertEqual(config.preamble, "set -euo pipefail")

    def test_unknown_shell_string_raises_value_error(self):
        """Test that an unknown bare shell name raises ValueError."""
        with self.assertRaises(ValueError) as cm:
            parse_shell_config("tcsh", "test-runner")
        self.assertIn("unknown shell", str(cm.exception))
        self.assertIn("tcsh", str(cm.exception))

    def test_unknown_shell_cmd_string_raises_value_error(self):
        """Test that an unknown shell name in cmd raises ValueError."""
        with self.assertRaises(ValueError) as cm:
            parse_shell_config({"cmd": "tcsh"}, "test-runner")
        self.assertIn("unknown shell", str(cm.exception))

    def test_non_string_cmd_raises_value_error(self):
        """Test that a non-string, non-list cmd raises ValueError."""
        with self.assertRaises(ValueError) as cm:
            parse_shell_config({"cmd": 42}, "test-runner")
        self.assertIn("must be a string or list", str(cm.exception))

    def test_non_string_preamble_raises_value_error(self):
        """Test that a non-string preamble raises ValueError."""
        with self.assertRaises(ValueError) as cm:
            parse_shell_config({"cmd": ["bash", "-c"], "preamble": 123}, "test-runner")
        self.assertIn("preamble", str(cm.exception))
        self.assertIn("must be a string", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
