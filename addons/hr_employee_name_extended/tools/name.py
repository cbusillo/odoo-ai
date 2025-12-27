from odoo.api import Environment


class NameFormatter:
    DEFAULT_PATTERNS: dict[str, str] = {
        "western": "{first_name} {last_name}",
        "asian": "{last_name} {first_name}",
        "spanish": "{first_name} {last_name}",
        "arabic": "{first_name} {last_name}",
    }

    @classmethod
    def _pattern(cls, env: Environment) -> str:
        icp = env["ir.config_parameter"].sudo()
        fmt = (icp.get_param("user_name_extended.format") or "western").strip().lower()
        custom = (icp.get_param("user_name_extended.custom_pattern") or "").strip() if fmt == "custom" else ""
        base = cls.DEFAULT_PATTERNS.get(fmt, cls.DEFAULT_PATTERNS["western"])
        return custom or base

    @classmethod
    def _norm(cls, value: str | None) -> str:
        return (value or "").strip()

    @classmethod
    def _norm_values(cls, first_name: str | None, last_name: str | None, nickname: str | None) -> dict[str, str]:
        return {
            "first_name": cls._norm(first_name),
            "last_name": cls._norm(last_name),
            "nickname": cls._norm(nickname),
        }

    @classmethod
    def compose_legal_name(
        cls, env: Environment, first_name: str, last_name: str, nickname: str | None = None, fmt_override: str | None = None
    ) -> str:
        if fmt_override == "custom":
            pattern = env["ir.config_parameter"].sudo().get_param("user_name_extended.custom_pattern") or cls._pattern(env)
        elif fmt_override:
            pattern = cls.DEFAULT_PATTERNS.get(fmt_override, cls._pattern(env))
        else:
            pattern = cls._pattern(env)
        values = cls._norm_values(first_name, last_name, nickname)
        raw = pattern.format(**values)
        parts = [p for p in raw.split(" ") if p]
        return " ".join(parts).strip()

    @classmethod
    def split_full_name(cls, full_name: str, fmt: str = "western") -> dict[str, str]:
        if not full_name:
            return {"first_name": "", "last_name": ""}
        full_name = " ".join(full_name.split())
        parts = full_name.split(" ", 1)
        if len(parts) == 1:
            return {"first_name": parts[0], "last_name": ""}
        if fmt == "asian":
            return {"last_name": parts[0], "first_name": parts[1]}
        return {"first_name": parts[0], "last_name": parts[1]}
