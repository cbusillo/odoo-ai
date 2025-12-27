from odoo.tests import TransactionCase, tagged
import pathlib


def _infer_addon_name() -> str:
    parts = __name__.split(".")
    if "addons" in parts:
        i = parts.index("addons")
        if i + 1 < len(parts):
            return parts[i + 1]
    try:
        p = pathlib.Path(__file__).resolve()
        for parent in p.parents:
            if parent.name == "addons":
                return p.parent.name
    except (OSError, RuntimeError):
        # Path resolution can fail in some harnesses; fall back to default
        pass
    return "hr_employee_name_extended"


STANDARD_TAGS = ["post_install", "-at_install"]
UNIT_TAGS = STANDARD_TAGS + ["unit_test"]
MODULE_TAG = _infer_addon_name()

__all__ = [
    "tagged",
    "TransactionCase",
    "STANDARD_TAGS",
    "UNIT_TAGS",
    "MODULE_TAG",
]
