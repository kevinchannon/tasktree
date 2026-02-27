# SPDX-License-Identifier: MIT
"""Cross-platform shell command generators for use in tests.

These functions return shell command strings suitable for use in tasktree
YAML ``cmd:`` and ``eval:`` fields.  They currently implement Linux/macOS
commands only; Windows implementations will be added in a subsequent pass.

Usage example::

    from helpers.crossplatform import crossplatform_print, crossplatform_write_file

    recipe_yaml = f\"\"\"
tasks:
  greet:
    cmd: {crossplatform_print("hello")}
  build:
    outputs: [build.txt]
    cmd: {crossplatform_write_file("build.txt", "Building...")}
\"\"\"
"""


def crossplatform_print(text: str) -> str:
    """Return a shell command that prints *text* to stdout.

    Linux/macOS: ``echo <text>``
    Windows (TODO): TBD
    """
    return f"echo {text}"


def crossplatform_noop() -> str:
    """Return a shell command that succeeds without doing anything.

    Linux/macOS: ``true``
    Windows (TODO): TBD
    """
    return "true"


def crossplatform_fail() -> str:
    """Return a shell command that always exits with a non-zero status.

    Linux/macOS: ``false``
    Windows (TODO): TBD
    """
    return "false"


def crossplatform_write_file(path: str, content: str) -> str:
    """Return a shell command that writes *content* to *path* (overwrite).

    Linux/macOS: ``echo <content> > <path>``
    Windows (TODO): TBD
    """
    return f"echo {content} > {path}"


def crossplatform_append_file(path: str, content: str) -> str:
    """Return a shell command that appends *content* to *path*.

    Linux/macOS: ``echo <content> >> <path>``
    Windows (TODO): TBD
    """
    return f"echo {content} >> {path}"


def crossplatform_copy_file(src: str, dst: str) -> str:
    """Return a shell command that copies a *single* file *src* to *dst*.

    Note: *src* must resolve to a single file path, not a glob that can
    match multiple files.  Use ``crossplatform_concat_files()`` (TODO) for
    multi-file concatenation.

    Linux/macOS: ``cp <src> <dst>``
    Windows (TODO): TBD
    """
    return f"cp {src} {dst}"


def crossplatform_make_dir(path: str) -> str:
    """Return a shell command that creates *path* including any missing parents.

    Linux/macOS: ``mkdir -p <path>``
    Windows (TODO): TBD
    """
    return f"mkdir -p {path}"


def crossplatform_get_cwd() -> str:
    """Return a shell command that prints the current working directory.

    Linux/macOS: ``pwd``
    Windows (TODO): TBD
    """
    return "pwd"


def crossplatform_list_files() -> str:
    """Return a shell command that lists files in the current directory.

    Linux/macOS: ``ls``
    Windows (TODO): TBD
    """
    return "ls"
