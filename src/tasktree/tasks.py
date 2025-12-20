import subprocess

from typing import Dict


def run(task_tree: Dict) -> None:
    for _, params in task_tree.items():
        _ = subprocess.run(params["cmd"], shell=True)
