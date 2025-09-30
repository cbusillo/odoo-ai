from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def load_env_values(path: Path, *, missing_ok: bool = False) -> Mapping[str, str]:
    if not path.exists():
        if missing_ok:
            return {}
        raise FileNotFoundError(path)

    values: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = _strip_quotes(value.strip())

        if " #" in value:
            value = value.split(" #", 1)[0].rstrip()

        values[key] = value

    return values
