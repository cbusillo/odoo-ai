from dataclasses import dataclass
from pathlib import Path


@dataclass
class PhaseOutcome:
    name: str
    return_code: int | None
    log_dir: Path | None
    summary: dict | None

    @property
    def ok(self) -> bool | None:
        if self.return_code is None:
            return None
        return self.return_code == 0
