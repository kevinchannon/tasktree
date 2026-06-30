"""Unit tests for parsing interpreter definitions and references."""

import unittest

from tasktree.interpreter import Interpreter
from tasktree.parser import (
    parse_interpreter_spec,
    _parse_interpreters_section,
    _parse_inline_interpreter,
)


class TestParseInlineInterpreter(unittest.TestCase):
    """Tests for inline interpreter definitions: {cmd, ext?, preamble?}."""

    def test_cmd_only(self):
        interp = _parse_inline_interpreter({"cmd": "bash"}, "ctx")
        self.assertEqual(interp, Interpreter(cmd="bash"))

    def test_string_shorthand(self):
        interp = _parse_inline_interpreter("bash", "ctx")
        self.assertEqual(interp, Interpreter(cmd="bash"))

    def test_empty_string_shorthand_raises(self):
        with self.assertRaises(ValueError):
            _parse_inline_interpreter("", "ctx")

    def test_cmd_ext_preamble(self):
        interp = _parse_inline_interpreter(
            {"cmd": "cmd.exe", "ext": ".bat", "preamble": "@echo off"}, "ctx"
        )
        self.assertEqual(interp.cmd, "cmd.exe")
        self.assertEqual(interp.ext, ".bat")
        self.assertEqual(interp.preamble, "@echo off")

    def test_missing_cmd_raises(self):
        with self.assertRaises(ValueError):
            _parse_inline_interpreter({"ext": ".sh"}, "ctx")

    def test_unknown_field_raises(self):
        with self.assertRaises(ValueError) as ctx:
            _parse_inline_interpreter({"cmd": "sh", "bogus": 1}, "ctx")
        self.assertIn("bogus", str(ctx.exception))

    def test_non_string_field_raises(self):
        with self.assertRaises(ValueError):
            _parse_inline_interpreter({"cmd": ["sh"]}, "ctx")

    def test_bad_ext_raises(self):
        with self.assertRaises(ValueError) as ctx:
            _parse_inline_interpreter({"cmd": "sh", "ext": "sh"}, "ctx")
        self.assertIn("dot", str(ctx.exception))


class TestParseInterpretersSection(unittest.TestCase):
    """Tests for the top-level 'interpreters' section."""

    def test_empty_when_absent(self):
        self.assertEqual(_parse_interpreters_section({}), {})

    def test_parses_named_interpreters(self):
        section = {
            "interpreters": {
                "py": {"cmd": "python3", "ext": ".py"},
                "sh": {"cmd": "bash"},
            }
        }
        result = _parse_interpreters_section(section)
        self.assertEqual(result["py"], Interpreter(cmd="python3", ext=".py"))
        self.assertEqual(result["sh"], Interpreter(cmd="bash"))

    def test_use_inside_section_raises(self):
        section = {"interpreters": {"x": {"use": "y"}}}
        with self.assertRaises(ValueError) as ctx:
            _parse_interpreters_section(section)
        self.assertIn("use", str(ctx.exception))

    def test_non_mapping_section_raises(self):
        with self.assertRaises(ValueError):
            _parse_interpreters_section({"interpreters": ["nope"]})


class TestParseInterpreterSpec(unittest.TestCase):
    """Tests for a runner's 'interpreter' field (inline or {use: name})."""

    def setUp(self):
        self.named = {"sh": Interpreter(cmd="bash"), "py": Interpreter(cmd="python3")}

    def test_inline(self):
        interp = parse_interpreter_spec({"cmd": "zsh"}, "Runner 'r'", self.named)
        self.assertEqual(interp, Interpreter(cmd="zsh"))

    def test_use_reference(self):
        interp = parse_interpreter_spec({"use": "py"}, "Runner 'r'", self.named)
        self.assertEqual(interp, Interpreter(cmd="python3"))

    def test_unknown_use_raises(self):
        with self.assertRaises(ValueError) as ctx:
            parse_interpreter_spec({"use": "nope"}, "Runner 'r'", self.named)
        self.assertIn("nope", str(ctx.exception))

    def test_use_with_extra_keys_raises(self):
        with self.assertRaises(ValueError):
            parse_interpreter_spec(
                {"use": "py", "cmd": "x"}, "Runner 'r'", self.named
            )

    def test_non_mapping_raises(self):
        with self.assertRaises(ValueError):
            parse_interpreter_spec("bash", "Runner 'r'", self.named)


if __name__ == "__main__":
    unittest.main()
