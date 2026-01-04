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
    current_entry: dict | None = None
    collecting_tb = False
    traceback_lines: list[str] = []
    collecting_hoot = False
    hoot_lines: list[str] = []
    hoot_test: str | None = None

    def _append_hoot_entry() -> None:
        nonlocal hoot_lines, hoot_test, collecting_hoot
        if not hoot_lines:
            return
        message = "\n".join(hoot_lines).strip()
        hoot_entries.append(
            {
                "type": "js_fail",
                "test": hoot_test,
                "message": message,
                "fingerprint": _hash_text(f"{hoot_test}\n{message}"),
            }
        )
        hoot_lines = []
        hoot_test = None
        collecting_hoot = False

    with open(log_path, errors="ignore") as log_handle:
        for raw_line in log_handle:
            line = raw_line.rstrip("\n")
            stripped_line = line.strip()
            lowered_line = stripped_line.lower()
            # Python traceback capture
            if stripped_line.startswith("Traceback (most recent call last):"):
                collecting_tb = True
                traceback_lines = [stripped_line]
                if current_entry is None:
                    current_entry = {"type": "error", "message": "", "test": None}
                continue
            if collecting_tb:
                if not stripped_line and traceback_lines:
                    current_entry = current_entry or {"type": "error", "message": "", "test": None}
                    traceback_text = "\n".join(traceback_lines)
                    current_entry["traceback"] = traceback_text
                    current_entry["fingerprint"] = _hash_text(traceback_text)
                    entries.append(current_entry)
                    current_entry = None
                    traceback_lines = []
                    collecting_tb = False
                else:
                    traceback_lines.append(stripped_line)
                continue

            # HOOT per-test failure lines
            hoot_match = re.search(r"\[HOOT] Test \"(?P<name>.+?)\" failed:", stripped_line)
            if hoot_match:
                if collecting_hoot and hoot_lines:
                    _append_hoot_entry()
                collecting_hoot = True
                hoot_lines = [stripped_line]
                hoot_test = hoot_match.group("name")
                continue
            if collecting_hoot:
                if re.match(r"^\d{4}-\d{2}-\d{2} ", stripped_line):
                    _append_hoot_entry()
                else:
                    hoot_lines.append(stripped_line)

            # Unittest-style headers (heuristic)
            if lowered_line.startswith(("fail:", "error:")):
                parts = stripped_line.split(maxsplit=1)
                failure_type = parts[0].rstrip(":").lower()
                rest_text = parts[1] if len(parts) > 1 else ""
                rest_lower = rest_text.lower()
                if "test" not in rest_lower:
                    continue
                test_id = rest_text
                current_entry = {
                    "type": "fail" if failure_type == "fail" else "error",
                    "test": test_id,
                    "message": "",
                }

    # Flush dangling blocks
    if collecting_hoot and hoot_lines:
        _append_hoot_entry()

    return entries + hoot_entries
