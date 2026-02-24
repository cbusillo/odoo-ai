from __future__ import annotations

import json
import statistics
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click


@dataclass(frozen=True)
class LocalBenchmarkSample:
    index: int
    duration_seconds: float
    return_code: int


@dataclass(frozen=True)
class WorkflowRunSample:
    run_number: int
    status: str
    conclusion: str
    branch: str
    head_sha: str
    html_url: str
    duration_seconds: float
    run_started_at: str
    updated_at: str


def _run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def _parse_iso8601(raw_timestamp: str) -> datetime:
    normalized = raw_timestamp.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    sorted_values = sorted(values)
    position = (len(sorted_values) - 1) * percentile_value
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)
    if lower_index == upper_index:
        return sorted_values[lower_index]
    weight = position - lower_index
    lower_value = sorted_values[lower_index]
    upper_value = sorted_values[upper_index]
    return lower_value + (upper_value - lower_value) * weight


def _summarize(values: list[float]) -> dict[str, float]:
    if not values:
        return {
            "count": 0,
            "min_seconds": 0.0,
            "max_seconds": 0.0,
            "mean_seconds": 0.0,
            "p50_seconds": 0.0,
            "p95_seconds": 0.0,
        }
    return {
        "count": float(len(values)),
        "min_seconds": min(values),
        "max_seconds": max(values),
        "mean_seconds": statistics.fmean(values),
        "p50_seconds": _percentile(values, 0.50),
        "p95_seconds": _percentile(values, 0.95),
    }


def _discover_repository_slug(repo_root: Path) -> str:
    origin_url_output = _run_command(["git", "-C", str(repo_root), "remote", "get-url", "origin"])
    if origin_url_output.returncode != 0:
        raise click.ClickException("Unable to resolve git origin URL for repository slug detection.")
    origin_url = origin_url_output.stdout.strip()
    if origin_url.endswith(".git"):
        origin_url = origin_url[:-4]
    if origin_url.startswith("git@github.com:"):
        return origin_url.removeprefix("git@github.com:")
    marker = "github.com/"
    if marker in origin_url:
        return origin_url.split(marker, 1)[1]
    raise click.ClickException(f"Unsupported git origin URL format: {origin_url}")


def _benchmark_local_gate(
    *,
    stack_name: str,
    sample_count: int,
    extra_arguments: tuple[str, ...],
) -> tuple[list[LocalBenchmarkSample], str | None]:
    samples: list[LocalBenchmarkSample] = []
    for sample_index in range(1, sample_count + 1):
        command = ["uv", "run", "test", "run", "--json", "--stack", stack_name, *extra_arguments]
        started_at = time.perf_counter()
        command_result = _run_command(command)
        duration_seconds = time.perf_counter() - started_at
        samples.append(
            LocalBenchmarkSample(
                index=sample_index,
                duration_seconds=duration_seconds,
                return_code=command_result.returncode,
            )
        )
        if command_result.returncode != 0:
            return samples, (
                f"Local gate benchmark sample {sample_index} failed with exit code {command_result.returncode}."
            )
    return samples, None


def _fetch_workflow_runs(
    *,
    repository_slug: str,
    workflow: str,
    branch: str,
    sample_count: int,
) -> tuple[list[WorkflowRunSample], str | None]:
    command = [
        "gh",
        "api",
        f"repos/{repository_slug}/actions/workflows/{workflow}/runs",
        "--field",
        f"branch={branch}",
        "--field",
        "status=completed",
        "--field",
        f"per_page={sample_count}",
    ]
    command_result = _run_command(command)
    if command_result.returncode != 0:
        stderr_message = command_result.stderr.strip()
        return [], f"GitHub workflow fetch failed: {stderr_message}"

    try:
        payload = json.loads(command_result.stdout)
    except json.JSONDecodeError as error:
        return [], f"GitHub workflow payload was not valid JSON: {error}"

    workflow_runs_payload = payload.get("workflow_runs")
    if not isinstance(workflow_runs_payload, list):
        return [], "GitHub workflow payload missing workflow_runs list."

    samples: list[WorkflowRunSample] = []
    for workflow_run in workflow_runs_payload:
        if not isinstance(workflow_run, dict):
            continue
        run_started_at = str(workflow_run.get("run_started_at") or "")
        updated_at = str(workflow_run.get("updated_at") or "")
        if not run_started_at or not updated_at:
            continue
        try:
            started_datetime = _parse_iso8601(run_started_at)
            updated_datetime = _parse_iso8601(updated_at)
        except ValueError:
            continue
        duration_seconds = max((updated_datetime - started_datetime).total_seconds(), 0.0)
        samples.append(
            WorkflowRunSample(
                run_number=int(workflow_run.get("run_number") or 0),
                status=str(workflow_run.get("status") or ""),
                conclusion=str(workflow_run.get("conclusion") or ""),
                branch=str(workflow_run.get("head_branch") or ""),
                head_sha=str(workflow_run.get("head_sha") or ""),
                html_url=str(workflow_run.get("html_url") or ""),
                duration_seconds=duration_seconds,
                run_started_at=run_started_at,
                updated_at=updated_at,
            )
        )
    return samples, None


def _emit_payload(payload: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        click.echo(json.dumps(payload, indent=2))
        return
    click.echo(json.dumps(payload, indent=2))


@click.command("gate-benchmark")
@click.option("--stack", "stack_name", required=True, help="Stack name for local benchmark (for example: cm or opw).")
@click.option(
    "--branch",
    "branch_name",
    required=True,
    help="Branch name used for GitHub workflow benchmark (for example: cm-testing).",
)
@click.option(
    "--workflow",
    "workflow_name",
    required=True,
    help="Workflow file or workflow name resolvable by GitHub API (for example: test-gate.yml).",
)
@click.option("--local-samples", default=1, show_default=True)
@click.option("--github-samples", default=5, show_default=True)
@click.option("--local-extra-argument", "local_extra_arguments", multiple=True)
@click.option("--skip-local", is_flag=True, default=False)
@click.option("--skip-github", is_flag=True, default=False)
@click.option("--json-output", is_flag=True, default=False)
def main(
    stack_name: str,
    branch_name: str,
    workflow_name: str,
    local_samples: int,
    github_samples: int,
    local_extra_arguments: tuple[str, ...],
    skip_local: bool,
    skip_github: bool,
    json_output: bool,
) -> None:
    if local_samples <= 0:
        raise click.ClickException("--local-samples must be greater than zero.")
    if github_samples <= 0:
        raise click.ClickException("--github-samples must be greater than zero.")

    repository_root = Path.cwd()
    payload: dict[str, Any] = {
        "stack": stack_name,
        "branch": branch_name,
        "workflow": workflow_name,
        "local": {
            "enabled": not skip_local,
            "samples": [],
            "summary": {},
            "error": "",
        },
        "github": {
            "enabled": not skip_github,
            "repository": "",
            "samples": [],
            "summary": {},
            "error": "",
        },
        "comparison": {
            "local_p50_seconds": 0.0,
            "github_p50_seconds": 0.0,
            "github_to_local_p50_ratio": 0.0,
            "note": "",
        },
    }

    local_durations: list[float] = []
    if not skip_local:
        local_samples_payload, local_error = _benchmark_local_gate(
            stack_name=stack_name,
            sample_count=local_samples,
            extra_arguments=local_extra_arguments,
        )
        payload["local"]["samples"] = [
            {
                "index": sample.index,
                "duration_seconds": sample.duration_seconds,
                "return_code": sample.return_code,
            }
            for sample in local_samples_payload
        ]
        local_durations = [sample.duration_seconds for sample in local_samples_payload]
        payload["local"]["summary"] = _summarize(local_durations)
        payload["local"]["error"] = local_error or ""

    github_durations: list[float] = []
    if not skip_github:
        repository_slug = _discover_repository_slug(repository_root)
        payload["github"]["repository"] = repository_slug
        workflow_samples_payload, github_error = _fetch_workflow_runs(
            repository_slug=repository_slug,
            workflow=workflow_name,
            branch=branch_name,
            sample_count=github_samples,
        )
        payload["github"]["samples"] = [
            {
                "run_number": sample.run_number,
                "status": sample.status,
                "conclusion": sample.conclusion,
                "branch": sample.branch,
                "head_sha": sample.head_sha,
                "duration_seconds": sample.duration_seconds,
                "run_started_at": sample.run_started_at,
                "updated_at": sample.updated_at,
                "html_url": sample.html_url,
            }
            for sample in workflow_samples_payload
        ]
        github_durations = [sample.duration_seconds for sample in workflow_samples_payload]
        payload["github"]["summary"] = _summarize(github_durations)
        payload["github"]["error"] = github_error or ""

    local_summary = payload["local"].get("summary", {})
    github_summary = payload["github"].get("summary", {})
    local_p50 = float(local_summary.get("p50_seconds") or 0.0)
    github_p50 = float(github_summary.get("p50_seconds") or 0.0)

    payload["comparison"]["local_p50_seconds"] = local_p50
    payload["comparison"]["github_p50_seconds"] = github_p50
    if local_p50 > 0 and github_p50 > 0:
        ratio = github_p50 / local_p50
        payload["comparison"]["github_to_local_p50_ratio"] = ratio
        payload["comparison"]["note"] = (
            "GitHub workflow p50 is within 1.5x local benchmark."
            if ratio <= 1.5
            else "GitHub workflow p50 is above 1.5x local benchmark; evaluate self-hosted runners."
        )
    else:
        payload["comparison"]["note"] = "Insufficient data for local vs GitHub p50 comparison."

    _emit_payload(payload, json_output=json_output)


if __name__ == "__main__":
    main()
