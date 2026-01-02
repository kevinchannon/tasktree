import hashlib
import json
from typing import Any, Optional


def hash_task(cmd: str, outputs: list[str], working_dir: str, args: list[str | dict[str, Any]], env: str = "") -> str:
    data = {
        "cmd": cmd,
        "outputs": sorted(outputs),
        "working_dir": working_dir,
        "args": args,
        "env": env,
    }

    serialized = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()[:8]


def hash_args(args_dict: dict[str, Any]) -> str:
    serialized = json.dumps(args_dict, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()[:8]


def hash_environment_definition(env) -> str:
    """Hash environment definition fields that affect task execution.

    Args:
        env: Environment to hash

    Returns:
        16-character hash of environment definition
    """
    # Import inside function to avoid circular dependency
    from tasktree.parser import Environment

    data = {
        "shell": env.shell,
        "args": sorted(env.args),  # Sort for determinism
        "preamble": env.preamble,
        "dockerfile": env.dockerfile,
        "context": env.context,
        "volumes": sorted(env.volumes),
        "ports": sorted(env.ports),
        "env_vars": dict(sorted(env.env_vars.items())),
        "working_dir": env.working_dir,
    }
    serialized = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()[:16]


def make_cache_key(task_hash: str, args_hash: Optional[str] = None) -> str:
    if args_hash:
        return f"{task_hash}__{args_hash}"
    return task_hash
