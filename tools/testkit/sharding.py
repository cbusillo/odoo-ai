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
        for pat in patterns:
            if list(module_dir.glob(pat)):
                modules.append(module_dir.name)
                break
    return modules


def greedy_shards(items: list[str], n: int) -> list[list[str]]:
    if n <= 1 or len(items) <= 1:
        return [items]
    shards: list[list[str]] = [[] for _ in range(n)]
    for i, item in enumerate(sorted(items)):
        shards[i % n].append(item)
    return [s for s in shards if s]


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
    ph_cache = cache.get(phase) or {}
    for name in list(weights.keys()):
        rec = ph_cache.get(name)
        if not rec:
            continue
        secs = float(rec.get("avg_secs") or 0.0)
        bucket = max(0, int(secs // SEC_PER_BUCKET))
        weights[name] = max(1, int(weights[name]) + bucket)
    return weights


@dataclass
class ShardPlan:
    phase: str
    shards: list[dict]
    total_weight: int
    shards_count: int
    strategy: str = "lpt_v1"


def lpt_shards(weights: dict[str, int], n: int) -> ShardPlan:
    """Longest Processing Time bin packing.

    Distributes modules into n shards by descending weight, always placing the
    next module onto the shard with the smallest current sum.
    """
    if n <= 1 or len(weights) <= 1:
        items = sorted(weights.items(), key=lambda kv: kv[0])
        wsum = sum(w for _, w in items)
        return ShardPlan(
            phase="unknown",
            shards=[{"index": 0, "weight": wsum, "modules": [{"name": k, "weight": v} for k, v in items]}],
            total_weight=wsum,
            shards_count=1,
        )

    # Initialize shard buckets
    shards: list[dict] = [{"index": i, "weight": 0, "modules": []} for i in range(n)]
    # Assign in descending weight order
    for name, w in sorted(weights.items(), key=lambda kv: kv[1], reverse=True):
        target = min(shards, key=lambda s: s["weight"])  # current lightest shard
        target["modules"].append({"name": name, "weight": int(w)})
        target["weight"] = int(target["weight"]) + int(w)

    total = sum(s["weight"] for s in shards)
    return ShardPlan(phase="unknown", shards=shards, total_weight=total, shards_count=len(shards))


def plan_shards_for_phase(modules: list[str], phase: str, n_shards: int) -> ShardPlan:
    if not modules:
        return ShardPlan(phase=phase, shards=[{"index": 0, "weight": 0, "modules": []}], total_weight=0, shards_count=1)
    weights = compute_weights(modules, phase)
    plan = lpt_shards(weights, max(1, n_shards))
    plan.phase = phase
    # Drop empty shards if any
    plan.shards = [s for s in plan.shards if s.get("modules")]
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
    # noinspection RegExpSimplifiable  # Keep explicit groups for readability.
    class_iter = list(re.finditer(r"^\s*class\s+([A-Za-z_][\w]*)\s*\([^)]*\):", text, flags=re.M))
    for i, m in enumerate(class_iter):
        name = m.group(1)
        start = m.end()
        end = class_iter[i + 1].start() if i + 1 < len(class_iter) else len(text)
        block = text[start:end]
        tests = len(re.findall(r"^\s*def\s+test_", block, flags=re.M))
        if tests > 0:
            classes.append((name, tests))
    return classes


def discover_test_classes(modules: list[str], phase: str) -> list[ClassItem]:
    root = Path("addons")
    out: list[ClassItem] = []
    patterns = {
        "unit": "tests/unit/**/*.py",
        "integration": "tests/integration/**/*.py",
        "tour": "tests/tour/**/*.py",
    }
    pat = patterns.get(phase)
    if not pat:
        return out
    for mod in modules:
        mdir = root / mod
        for p in mdir.glob(pat):
            if not p.is_file():
                continue
            try:
                txt = p.read_text(errors="ignore")
            except OSError:
                continue
            for cname, wt in _test_classes_in_file(txt):
                out.append(ClassItem(module=mod, cls=cname, weight=wt))
    return out


def plan_within_module_shards(modules: list[str], phase: str, n: int) -> list[list[ClassItem]]:
    items = discover_test_classes(modules, phase)
    if not items or n <= 1:
        return [items] if items else []
    shards: list[list[ClassItem]] = [[] for _ in range(n)]
    weights = [0] * n
    for it in sorted(items, key=lambda x: x.weight, reverse=True):
        idx = min(range(n), key=lambda i: weights[i])
        shards[idx].append(it)
        weights[idx] += it.weight
    return [s for s in shards if s]
