from __future__ import annotations

from pathlib import Path


def discover_repo_root(start_directory: Path) -> Path:
    current_directory = start_directory.resolve()
    for candidate_directory in (current_directory, *current_directory.parents):
        if (candidate_directory / ".git").exists():
            return candidate_directory
    for candidate_directory in (current_directory, *current_directory.parents):
        if (candidate_directory / "pyproject.toml").exists():
            return candidate_directory
    return current_directory


def parse_env_lines(raw_lines: list[str]) -> dict[str, str]:
    parsed_values: dict[str, str] = {}
    for raw_line in raw_lines:
        stripped_line = raw_line.strip()
        if not stripped_line or stripped_line.startswith("#"):
            continue
        if stripped_line.startswith("export "):
            stripped_line = stripped_line[len("export ") :].strip()
        if "=" not in stripped_line:
            continue
        key_part, value_part = stripped_line.split("=", 1)
        environment_key = key_part.strip()
        environment_value = value_part.strip()
        is_quoted_value = (
            len(environment_value) >= 2
            and environment_value[0] == environment_value[-1]
            and environment_value[0] in {'"', "'"}
        )
        if is_quoted_value:
            environment_value = environment_value[1:-1]
        elif " #" in environment_value:
            environment_value = environment_value.split(" #", 1)[0].rstrip()
        parsed_values[environment_key] = environment_value
    return parsed_values


def parse_env_file(env_file_path: Path) -> dict[str, str]:
    return parse_env_lines(env_file_path.read_text(encoding="utf-8").splitlines())
