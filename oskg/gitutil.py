"""Git operations on a generated project.

Every phase commits, so an interrupted overnight build leaves a readable history
rather than a pile of untracked files, and a bad phase can be reverted without
losing the ones before it.

Every helper is best-effort: a build must not die because git is unavailable or
the working tree is in a state git dislikes. Failures are reported, never raised.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

__all__ = ["available", "init", "commit", "is_repo", "create_github_repo", "current_branch"]


def available() -> bool:
    return shutil.which("git") is not None


def _run(args: list[str], cwd: Path, timeout: int = 60) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            args, cwd=str(cwd), capture_output=True, text=True, timeout=timeout, check=False
        )
        return proc.returncode, (proc.stdout + proc.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)


def is_repo(path: Path | str) -> bool:
    return (Path(path) / ".git").exists()


def init(path: Path | str, *, branch: str = "main") -> tuple[bool, str]:
    path = Path(path)
    if not available():
        return False, "git not found on PATH"
    if is_repo(path):
        return True, "already a repository"
    code, out = _run(["git", "init", "-b", branch], path)
    return code == 0, out


def current_branch(path: Path | str) -> str:
    code, out = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], Path(path))
    return out if code == 0 else ""


def commit(path: Path | str, message: str, *, add_all: bool = True) -> tuple[bool, str]:
    """Stage and commit. A clean tree is success, not failure."""
    path = Path(path)
    if not available() or not is_repo(path):
        return False, "not a git repository"
    if add_all:
        code, out = _run(["git", "add", "-A"], path)
        if code != 0:
            return False, out
    code, out = _run(["git", "diff", "--cached", "--quiet"], path)
    if code == 0:
        return True, "nothing to commit"
    code, out = _run(["git", "commit", "-m", message], path)
    return code == 0, out


def create_github_repo(
    path: Path | str, name: str, *, private: bool = True, description: str = ""
) -> tuple[bool, str]:
    """Create a GitHub repo and push. Only ever called behind an explicit flag.

    An unattended build must not publish anything on its own — `oskg build`
    requires `--github` to reach this, and defaults to leaving the project local.
    """
    path = Path(path)
    if shutil.which("gh") is None:
        return False, "gh CLI not found on PATH"
    args = [
        "gh", "repo", "create", name,
        "--private" if private else "--public",
        "--source", ".", "--push", "--remote", "origin",
    ]
    if description:
        args += ["--description", description]
    code, out = _run(args, path, timeout=180)
    return code == 0, out
