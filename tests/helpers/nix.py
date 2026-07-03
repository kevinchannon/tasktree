import subprocess


def is_nix_available() -> bool:
    """Check if Nix is installed with flakes usable.

    Uses the same functional probe as tasktree.nix: 'nix eval' itself needs
    nix-command, and builtins.getFlake only exists when flakes are usable
    (feature lists are unreliable - Determinate Nix stabilises the features
    and drops them from experimental-features entirely).

    Returns:
        True if nix is present and flakes work
    """
    try:
        result = subprocess.run(
            ["nix", "eval", "--expr", "builtins ? getFlake"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
    ):
        return False
