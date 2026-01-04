from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .executor import OdooExecutor
from .settings import TestSettings


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


class TestPhase:
    def __init__(self, name: str, runner: Callable[..., int]) -> None:
        self.name = name
        self._runner = runner

    def run(self, *, session_dir: Path) -> PhaseOutcome:
        # This adapter is used only if keeping the old functions; the new
        # design provides concrete phase classes below.
        return_code = self._runner(session_dir=session_dir)
        # Reporter utilities live in session; keep best-effort here
        return PhaseOutcome(self.name, return_code, session_dir / self.name, None)


class UnitPhase:
    def __init__(self, modules: list[str], timeout: int) -> None:
        self.modules = modules
        self.timeout = timeout

    def run(self, session_dir: Path) -> PhaseOutcome:
        executor = OdooExecutor(session_dir, "unit")
        # When many modules are present, the session orchestrator shards them.
        # This single-phase runner emits one combined run when called directly.
        return_code = executor.run(
            test_tags="unit_test",
            db_name=f"{TestSettings().db_name}_test_unit",
            modules_to_install=self.modules,
            timeout=self.timeout,
        ).returncode
        return PhaseOutcome("unit", return_code, session_dir / "unit", None)


class JsPhase:
    def __init__(self, modules: list[str], timeout: int) -> None:
        self.modules = modules
        self.timeout = timeout

    def run(self, session_dir: Path) -> PhaseOutcome:
        executor = OdooExecutor(session_dir, "js")
        return_code = executor.run(
            test_tags="js_test",
            db_name=f"{TestSettings().db_name}_test_js",
            modules_to_install=self.modules,
            timeout=self.timeout,
            is_js_test=True,
        ).returncode
        return PhaseOutcome("js", return_code, session_dir / "js", None)


class IntegrationPhase:
    def __init__(self, modules: list[str], timeout: int) -> None:
        self.modules = modules
        self.timeout = timeout

    def run(self, session_dir: Path) -> PhaseOutcome:
        executor = OdooExecutor(session_dir, "integration")
        return_code = executor.run(
            test_tags="integration_test",
            db_name=f"{TestSettings().db_name}_test_integration",
            modules_to_install=self.modules,
            timeout=self.timeout,
            use_production_clone=True,
        ).returncode
        return PhaseOutcome("integration", return_code, session_dir / "integration", None)


class TourPhase:
    def __init__(self, modules: list[str], timeout: int) -> None:
        self.modules = modules
        self.timeout = timeout

    def run(self, session_dir: Path) -> PhaseOutcome:
        executor = OdooExecutor(session_dir, "tour")
        return_code = executor.run(
            test_tags="tour_test,-js_test",
            db_name=f"{TestSettings().db_name}_test_tour",
            modules_to_install=self.modules,
            timeout=self.timeout,
            use_production_clone=True,
            is_tour_test=True,
        ).returncode
        return PhaseOutcome("tour", return_code, session_dir / "tour", None)
