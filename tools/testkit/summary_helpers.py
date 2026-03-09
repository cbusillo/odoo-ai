from __future__ import annotations


def host_resources_from_run_plan(run_plan: dict[str, object]) -> dict[str, int]:
    host_resources = run_plan.get("host_resources")
    if not isinstance(host_resources, dict):
        return {}
    normalized: dict[str, int] = {}
    for key in ("browser_slots", "production_clone_slots"):
        value = host_resources.get(key)
        if isinstance(value, int):
            normalized[key] = value
    return normalized


def outcome_kinds_from_results(results: dict[str, object]) -> dict[str, int]:
    outcome_kinds: dict[str, int] = {}
    for phase_payload in results.values():
        if not isinstance(phase_payload, dict):
            continue
        phase_outcomes = phase_payload.get("outcome_kinds")
        if not isinstance(phase_outcomes, dict):
            continue
        for name, value in phase_outcomes.items():
            if isinstance(name, str) and isinstance(value, int):
                outcome_kinds[name] = outcome_kinds.get(name, 0) + value
    return outcome_kinds


def phase_outcome_kinds_from_results(results: dict[str, object]) -> dict[str, dict[str, int]]:
    outcome_kinds: dict[str, dict[str, int]] = {}
    for phase, phase_payload in results.items():
        if not isinstance(phase, str) or not isinstance(phase_payload, dict):
            continue
        phase_counts = phase_payload.get("outcome_kinds")
        if not isinstance(phase_counts, dict):
            continue
        normalized_counts = {key: value for key, value in phase_counts.items() if isinstance(key, str) and isinstance(value, int)}
        if normalized_counts:
            outcome_kinds[phase] = normalized_counts
    return outcome_kinds
