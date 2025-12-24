import hashlib
import json
from typing import Any, Optional


def hash_task(cmd: str, outputs: list[str], working_dir: str, args: list[str], env: str = "") -> str:
    data = {
        "cmd": cmd,
        "outputs": sorted(outputs),
        "working_dir": working_dir,
        "args": sorted(args),
        "env": env,
    }

    serialized = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()[:8]


def hash_args(args_dict: dict[str, Any]) -> str:
    serialized = json.dumps(args_dict, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()[:8]


def make_cache_key(task_hash: str, args_hash: Optional[str] = None) -> str:
    if args_hash:
        return f"{task_hash}__{args_hash}"
    return task_hash
