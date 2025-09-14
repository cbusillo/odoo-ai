from __future__ import annotations

import json
import re
from pathlib import Path


def _hash_text(text: str) -> str:
    import hashlib

    return hashlib.sha1(text.encode(errors="ignore")).hexdigest()[:16]


def parse_failures(log_path: Path) -> list[dict]:
    entries: list[dict] = []
    hoot_entries: list[dict] = []
    if not log_path.exists():
        return []
    cur: dict | None = None
    collecting_tb = False
    tb_lines: list[str] = []
    collecting_hoot = False
    hoot_lines: list[str] = []
    hoot_test: str | None = None

    with open(log_path, errors="ignore") as f:
        for raw in f:
            line = raw.rstrip("\n")
            l = line.strip()
            lw = l.lower()
            # Python traceback capture
            if l.startswith("Traceback (most recent call last):"):
                collecting_tb = True
                tb_lines = [l]
                if cur is None:
                    cur = {"type": "error", "message": "", "test": None}
                continue
            if collecting_tb:
                if l == "" and tb_lines:
                    cur = cur or {"type": "error", "message": "", "test": None}
                    tb = "\n".join(tb_lines)
                    cur["traceback"] = tb
                    cur["fingerprint"] = _hash_text(tb)
                    entries.append(cur)
                    cur = None
                    tb_lines = []
                    collecting_tb = False
                else:
                    tb_lines.append(l)
                continue

            # HOOT per-test failure lines
            m_hoot = re.search(r"\[HOOT] Test \"(?P<name>.+?)\" failed:", l)
            if m_hoot:
                if collecting_hoot and hoot_lines:
                    msg = "\n".join(hoot_lines).strip()
                    ent = {"type": "js_fail", "test": hoot_test, "message": msg}
                    ent["fingerprint"] = _hash_text(f"{hoot_test}\n{msg}")
                    hoot_entries.append(ent)
                collecting_hoot = True
                hoot_lines = [l]
                hoot_test = m_hoot.group("name")
                continue
            if collecting_hoot:
                if re.match(r"^\d{4}-\d{2}-\d{2} ", l):
                    msg = "\n".join(hoot_lines).strip()
                    ent = {"type": "js_fail", "test": hoot_test, "message": msg}
                    ent["fingerprint"] = _hash_text(f"{hoot_test}\n{msg}")
                    hoot_entries.append(ent)
                    collecting_hoot = False
                    hoot_lines = []
                    hoot_test = None
                else:
                    hoot_lines.append(l)

            # Unittest-style headers (heuristic)
            if lw.startswith(("fail:", "error:")):
                parts = l.split(maxsplit=1)
                typ = parts[0].rstrip(":").lower()
                rest = parts[1] if len(parts) > 1 else ""
                rest_l = rest.lower()
                if "test" not in rest_l:
                    continue
                test_id = rest
                cur = {"type": "fail" if typ == "fail" else "error", "test": test_id, "message": ""}

    # Flush dangling blocks
    if collecting_hoot and hoot_lines:
        msg = "\n".join(hoot_lines).strip()
        ent = {"type": "js_fail", "test": hoot_test, "message": msg}
        ent["fingerprint"] = _hash_text(f"{hoot_test}\n{msg}")
        hoot_entries.append(ent)

    return entries + hoot_entries
