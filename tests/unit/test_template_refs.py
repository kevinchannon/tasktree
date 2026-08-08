"""Unit tests for the generic template-reference walker."""

import unittest

from tasktree.template_refs import (
    TEMPLATE_PREFIXES,
    collect_template_refs,
    expand_variable_refs,
    rewrite_var_refs,
)


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

    def test_positional_input_reference_keeps_index(self):
        refs = collect_template_refs("cat {{ self.inputs.0 }} {{ self.inputs.1 }}")
        self.assertEqual(refs["self"], {"inputs.0", "inputs.1"})

    def test_positional_dep_output_reference_keeps_index(self):
        refs = collect_template_refs("{{ dep.build.outputs.0 }}")
        self.assertEqual(refs["dep"], {"build.outputs.0"})

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


class TestCollectFromSubtrees(unittest.TestCase):
    def test_walks_list_items(self):
        refs = collect_template_refs(["{{ var.a }}", "{{ var.b }}", 7])
        self.assertEqual(refs["var"], {"a", "b"})

    def test_walks_dict_values(self):
        refs = collect_template_refs({"cmd": "echo {{ var.a }}", "count": 3})
        self.assertEqual(refs["var"], {"a"})

    def test_walks_dict_keys(self):
        refs = collect_template_refs({"{{ var.key_name }}": "value"})
        self.assertEqual(refs["var"], {"key_name"})

    def test_walks_task_shaped_subtree(self):
        task = {
            "desc": "build {{ var.project }}",
            "deps": [{"compile": {"mode": "{{ arg.mode }}"}}],
            "inputs": ["src/**/*.py", {"config": "{{ env.CONFIG_PATH }}"}],
            "outputs": [{"bin": "dist/{{ var.version }}/app"}],
            "working_dir": "{{ tt.project_root }}/build",
            "cmd": "cp {{ dep.compile.outputs.obj }} {{ self.outputs.bin }}",
        }
        refs = collect_template_refs(task)
        self.assertEqual(refs["var"], {"project", "version"})
        self.assertEqual(refs["arg"], {"mode"})
        self.assertEqual(refs["env"], {"CONFIG_PATH"})
        self.assertEqual(refs["tt"], {"project_root"})
        self.assertEqual(refs["dep"], {"compile.outputs.obj"})
        self.assertEqual(refs["self"], {"outputs.bin"})

    def test_empty_containers_yield_nothing(self):
        for node in ({}, []):
            refs = collect_template_refs(node)
            self.assertEqual(refs["var"], set(), f"unexpected refs for {node!r}")


class TestExpandVariableRefs(unittest.TestCase):
    def test_no_variables_referenced_returns_same_refs(self):
        refs = collect_template_refs("echo {{ env.HOME }}")
        expanded = expand_variable_refs(refs, {"unused": "value"})
        self.assertEqual(expanded, refs)

    def test_definition_referencing_another_variable(self):
        refs = collect_template_refs("echo {{ var.greeting }}")
        variables = {"greeting": "{{ var.salutation }} world", "salutation": "hello"}
        expanded = expand_variable_refs(refs, variables)
        self.assertEqual(expanded["var"], {"greeting", "salutation"})

    def test_chain_of_definitions_reaches_fixpoint(self):
        refs = collect_template_refs("{{ var.a }}")
        variables = {"a": "{{ var.b }}", "b": "{{ var.c }}", "c": "leaf"}
        expanded = expand_variable_refs(refs, variables)
        self.assertEqual(expanded["var"], {"a", "b", "c"})

    def test_definition_referencing_env_var(self):
        refs = collect_template_refs("{{ var.a }}")
        variables = {"a": "{{ env.BUILD_NUMBER }}"}
        expanded = expand_variable_refs(refs, variables)
        self.assertEqual(expanded["env"], {"BUILD_NUMBER"})

    def test_undefined_variable_is_kept_but_not_chased(self):
        refs = collect_template_refs("{{ var.missing }}")
        expanded = expand_variable_refs(refs, {})
        self.assertEqual(expanded["var"], {"missing"})

    def test_unreferenced_definitions_are_not_chased(self):
        refs = collect_template_refs("{{ var.a }}")
        variables = {"a": "leaf", "other": "{{ var.b }}"}
        expanded = expand_variable_refs(refs, variables)
        self.assertEqual(expanded["var"], {"a"})

    def test_env_form_definition_adds_env_ref(self):
        refs = collect_template_refs("{{ var.a }}")
        variables = {"a": {"env": "BUILD_ENV", "default": "dev"}}
        expanded = expand_variable_refs(refs, variables)
        self.assertEqual(expanded["env"], {"BUILD_ENV"})

    def test_env_form_default_is_walked_for_templates(self):
        refs = collect_template_refs("{{ var.a }}")
        variables = {"a": {"env": "MODE", "default": "{{ var.fallback }}"}, "fallback": "x"}
        expanded = expand_variable_refs(refs, variables)
        self.assertEqual(expanded["var"], {"a", "fallback"})

    def test_eval_form_command_is_walked_for_templates(self):
        refs = collect_template_refs("{{ var.a }}")
        variables = {"a": {"eval": "git -C {{ tt.project_root }} rev-parse HEAD"}}
        expanded = expand_variable_refs(refs, variables)
        self.assertEqual(expanded["tt"], {"project_root"})

    def test_read_form_path_is_walked_for_templates(self):
        refs = collect_template_refs("{{ var.a }}")
        variables = {"a": {"read": "{{ env.CONFIG_DIR }}/version.txt"}}
        expanded = expand_variable_refs(refs, variables)
        self.assertEqual(expanded["env"], {"CONFIG_DIR"})

    def test_cyclic_definitions_terminate(self):
        refs = collect_template_refs("{{ var.a }}")
        variables = {"a": "{{ var.b }}", "b": "{{ var.a }}"}
        expanded = expand_variable_refs(refs, variables)
        self.assertEqual(expanded["var"], {"a", "b"})

    def test_self_referencing_definition_terminates(self):
        refs = collect_template_refs("{{ var.a }}")
        expanded = expand_variable_refs(refs, {"a": "{{ var.a }}"})
        self.assertEqual(expanded["var"], {"a"})

    def test_input_refs_are_not_mutated(self):
        refs = collect_template_refs("{{ var.a }}")
        expand_variable_refs(refs, {"a": "{{ var.b }}"})
        self.assertEqual(refs["var"], {"a"})


class TestRewriteVarRefs(unittest.TestCase):
    """
    Namespacing an imported file's variable references. Every var.* reference
    inside a template block must be rewritten wherever it sits in the
    expression, and nothing outside a block may be touched.
    """

    def test_whole_block_reference_rewritten(self):
        self.assertEqual(
            rewrite_var_refs("{{ var.greeting }}", "build"),
            "{{ var.build.greeting }}",
        )

    def test_reference_with_filter_rewritten(self):
        self.assertEqual(
            rewrite_var_refs("echo {{ var.greeting | upper }}", "build"),
            "echo {{ var.build.greeting | upper }}",
        )

    def test_both_branches_of_a_conditional_rewritten(self):
        self.assertEqual(
            rewrite_var_refs("{{ var.a if var.flag else var.b }}", "build"),
            "{{ var.build.a if var.build.flag else var.build.b }}",
        )

    def test_other_prefixes_in_the_same_block_left_alone(self):
        self.assertEqual(
            rewrite_var_refs("{{ var.a if tt.uid == 0 else var.b }}", "build"),
            "{{ var.build.a if tt.uid == 0 else var.build.b }}",
        )

    def test_multiple_blocks_in_one_string(self):
        self.assertEqual(
            rewrite_var_refs("{{ var.a }}-{{ var.b }}", "build"),
            "{{ var.build.a }}-{{ var.build.b }}",
        )

    def test_block_without_a_var_reference_unchanged(self):
        self.assertEqual(rewrite_var_refs("{{ arg.x }}", "build"), "{{ arg.x }}")

    def test_text_outside_a_block_is_never_touched(self):
        self.assertEqual(
            rewrite_var_refs("see var.greeting in the docs", "build"),
            "see var.greeting in the docs",
        )

    def test_dotted_reference_keeps_its_tail(self):
        self.assertEqual(
            rewrite_var_refs("{{ var.paths.root }}", "build"),
            "{{ var.build.paths.root }}",
        )

    def test_nested_namespace_chain(self):
        """Each import level namespaces again, building the full chain."""
        once = rewrite_var_refs("{{ var.greeting | upper }}", "inner")
        self.assertEqual(
            rewrite_var_refs(once, "outer"),
            "{{ var.outer.inner.greeting | upper }}",
        )

    def test_walks_dicts_and_lists(self):
        node = {
            "cmd": "echo {{ var.greeting | upper }}",
            "deps": [{"other": {"msg": "{{ var.greeting }}"}}],
        }
        self.assertEqual(
            rewrite_var_refs(node, "build"),
            {
                "cmd": "echo {{ var.build.greeting | upper }}",
                "deps": [{"other": {"msg": "{{ var.build.greeting }}"}}],
            },
        )

    def test_dict_keys_are_not_rewritten(self):
        """Keys are section and item names, never templates."""
        self.assertEqual(
            rewrite_var_refs({"{{ var.a }}": "{{ var.a }}"}, "build"),
            {"{{ var.a }}": "{{ var.build.a }}"},
        )

    def test_non_string_scalars_pass_through(self):
        self.assertEqual(rewrite_var_refs({"port": 8080}, "build"), {"port": 8080})


if __name__ == "__main__":
    unittest.main()
