"""Unit tests for the Interpreter value type."""

import unittest

from tasktree.interpreter import Interpreter, InterpreterError


class TestInterpreterConstruction(unittest.TestCase):
    """Direct construction and validation of Interpreter instances."""

    def test_minimal_interpreter(self):
        interp = Interpreter(cmd="bash")
        self.assertEqual(interp.cmd, "bash")
        self.assertEqual(interp.ext, "")
        self.assertEqual(interp.preamble, "")

    def test_full_interpreter(self):
        interp = Interpreter(cmd="cmd.exe", ext=".bat", preamble="@echo off")
        self.assertEqual(interp.cmd, "cmd.exe")
        self.assertEqual(interp.ext, ".bat")
        self.assertEqual(interp.preamble, "@echo off")

    def test_empty_cmd_raises(self):
        with self.assertRaises(InterpreterError):
            Interpreter(cmd="")

    def test_ext_without_leading_dot_raises(self):
        with self.assertRaises(InterpreterError) as ctx:
            Interpreter(cmd="sh", ext="bat")
        self.assertIn("dot", str(ctx.exception))

    def test_empty_ext_is_allowed(self):
        self.assertEqual(Interpreter(cmd="sh", ext="").ext, "")

    def test_is_frozen(self):
        interp = Interpreter(cmd="sh")
        with self.assertRaises(Exception):
            interp.cmd = "bash"  # type: ignore[misc]


class TestInterpreterInvocation(unittest.TestCase):
    """The invocation property tokenises cmd verbatim with shlex."""

    def test_single_token(self):
        self.assertEqual(Interpreter(cmd="bash").invocation, ["bash"])

    def test_multiple_tokens_preserved(self):
        self.assertEqual(
            Interpreter(cmd="cmd.exe /c").invocation, ["cmd.exe", "/c"]
        )

    def test_quoted_tokens(self):
        self.assertEqual(
            Interpreter(cmd='/usr/bin/env "my python"').invocation,
            ["/usr/bin/env", "my python"],
        )

    def test_path_with_flag(self):
        self.assertEqual(
            Interpreter(cmd="/usr/local/bin/python3 -X utf8").invocation,
            ["/usr/local/bin/python3", "-X", "utf8"],
        )


if __name__ == "__main__":
    unittest.main()
