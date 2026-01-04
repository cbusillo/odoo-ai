import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from .counts import count_js_tests, count_py_tests

_logger = logging.getLogger(__name__)
SEC_PER_BUCKET = 5


def discover_modules_with(patterns: list[str], addons_root: Path | None = None) -> list[str]:
    addons = addons_root or Path("addons")
    modules: list[str] = []
    if not addons.exists():
        return modules
    for module_dir in addons.iterdir():
        if not module_dir.is_dir() or not (module_dir / "__manifest__.py").exists():
            continue
        for pattern in patterns:
            if list(module_dir.glob(pattern)):
                modules.append(module_dir.name)
                break
    return modules


def greedy_shards(items: list[str], shard_count: int) -> list[list[str]]:
    if shard_count <= 1 or len(items) <= 1:
        return [items]
    shards: list[list[str]] = [[] for _ in range(shard_count)]
    for index, item in enumerate(sorted(items)):
        shards[index % shard_count].append(item)
    return [shard for shard in shards if shard]


def compute_weights(modules: list[str], phase: str) -> dict[str, int]:
    """Estimate module weights by counting tests for the given phase.

    phase ∈ {"unit","js","integration","tour"}
    """
    weights: dict[str, int] = {}
    for name in modules:
        root = Path("addons") / name
        if not root.exists():
            continue
        if phase == "unit":
            paths = list(root.glob("**/tests/unit/**/*.py"))
            weights[name] = count_py_tests(paths)
        elif phase == "integration":
            paths = list(root.glob("**/tests/integration/**/*.py"))
            weights[name] = count_py_tests(paths)
        elif phase == "tour":
            paths = list(root.glob("**/tests/tour/**/*.py"))
            weights[name] = count_py_tests(paths)
        elif phase == "js":
            paths = list(root.glob("static/tests/**/*.test.js"))
            weights[name] = count_js_tests(paths)
        else:
            weights[name] = 1
        # Ensure minimum weight 1 so an empty module still schedules
        if weights[name] <= 0:
            weights[name] = 1
    # Blend in historical timing if available
    try:
        cache = json.loads((Path("tmp/test-logs") / "weights.json").read_text())
    except (OSError, json.JSONDecodeError) as exc:
        _logger.debug("sharding: failed to load weight cache (%s)", exc)
        cache = {}
    phase_cache = cache.get(phase) or {}
    for name in list(weights.keys()):
        record = phase_cache.get(name)
        if not record:
            continue
        seconds = float(record.get("avg_secs") or 0.0)
        bucket = max(0, int(seconds // SEC_PER_BUCKET))
        weights[name] = max(1, int(weights[name]) + bucket)
    return weights


@dataclass
class ShardPlan:
    phase: str
    shards: list[dict]
    total_weight: int
    shards_count: int
    strategy: str = "lpt_v1"


def lpt_shards(weights: dict[str, int], shard_count: int) -> ShardPlan:
    """Longest Processing Time bin packing.

    Distributes modules into n shards by descending weight, always placing the
    next module onto the shard with the smallest current sum.
    """
    if shard_count <= 1 or len(weights) <= 1:
        items = sorted(weights.items(), key=lambda entry: entry[0])
        total_weight = sum(weight for _, weight in items)
        return ShardPlan(
            phase="unknown",
            shards=[
                {
                    "index": 0,
                    "weight": total_weight,
                    "modules": [{"name": module_name, "weight": weight} for module_name, weight in items],
                }
            ],
            total_weight=total_weight,
            shards_count=1,
        )

    # Initialize shard buckets
    shards: list[dict] = [{"index": index, "weight": 0, "modules": []} for index in range(shard_count)]
    # Assign in descending weight order
    for module_name, weight in sorted(weights.items(), key=lambda entry: entry[1], reverse=True):
        target = min(shards, key=lambda shard: shard["weight"])  # current lightest shard
        target["modules"].append({"name": module_name, "weight": int(weight)})
        target["weight"] = int(target["weight"]) + int(weight)

    total_weight = sum(shard["weight"] for shard in shards)
    return ShardPlan(phase="unknown", shards=shards, total_weight=total_weight, shards_count=len(shards))


def plan_shards_for_phase(modules: list[str], phase: str, n_shards: int) -> ShardPlan:
    if not modules:
        return ShardPlan(phase=phase, shards=[{"index": 0, "weight": 0, "modules": []}], total_weight=0, shards_count=1)
    weights = compute_weights(modules, phase)
    plan = lpt_shards(weights, max(1, n_shards))
    plan.phase = phase
    # Drop empty shards if any
    plan.shards = [shard for shard in plan.shards if shard.get("modules")]
    plan.shards_count = len(plan.shards)
    return plan


# ---------------- Within-module sharding (by class) ----------------


@dataclass
class ClassItem:
    module: str
    cls: str
    weight: int


def _test_classes_in_file(text: str) -> list[tuple[str, int]]:
    classes: list[tuple[str, int]] = []
    class_iter = list(re.finditer(r"^\s*class\s+([A-Za-z_]\w*)\s*\([^)]*\):", text, flags=re.M))
    for index, match in enumerate(class_iter):
        name = match.group(1)
        start = match.end()
        end = class_iter[index + 1].start() if index + 1 < len(class_iter) else len(text)
        block = text[start:end]
        tests = len(re.findall(r"^\s*def\s+test_", block, flags=re.M))
        if tests > 0:
            classes.append((name, tests))
    return classes


def discover_test_classes(modules: list[str], phase: str) -> list[ClassItem]:
    root = Path("addons")
    class_items: list[ClassItem] = []
    patterns = {
        "unit": "tests/unit/**/*.py",
        "integration": "tests/integration/**/*.py",
        "tour": "tests/tour/**/*.py",
    }
    pattern = patterns.get(phase)
    if not pattern:
        return class_items
    for module_name in modules:
        module_dir = root / module_name
        for path in module_dir.glob(pattern):
            if not path.is_file():
                continue
            try:
                content = path.read_text(errors="ignore")
            except OSError:
                continue
            for class_name, weight in _test_classes_in_file(content):
                class_items.append(ClassItem(module=module_name, cls=class_name, weight=weight))
    return class_items


def plan_within_module_shards(modules: list[str], phase: str, shard_count: int) -> list[list[ClassItem]]:
    items = discover_test_classes(modules, phase)
    if not items or shard_count <= 1:
        return [items] if items else []
    shards: list[list[ClassItem]] = [[] for _ in range(shard_count)]
    shard_weights = [0] * shard_count
    for item in sorted(items, key=lambda entry: entry.weight, reverse=True):
        target_index = min(range(shard_count), key=lambda index: shard_weights[index])
        shards[target_index].append(item)
        shard_weights[target_index] += item.weight
    return [shard for shard in shards if shard]
