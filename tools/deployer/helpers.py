from pathlib import Path

from .command import run_process


def get_git_commit(repo_root: Path) -> str:
    result = run_process(["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True)
    output = (result.stdout or "").strip()
    if not output:
        raise RuntimeError("unable to determine git revision")
    return output


def get_git_remote_url(repo_root: Path, remote_name: str = "origin") -> str:
    result = run_process(["git", "remote", "get-url", remote_name], cwd=repo_root, capture_output=True, check=False)
    output = (result.stdout or "").strip()
    if result.returncode != 0 or not output:
        raise RuntimeError(f"remote '{remote_name}' url unavailable")
    return output
