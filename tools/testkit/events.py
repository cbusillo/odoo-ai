from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class EventStream:
    def __init__(self, path: Path, *, echo: bool = False) -> None:
        self.path = path
        self.echo = echo
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Touch file
        try:
            self.path.touch()
        except Exception:
            pass

    def emit(self, event: str, **payload: Any) -> None:
        rec = {"ts": time.time(), "event": event, **payload}
        line = json.dumps(rec)
        try:
            with self.path.open("a", buffering=1) as f:
                f.write(line + "\n")
        except Exception:
            pass
        if self.echo:
            try:
                print(line)
            except Exception:
                pass
