"""Unit tests for the generic template-reference walker."""

import unittest

from tasktree.template_refs import TEMPLATE_PREFIXES, collect_template_refs


class TestCollectFromStrings(unittest.TestCase):
    def test_returns_entry_for_every_prefix(self):
        refs = collect_template_refs("no templates here")
        self.assertEqual(set(refs.keys()), set(TEMPLATE_PREFIXES))
        for prefix in TEMPLATE_PREFIXES:
            self.assertEqual(refs[prefix], set())

    def test_extracts_single_var_reference(self):
        refs = collect_template_refs("echo {{ var.version }}")
        self.assertEqual(refs["var"], {"version"})

    def test_extracts_all_prefixes(self):
        text = (
            "{{ var.a }} {{ arg.count }} {{ env.PYTHONPATH }} "
            "{{ tt.project_root }} {{ dep.build.outputs.bin }} "
            "{{ self.inputs.src }}"
        )
        refs = collect_template_refs(text)
        self.assertEqual(refs["var"], {"a"})
        self.assertEqual(refs["arg"], {"count"})
        self.assertEqual(refs["env"], {"PYTHONPATH"})
        self.assertEqual(refs["tt"], {"project_root"})
        self.assertEqual(refs["dep"], {"build.outputs.bin"})
        self.assertEqual(refs["self"], {"inputs.src"})

    def test_multiple_references_in_one_block(self):
        refs = collect_template_refs("{{ var.a + var.b }}")
        self.assertEqual(refs["var"], {"a", "b"})

    def test_jinja_conditional_expression(self):
        refs = collect_template_refs("{{ var.a if arg.flag else var.b }}")
        self.assertEqual(refs["var"], {"a", "b"})
        self.assertEqual(refs["arg"], {"flag"})

    def test_namespaced_variable_name(self):
        refs = collect_template_refs("{{ var.build.version }}")
        self.assertEqual(refs["var"], {"build.version"})

    def test_whitespace_around_prefix_dot(self):
        refs = collect_template_refs("{{ var . spaced }}")
        self.assertEqual(refs["var"], {"spaced"})

    def test_prefix_outside_template_block_is_ignored(self):
        refs = collect_template_refs("echo var.not_a_template")
        self.assertEqual(refs["var"], set())

    def test_prefix_as_suffix_of_longer_word_is_ignored(self):
        refs = collect_template_refs("{{ sidebar.width }} {{ my_env.HOME }}")
        self.assertEqual(refs["var"], set())
        self.assertEqual(refs["env"], set())

    def test_non_string_scalars_yield_nothing(self):
        for node in (None, 42, 3.14, True):
            refs = collect_template_refs(node)
            self.assertEqual(refs["var"], set(), f"unexpected refs for {node!r}")


if __name__ == "__main__":
    unittest.main()
