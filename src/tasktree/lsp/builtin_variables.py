"""Built-in variable definitions for tasktree LSP completion."""

# Built-in variables available in tasktree templates
# These correspond to the variables defined in src/tasktree/executor.py
BUILTIN_VARIABLES = [
    "project_root",  # Absolute path to project root
    "recipe_dir",  # Absolute path to directory containing the recipe file
    "task_name",  # Name of currently executing task
    "working_dir",  # Absolute path to task's effective working directory
    "timestamp",  # ISO8601 timestamp when task started execution
    "timestamp_unix",  # Unix epoch timestamp when task started
    "user_home",  # Current user's home directory (cross-platform)
    "user_name",  # Current username
]
