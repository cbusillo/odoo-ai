from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)


class EventStream:
    def __init__(self, path: Path, *, echo: bool = False) -> None:
        self.path = path
        self.echo = echo
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.path.touch()
        except OSError as exc:
            _logger.debug("events: failed to touch %s (%s)", path, exc)

    def emit(self, event: str, **payload: Any) -> None:
        rec = {"ts": time.time(), "event": event, **payload}
        line = json.dumps(rec)
        try:
            with self.path.open("a", buffering=1) as f:
                f.write(line + "\n")
        except OSError as exc:
            _logger.debug("events: failed to write %s (%s)", self.path, exc)
        if self.echo:
            try:
                print(line)
            except OSError as exc:
                _logger.debug("events: failed to echo (%s)", exc)
