import json
import os
from pathlib import Path


TOUR_PREFIX = os.environ.get("RECORDED_TOURS_PREFIX", "test_")
DEFAULT_OUTPUT = "-"


def _normalize_steps(steps: list[dict[str, object]] | list[object]) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        trigger_value = step.get("trigger")
        if not isinstance(trigger_value, str) or not trigger_value:
            continue
        normalized.append(
            {
                "sequence": step.get("sequence"),
                "trigger": trigger_value,
                "content": step.get("content"),
                "run": step.get("run"),
                "tooltip_position": step.get("tooltip_position"),
            }
        )
    return normalized


def export_recorded_tours(env) -> None:
    output_value = os.environ.get("RECORDED_TOURS_OUTPUT", DEFAULT_OUTPUT)
    tour_model = env["web_tour.tour"]
    domain = [("name", "ilike", f"{TOUR_PREFIX}%"), ("step_ids", "!=", False)]
    if "custom" in tour_model._fields:
        domain.append(("custom", "=", True))

    tours = tour_model.search(domain)
    payload: list[dict[str, object]] = []
    for tour in tours:
        steps = [
            {
                "sequence": step.sequence,
                "trigger": step.trigger,
                "content": step.content,
                "run": step.run,
                "tooltip_position": step.tooltip_position,
            }
            for step in tour.step_ids.sorted(lambda record: record.sequence or record.id)
        ]
        normalized_steps = _normalize_steps(steps)
        if not normalized_steps:
            continue
        payload.append(
            {
                "name": tour.name,
                "url": tour.url or "/web",
                "steps": normalized_steps,
            }
        )

    output_text = json.dumps(payload, indent=2, sort_keys=True)
    if output_value == "-":
        print(output_text)
        return
    output_path = Path(output_value)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output_text, encoding="utf-8")
    print(f"Exported {len(payload)} recorded tour(s) to {output_path}")


if "env" in globals():
    export_recorded_tours(globals()["env"])
else:
    raise SystemExit("Run via Odoo shell: uv run ops local shell <target> < tools/tour_recorder/export_recorded_tours.py")
