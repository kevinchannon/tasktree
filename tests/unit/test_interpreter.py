"""Unit tests for the Interpreter strategy type."""

import platform
import unittest

from tasktree.interpreter import (
    INTERPRETER_LOOKUP,
    Interpreter,
    UnknownInterpreterError,
)


class TestInterpreterConstruction(unittest.TestCase):
    """Test direct construction of Interpreter instances."""

    def test_fields_are_stored(self):
        interp = Interpreter(
            name="bash", invocation_cmd=("bash",), script_extension=".sh"
        )
        self.assertEqual(interp.name, "bash")
        self.assertEqual(interp.invocation_cmd, ("bash",))
        self.assertEqual(interp.script_extension, ".sh")

    def test_default_invocation_cmd_is_empty_tuple(self):
        interp = Interpreter(name="custom")
        self.assertEqual(interp.invocation_cmd, ())

    def test_default_script_extension_is_empty_string(self):
        interp = Interpreter(name="custom")
        self.assertEqual(interp.script_extension, "")


class TestInterpreterLookup(unittest.TestCase):
    """Test INTERPRETER_LOOKUP contents."""

    def test_lookup_contains_all_expected_interpreters(self):
        expected = {"bash", "sh", "zsh", "fish", "cmd.exe", "powershell", "pwsh", "python", "python3"}
        self.assertEqual(set(INTERPRETER_LOOKUP.keys()), expected)

    def test_all_entries_are_interpreter_instances(self):
        for name, interp in INTERPRETER_LOOKUP.items():
            with self.subTest(name=name):
                self.assertIsInstance(interp, Interpreter)

    def test_all_invocation_cmds_are_non_empty_tuples(self):
        for name, interp in INTERPRETER_LOOKUP.items():
            with self.subTest(name=name):
                self.assertIsInstance(interp.invocation_cmd, tuple)
                self.assertGreater(len(interp.invocation_cmd), 0)

    def test_bash_invocation(self):
        self.assertEqual(INTERPRETER_LOOKUP["bash"].invocation_cmd, ("bash",))

    def test_sh_invocation(self):
        self.assertEqual(INTERPRETER_LOOKUP["sh"].invocation_cmd, ("sh",))

    def test_zsh_invocation(self):
        self.assertEqual(INTERPRETER_LOOKUP["zsh"].invocation_cmd, ("zsh",))

    def test_fish_invocation(self):
        self.assertEqual(INTERPRETER_LOOKUP["fish"].invocation_cmd, ("fish",))

    def test_cmd_exe_invocation(self):
        self.assertEqual(INTERPRETER_LOOKUP["cmd.exe"].invocation_cmd, ("cmd.exe", "/c"))

    def test_powershell_invocation(self):
        self.assertEqual(
            INTERPRETER_LOOKUP["powershell"].invocation_cmd,
            ("powershell", "-ExecutionPolicy", "Bypass", "-File"),
        )

    def test_pwsh_invocation(self):
        self.assertEqual(
            INTERPRETER_LOOKUP["pwsh"].invocation_cmd,
            ("pwsh", "-ExecutionPolicy", "Bypass", "-File"),
        )

    def test_python_invocation(self):
        self.assertEqual(INTERPRETER_LOOKUP["python"].invocation_cmd, ("python",))

    def test_python3_invocation(self):
        self.assertEqual(INTERPRETER_LOOKUP["python3"].invocation_cmd, ("python3",))

    def test_posix_shells_have_sh_extension(self):
        for name in ("bash", "sh", "zsh"):
            with self.subTest(name=name):
                self.assertEqual(INTERPRETER_LOOKUP[name].script_extension, ".sh")

    def test_fish_has_fish_extension(self):
        self.assertEqual(INTERPRETER_LOOKUP["fish"].script_extension, ".fish")

    def test_cmd_exe_has_bat_extension(self):
        self.assertEqual(INTERPRETER_LOOKUP["cmd.exe"].script_extension, ".bat")

    def test_powershell_has_ps1_extension(self):
        self.assertEqual(INTERPRETER_LOOKUP["powershell"].script_extension, ".ps1")

    def test_pwsh_has_ps1_extension(self):
        self.assertEqual(INTERPRETER_LOOKUP["pwsh"].script_extension, ".ps1")

    def test_python_has_py_extension(self):
        self.assertEqual(INTERPRETER_LOOKUP["python"].script_extension, ".py")

    def test_python3_has_py_extension(self):
        self.assertEqual(INTERPRETER_LOOKUP["python3"].script_extension, ".py")


class TestInterpreterFromName(unittest.TestCase):
    """Test Interpreter.from_name() static method."""

    def test_from_name_returns_correct_interpreter_for_bash(self):
        interp = Interpreter.from_name("bash")
        self.assertEqual(interp.name, "bash")
        self.assertEqual(interp.invocation_cmd, ("bash",))

    def test_from_name_returns_correct_interpreter_for_powershell(self):
        interp = Interpreter.from_name("powershell")
        self.assertEqual(interp.script_extension, ".ps1")

    def test_from_name_raises_for_unknown_name(self):
        with self.assertRaises(UnknownInterpreterError):
            Interpreter.from_name("not-a-real-interpreter")

    def test_from_name_error_message_includes_name(self):
        with self.assertRaises(UnknownInterpreterError) as ctx:
            Interpreter.from_name("bad-shell")
        self.assertIn("bad-shell", str(ctx.exception))

    def test_from_name_works_for_all_known_interpreters(self):
        for name in INTERPRETER_LOOKUP:
            with self.subTest(name=name):
                interp = Interpreter.from_name(name)
                self.assertEqual(interp.name, name)


class TestInterpreterDefaults(unittest.TestCase):
    """Test host_default() and container_default() static methods."""

    def test_container_default_is_sh(self):
        interp = Interpreter.container_default()
        self.assertEqual(interp.name, "sh")
        self.assertEqual(interp.invocation_cmd, ("sh",))

    def test_container_default_has_sh_extension(self):
        interp = Interpreter.container_default()
        self.assertEqual(interp.script_extension, ".sh")

    @unittest.skipIf(platform.system() == "Windows", "Unix-only behaviour")
    def test_host_default_is_bash_on_unix(self):
        interp = Interpreter.host_default()
        self.assertEqual(interp.name, "bash")

    @unittest.skipUnless(platform.system() == "Windows", "Windows-only behaviour")
    def test_host_default_is_cmd_on_windows(self):
        interp = Interpreter.host_default()
        self.assertEqual(interp.name, "cmd.exe")

    def test_host_default_returns_interpreter_instance(self):
        interp = Interpreter.host_default()
        self.assertIsInstance(interp, Interpreter)

    def test_container_default_returns_interpreter_instance(self):
        interp = Interpreter.container_default()
        self.assertIsInstance(interp, Interpreter)


class TestInterpreterFromShellCmd(unittest.TestCase):
    """Tests for the Interpreter.from_shell_cmd bridge factory."""

    def test_known_shell_name(self):
        interp = Interpreter.from_shell_cmd(["bash"])
        self.assertEqual(interp.name, "bash")
        self.assertEqual(interp.invocation_cmd, ("bash",))
        self.assertEqual(interp.script_extension, ".sh")

    def test_custom_flags_are_preserved(self):
        interp = Interpreter.from_shell_cmd(["bash", "-x"])
        self.assertEqual(interp.invocation_cmd, ("bash", "-x"))
        self.assertEqual(interp.script_extension, ".sh")

    def test_powershell_invocation(self):
        interp = Interpreter.from_shell_cmd(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File"]
        )
        self.assertEqual(interp.invocation_cmd[0], "powershell")
        self.assertEqual(interp.script_extension, ".ps1")

    def test_unknown_executable_derives_extension(self):
        interp = Interpreter.from_shell_cmd(["/usr/local/bin/cmd.exe", "/c"])
        self.assertEqual(interp.script_extension, ".bat")

    def test_path_containing_cmd_substring_is_not_bat(self):
        """A path like /opt/cmd_tools/bash must not be classified as .bat."""
        interp = Interpreter.from_shell_cmd(["/opt/cmd_tools/bash"])
        self.assertEqual(interp.script_extension, ".sh")

    def test_path_containing_pwsh_substring_is_not_ps1(self):
        interp = Interpreter.from_shell_cmd(["/opt/pwsh_helpers/sh"])
        self.assertEqual(interp.script_extension, ".sh")

    def test_empty_cmd_falls_back_to_host_default(self):
        interp = Interpreter.from_shell_cmd([])
        self.assertEqual(interp, Interpreter.host_default())


class TestInterpreterHostScriptExtension(unittest.TestCase):
    """Tests for Interpreter.host_script_extension (host-path policy)."""

    @unittest.skipIf(platform.system() == "Windows", "Unix-only behaviour")
    def test_unix_uses_no_extension(self):
        for name in ("bash", "sh", "python3", "cmd.exe", "powershell"):
            with self.subTest(interpreter=name):
                self.assertEqual(
                    Interpreter.from_name(name).host_script_extension(), ""
                )

    @unittest.skipUnless(platform.system() == "Windows", "Windows-only behaviour")
    def test_windows_uses_dispatch_extensions_only(self):
        self.assertEqual(
            Interpreter.from_name("cmd.exe").host_script_extension(), ".bat"
        )
        self.assertEqual(
            Interpreter.from_name("powershell").host_script_extension(), ".ps1"
        )
        self.assertEqual(Interpreter.from_name("bash").host_script_extension(), "")
        self.assertEqual(
            Interpreter.from_name("python3").host_script_extension(), ""
        )


if __name__ == "__main__":
    unittest.main()
