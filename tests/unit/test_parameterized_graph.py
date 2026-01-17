import unittest
from pathlib import Path
from tasktree.parser import Recipe, Task
from tasktree.graph import resolve_execution_order, TaskNode


class TestParameterizedGraphConstruction(unittest.TestCase):
    """
    Test graph construction with parameterized dependencies.
    @athena: 561fe41e63fc
    """

    def setUp(self):
        """
        Create a test recipe with parameterized tasks.
        @athena: 23b0c3761e31
        """
        self.tasks = {
            "process": Task(
                name="process",
                cmd="echo mode={{arg.mode}}",
                args=["mode"],
                deps=[],
            ),
            "multi_invoke": Task(
                name="multi_invoke",
                cmd="echo done",
                deps=[
                    {"process": ["debug"]},
                    {"process": ["release"]},
                ],
            ),
            "consumer": Task(
                name="consumer",
                cmd="echo consuming",
                deps=[{"process": ["production"]}],
            ),
        }
        self.recipe = Recipe(
            tasks=self.tasks,
            project_root=Path("/test"),
            recipe_path=Path("/test/tasktree.yaml"),
        )

    def test_simple_dependency_without_args(self):
        """
        Test simple dependency without arguments.
        @athena: 6616953ee055
        """
        tasks = {
            "build": Task(name="build", cmd="make", deps=[]),
            "test": Task(name="test", cmd="test", deps=["build"]),
        }
        recipe = Recipe(
            tasks=tasks,
            project_root=Path("/test"),
            recipe_path=Path("/test/tasktree.yaml"),
        )

        order = resolve_execution_order(recipe, "test")
        self.assertEqual(len(order), 2)
        self.assertEqual(order[0], ("build", None))
        self.assertEqual(order[1], ("test", None))

    def test_dependency_with_positional_args(self):
        """
        Test dependency with positional arguments.
        @athena: 69a6e5a5ff76
        """
        order = resolve_execution_order(self.recipe, "consumer")
        self.assertEqual(len(order), 2)
        self.assertEqual(order[0][0], "process")
        self.assertEqual(order[0][1], {"mode": "production"})
        self.assertEqual(order[1][0], "consumer")

    def test_same_task_different_args_creates_multiple_nodes(self):
        """
        Test that same task with different args creates separate nodes.
        @athena: a17b3d177016
        """
        order = resolve_execution_order(self.recipe, "multi_invoke")

        # Should have 3 nodes: process(debug), process(release), multi_invoke
        self.assertEqual(len(order), 3)

        # Extract the process invocations
        process_invocations = [
            (name, args) for name, args in order if name == "process"
        ]
        self.assertEqual(len(process_invocations), 2)

        # Check that both invocations are present
        modes = {args["mode"] for _, args in process_invocations}
        self.assertEqual(modes, {"debug", "release"})

    def test_same_task_same_args_creates_single_node(self):
        """
        Test that same task with same args (after normalization) creates single node.
        @athena: e34cd0df2ad7
        """
        tasks = {
            "process": Task(
                name="process",
                cmd="echo mode={{arg.mode}}",
                args=[{"mode": {"default": "debug"}}],
                deps=[],
            ),
            "consumer1": Task(
                name="consumer1",
                cmd="echo c1",
                deps=[{"process": ["debug"]}],
            ),
            "consumer2": Task(
                name="consumer2",
                cmd="echo c2",
                deps=[{"process": {"mode": "debug"}}],
            ),
            "final": Task(
                name="final",
                cmd="echo done",
                deps=["consumer1", "consumer2"],
            ),
        }
        recipe = Recipe(
            tasks=tasks,
            project_root=Path("/test"),
            recipe_path=Path("/test/tasktree.yaml"),
        )

        order = resolve_execution_order(recipe, "final")

        # Should only have 4 nodes (process appears once, despite two consumers)
        self.assertEqual(len(order), 4)

        # Count process invocations
        process_count = sum(1 for name, _ in order if name == "process")
        self.assertEqual(process_count, 1)


class TestTaskNodeHashing(unittest.TestCase):
    """
    Test TaskNode hashing and equality.
    @athena: 5dab0fe1fcd5
    """

    def test_nodes_with_same_task_same_args_are_equal(self):
        """
        Test that nodes with same task and args are equal.
        @athena: cf28cc06d683
        """
        node1 = TaskNode("build", {"mode": "debug"})
        node2 = TaskNode("build", {"mode": "debug"})
        self.assertEqual(node1, node2)
        self.assertEqual(hash(node1), hash(node2))

    def test_nodes_with_same_task_different_args_are_not_equal(self):
        """
        Test that nodes with same task but different args are not equal.
        @athena: 43a3c3270cad
        """
        node1 = TaskNode("build", {"mode": "debug"})
        node2 = TaskNode("build", {"mode": "release"})
        self.assertNotEqual(node1, node2)
        self.assertNotEqual(hash(node1), hash(node2))

    def test_nodes_with_different_tasks_are_not_equal(self):
        """
        Test that nodes with different tasks are not equal.
        @athena: 679ff466192f
        """
        node1 = TaskNode("build", {})
        node2 = TaskNode("test", {})
        self.assertNotEqual(node1, node2)
        self.assertNotEqual(hash(node1), hash(node2))

    def test_node_with_no_args_equals_node_with_empty_dict(self):
        """
        Test that None args equals empty dict.
        @athena: a3beab3a4f15
        """
        node1 = TaskNode("build", None)
        node2 = TaskNode("build", {})
        self.assertEqual(node1, node2)
        self.assertEqual(hash(node1), hash(node2))


if __name__ == "__main__":
    unittest.main()
