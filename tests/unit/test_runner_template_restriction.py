"""
Behaviour tests: per-task template references are rejected in runner and
interpreter definitions at parse time.

Runners/interpreters are shared across tasks and render once, before any task
runs, so arg.*, dep.*, self.* and per-task tt builtins may not appear in them
(schema-validation-pipeline plan, decision 4).

This file is deliberately self-contained (it imports only parse_recipe) so it
can be copied into the v1.3.2 reference worktree for the reference gate. The
rejection tests FAIL there by design: v1.3.2 silently accepted these recipes.
That divergence is recorded in the plan's expected-divergences list.
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tasktree.parser import parse_recipe


def _parse(recipe_yaml: str) -> None:
    """Parse a recipe that is valid apart from the templates under test.

    A real Dockerfile is created so the recipes are accepted by versions
    without the restriction (the parser validates dockerfile paths on disk).
    """
    with TemporaryDirectory() as tmpdir:
        docker_dir = Path(tmpdir) / "docker"
        docker_dir.mkdir()
        (docker_dir / "Dockerfile").write_text("FROM alpine\n")
        recipe_path = Path(tmpdir) / "tasktree.yaml"
        recipe_path.write_text(recipe_yaml)
        parse_recipe(recipe_path)


class TestPerTaskRefsRejectedInRunners(unittest.TestCase):
    def test_arg_in_runner_volumes_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            _parse("""
runners:
  build-env:
    type: containerised
    engine: docker
    dockerfile: docker/Dockerfile
    volumes:
      - "{{ arg.mount }}:/data"
tasks:
  build:
    runner: build-env
    cmd: echo build
""")
        message = str(ctx.exception)
        self.assertIn("Runner 'build-env'", message)
        self.assertIn("arg.mount", message)
        self.assertIn("shared across tasks", message)

    def test_dep_and_self_in_runner_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            _parse("""
runners:
  build-env:
    type: containerised
    engine: docker
    dockerfile: docker/Dockerfile
    volumes:
      - "{{ dep.gen.outputs.data }}:/data"
    env_vars:
      SRC: "{{ self.inputs.src }}"
tasks:
  build:
    runner: build-env
    cmd: echo build
""")
        message = str(ctx.exception)
        self.assertIn("dep.gen.outputs.data", message)
        self.assertIn("self.inputs.src", message)

    def test_per_task_tt_builtin_in_runner_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            _parse("""
runners:
  build-env:
    type: containerised
    engine: docker
    dockerfile: docker/Dockerfile
    env_vars:
      TASK: "{{ tt.task_name }}"
tasks:
  build:
    runner: build-env
    cmd: echo build
""")
        self.assertIn("tt.task_name", str(ctx.exception))

    def test_arg_in_inline_task_runner_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            _parse("""
tasks:
  build:
    runner:
      type: containerised
      engine: docker
      dockerfile: docker/Dockerfile
      volumes:
        - "{{ arg.mount }}:/data"
    cmd: echo build
""")
        self.assertIn("arg.mount", str(ctx.exception))

    def test_allowed_refs_in_runner_accepted(self):
        with TemporaryDirectory() as tmpdir:
            docker_dir = Path(tmpdir) / "docker"
            docker_dir.mkdir()
            (docker_dir / "Dockerfile").write_text("FROM alpine\n")
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text("""
variables:
  data_dir: /srv/data
runners:
  build-env:
    type: containerised
    engine: docker
    dockerfile: docker/Dockerfile
    volumes:
      - "{{ tt.project_root }}:/workspace"
      - "{{ var.data_dir }}:/data"
    env_vars:
      HOME_DIR: "{{ tt.user_home }}"
      MODE: "{{ env.MODE }}"
tasks:
  build:
    runner: build-env
    cmd: echo build
""")
            parse_recipe(recipe_path)  # Must not raise


if __name__ == "__main__":
    unittest.main()
