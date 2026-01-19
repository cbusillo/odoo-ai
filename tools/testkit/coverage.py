import logging
import subprocess
import xml.etree.ElementTree as ElementTree
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .docker_api import compose_env, get_script_runner_service
from .settings import TestSettings

_logger = logging.getLogger(__name__)

COVERAGE_DIRECTORY_NAME = "coverage"
EXCLUDED_ADDONS = {
    "openupgrade_scripts_custom",
    "test_web_tours",
}


@dataclass(frozen=True)
class CoverageRun:
    command_prefix: list[str]
    environment: dict[str, str]
    source_paths: list[str]
    data_directory: Path
    container_directory: str


def coverage_enabled(settings: TestSettings) -> bool:
    return bool(settings.coverage_py or settings.coverage_modules)


def _parse_modules(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []
    modules = [item.strip() for item in raw_value.split(",") if item.strip()]
    seen: set[str] = set()
    unique_modules: list[str] = []
    for module in modules:
        if module in seen:
            continue
        seen.add(module)
        unique_modules.append(module)
    return unique_modules


def _container_session_path(session_directory: Path) -> Path:
    return Path("/opt/project") / session_directory


def _coverage_source_paths(settings: TestSettings, modules_to_install: list[str]) -> list[str]:
    modules = _parse_modules(settings.coverage_modules)
    if not modules:
        modules = list(modules_to_install)
    source_paths: list[str] = []
    for module in modules:
        module_path = Path("addons") / module
        if not module_path.exists():
            _logger.info("Coverage skipping missing addon module: %s", module)
            continue
        source_paths.append(str(Path("/opt/project") / module_path))
    return sorted(set(source_paths))


def _discover_addons() -> dict[str, Path]:
    addons_root = Path("addons")
    addons: dict[str, Path] = {}
    if not addons_root.exists():
        return addons
    for addon_path in sorted(addons_root.iterdir()):
        if not addon_path.is_dir():
            continue
        if (addon_path / "__manifest__.py").exists():
            addons[addon_path.name] = addon_path
    return addons


def _addon_has_source(addon_path: Path) -> bool:
    for path in addon_path.rglob("*.py"):
        if "tests" in path.parts:
            continue
        if path.name in {"__init__.py", "__manifest__.py"}:
            continue
        return True
    return False


def _coverage_by_addon(coverage_xml: Path, addons: set[str]) -> dict[str, dict[str, int]]:
    totals: dict[str, dict[str, int]] = defaultdict(lambda: {"covered": 0, "total": 0})
    tree = ElementTree.parse(coverage_xml)
    root = tree.getroot()
    for class_node in root.findall(".//class"):
        filename = class_node.get("filename")
        if not filename:
            continue
        path = Path(filename)
        parts = path.parts
        if "addons" not in parts:
            continue
        addon_index = parts.index("addons") + 1
        if addon_index >= len(parts):
            continue
        addon_name = parts[addon_index]
        if addon_name not in addons:
            continue
        for line_node in class_node.findall("./lines/line"):
            if line_node.get("number") is None:
                continue
            totals[addon_name]["total"] += 1
            if int(line_node.get("hits", "0")) > 0:
                totals[addon_name]["covered"] += 1
    return totals


def _coverage_addon_summary(coverage_xml: Path) -> tuple[list[dict[str, object]], list[str]]:
    addons = _discover_addons()
    excluded: list[str] = []
    included: set[str] = set()
    for name, path in addons.items():
        if name in EXCLUDED_ADDONS:
            excluded.append(name)
            continue
        if not _addon_has_source(path):
            excluded.append(name)
            continue
        included.add(name)

    totals = _coverage_by_addon(coverage_xml, included)
    summary: list[dict[str, object]] = []
    for name in sorted(included):
        counts = totals.get(name, {"covered": 0, "total": 0})
        covered = counts["covered"]
        total = counts["total"]
        percent = round(covered / total * 100, 2) if total else None
        summary.append({"name": name, "covered": covered, "total": total, "percent": percent})
    return summary, sorted(excluded)


def prepare_coverage_directory(settings: TestSettings, session_directory: Path) -> Path | None:
    if not coverage_enabled(settings):
        return None
    coverage_directory = session_directory / COVERAGE_DIRECTORY_NAME
    coverage_directory.mkdir(parents=True, exist_ok=True)
    return coverage_directory


def build_coverage_run(
    settings: TestSettings,
    session_directory: Path,
    modules_to_install: list[str],
) -> CoverageRun | None:
    if not coverage_enabled(settings):
        return None
    source_paths = _coverage_source_paths(settings, modules_to_install)
    if not source_paths:
        return None
    coverage_directory = session_directory / COVERAGE_DIRECTORY_NAME
    coverage_directory.mkdir(parents=True, exist_ok=True)
    container_directory = _container_session_path(session_directory) / COVERAGE_DIRECTORY_NAME
    data_file = f"{container_directory}/.coverage"
    command_prefix = [
        "/venv/bin/python",
        "-m",
        "coverage",
        "run",
        "--parallel-mode",
        f"--source={','.join(source_paths)}",
        "--omit=*/tests/*",
    ]
    environment = {"COVERAGE_FILE": data_file}
    return CoverageRun(
        command_prefix=command_prefix,
        environment=environment,
        source_paths=source_paths,
        data_directory=coverage_directory,
        container_directory=str(container_directory),
    )


def _run_coverage_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, env=compose_env())


def finalize_coverage(settings: TestSettings, session_directory: Path) -> dict[str, object] | None:
    if not coverage_enabled(settings):
        return None
    coverage_directory = session_directory / COVERAGE_DIRECTORY_NAME
    if not coverage_directory.exists():
        return None
    data_files = list(coverage_directory.glob(".coverage.*"))
    if not data_files:
        return None

    container_directory = _container_session_path(session_directory) / COVERAGE_DIRECTORY_NAME
    data_file = f"{container_directory}/.coverage"
    script_runner_service = get_script_runner_service()
    host_session_dir = session_directory.resolve()
    container_session_dir = _container_session_path(session_directory)
    base_command = [
        "docker",
        "compose",
        "run",
        "--rm",
        "-v",
        f"{host_session_dir}:{container_session_dir}",
        script_runner_service,
    ]

    combine_result = _run_coverage_command(
        base_command
        + [
            "/venv/bin/python",
            "-m",
            "coverage",
            "combine",
            "--data-file",
            data_file,
            str(container_directory),
        ]
    )
    if combine_result.returncode != 0:
        _logger.warning("Coverage combine failed: %s", combine_result.stderr.strip())
        return None

    xml_result = _run_coverage_command(
        base_command
        + [
            "/venv/bin/python",
            "-m",
            "coverage",
            "xml",
            "--data-file",
            data_file,
            "-o",
            f"{container_directory}/coverage.xml",
        ]
    )
    if xml_result.returncode != 0:
        _logger.warning("Coverage XML report failed: %s", xml_result.stderr.strip())

    html_result = _run_coverage_command(
        base_command
        + [
            "/venv/bin/python",
            "-m",
            "coverage",
            "html",
            "--data-file",
            data_file,
            "-d",
            f"{container_directory}/html",
        ]
    )
    if html_result.returncode != 0:
        _logger.warning("Coverage HTML report failed: %s", html_result.stderr.strip())

    report_result = _run_coverage_command(
        base_command
        + [
            "/venv/bin/python",
            "-m",
            "coverage",
            "report",
            "--data-file",
            data_file,
            "--show-missing",
        ]
    )
    if report_result.returncode != 0:
        _logger.warning("Coverage text report failed: %s", report_result.stderr.strip())
    else:
        (coverage_directory / "coverage.txt").write_text(report_result.stdout)

    payload: dict[str, object] = {
        "directory": str(coverage_directory.resolve()),
        "data_file": str((coverage_directory / ".coverage").resolve()),
        "xml": str((coverage_directory / "coverage.xml").resolve()),
        "html": str((coverage_directory / "html").resolve()),
        "text": str((coverage_directory / "coverage.txt").resolve()),
    }
    coverage_xml = coverage_directory / "coverage.xml"
    if coverage_xml.exists():
        try:
            summary, excluded = _coverage_addon_summary(coverage_xml)
        except (ElementTree.ParseError, OSError, ValueError) as exc:
            _logger.warning("Coverage summary parse failed: %s", exc)
        else:
            payload["addons"] = summary
            if excluded:
                payload["excluded_addons"] = excluded

    return payload
