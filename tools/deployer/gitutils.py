from __future__ import annotations

from configparser import ConfigParser
from pathlib import Path


def load_gitmodules(path: Path) -> dict[str, str]:
    parser = ConfigParser()
    parser.read(path)
    mapping: dict[str, str] = {}
    for section in parser.sections():
        repo_path = parser.get(section, "path", fallback="")
        repo_url = parser.get(section, "url", fallback="")
        repo_name = repo_url.rstrip("/").split("/")[-1].removesuffix(".git") if repo_url else repo_path
        if repo_name:
            mapping[repo_name] = repo_path
    return mapping
