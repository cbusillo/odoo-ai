from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any


def enqueue(destination: Path, payload: dict[str, Any]) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    identifier = f"{int(time.time())}-{uuid.uuid4().hex}.json"
    target = destination / identifier
    temp_file = target.with_suffix(".tmp")
    temp_file.write_text(json.dumps(payload, separators=(",", ":")))
    temp_file.replace(target)
    return target


def iter_queue(queue_dir: Path) -> list[Path]:
    if not queue_dir.exists():
        return []
    return sorted(path for path in queue_dir.iterdir() if path.suffix == ".json")


def load_payload(task_file: Path) -> dict[str, Any]:
    return json.loads(task_file.read_text())


def remove_task(task_file: Path) -> None:
    task_file.unlink(missing_ok=True)
