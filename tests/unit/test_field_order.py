"""Tests for ordering a task's references to its own inputs and outputs."""

import unittest

from tasktree.field_order import render_own_patterns


def record_order(seen: list):
    """A render that notes what it was asked for, and resolves trivially."""

    def render(pattern: str, resolved_so_far: dict) -> str:
        seen.append(pattern)
        return pattern.replace("{{ self.inputs.src }}", "a.txt")

    return render


class TestRenderOwnPatterns(unittest.TestCase):
    def test_named_and_anonymous_patterns_keep_declaration_order(self):
        result = render_own_patterns(
            "build",
            ["one", {"named": "two"}, "three"],
            [],
            lambda pattern, resolved: pattern.upper(),
        )

        self.assertEqual(result["inputs_indexed"], ["ONE", "TWO", "THREE"])
        self.assertEqual(result["inputs_named"], {"named": "TWO"})
        self.assertEqual(result["outputs_indexed"], [])

    def test_a_pattern_renders_after_the_one_it_names(self):
        seen = []
        render_own_patterns(
            "build",
            [{"backup": "{{ self.inputs.src }}.bak"}, {"src": "a.txt"}],
            [],
            record_order(seen),
        )

        self.assertEqual(seen, ["a.txt", "{{ self.inputs.src }}.bak"])

    def test_the_namespace_holds_what_resolved_before(self):
        """
        What each render receives is the point: a pattern can only see the
        ones already resolved, which is what the ordering guarantees.
        """
        snapshots = []

        def render(pattern, resolved_so_far):
            snapshots.append(dict(resolved_so_far["inputs_named"]))
            return pattern

        render_own_patterns(
            "build",
            [{"backup": "{{ self.inputs.src }}.bak"}, {"src": "a.txt"}],
            [],
            render,
        )

        self.assertEqual(snapshots[0], {})
        self.assertEqual(snapshots[1], {"src": "a.txt"})

    def test_an_output_may_name_an_input(self):
        result = render_own_patterns(
            "build",
            [{"src": "a.txt"}],
            [{"log": "{{ self.inputs.src }}.log"}],
            record_order([]),
        )

        self.assertEqual(result["outputs_named"], {"log": "a.txt.log"})

    def test_a_positional_reference_counts_every_path(self):
        seen = []
        render_own_patterns(
            "build",
            ["{{ self.inputs.1 }}", "second"],
            [],
            record_order(seen),
        )

        self.assertEqual(seen, ["second", "{{ self.inputs.1 }}"])

    def test_a_loop_is_reported_with_both_ends(self):
        with self.assertRaises(ValueError) as cm:
            render_own_patterns(
                "build",
                [{"a": "{{ self.inputs.b }}"}, {"b": "{{ self.inputs.a }}"}],
                [],
                record_order([]),
            )

        message = str(cm.exception)
        self.assertIn("build", message)
        self.assertIn("loop", message)
        self.assertIn("self.inputs.a", message)
        self.assertIn("self.inputs.b", message)

    def test_a_reference_to_something_absent_is_left_to_the_render(self):
        """
        No edge is made for it, so the render is reached and reports it with
        the names that do exist -- a better error than this module could give.
        """
        def render(pattern, resolved_so_far):
            if "nope" in pattern:
                raise ValueError("no input named 'nope'")
            return pattern

        with self.assertRaises(ValueError) as cm:
            render_own_patterns("build", ["{{ self.inputs.nope }}"], [], render)

        self.assertIn("no input named", str(cm.exception))

    def test_patterns_that_are_not_strings_pass_through(self):
        result = render_own_patterns("build", [], [], record_order([]))

        self.assertEqual(result["inputs_indexed"], [])


if __name__ == "__main__":
    unittest.main()
