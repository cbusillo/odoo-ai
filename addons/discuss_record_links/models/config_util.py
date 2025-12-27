import re
from dataclasses import dataclass

import json  # noqa: F401


@dataclass
class ModelCfg:
    key: str
    model: str
    label: str
    search: list[str]
    display_template: str
    image_field: str | None
    limit: int
    enabled: bool = True


CFG_PARAM = "discuss_record_links.models"  # legacy key (no longer used)


def default_config() -> dict[str, ModelCfg]:
    return {}


def load_config(env) -> dict[str, ModelCfg]:
    cfg: dict[str, ModelCfg] = {}
    # Read structured rows only
    try:
        model = env["discuss.record.link.config"]
        rows = model.sudo().search([("active", "=", True)])
        for r in rows:
            search_fields = [f.name for f in r.search_field_ids]
            cfg[r.prefix.lower()] = ModelCfg(
                key=r.prefix.lower(),
                model=r.model_id.model,
                label=r.label,
                search=search_fields,
                display_template=r.display_template or "{{ display_name }}",
                image_field=(r.image_field_id.name if r.image_field_id else None),
                limit=r.limit or 8,
                enabled=True,
            )
    except Exception:
        # During module install/update the model might be unavailable briefly.
        pass
    return cfg


VAR_RE = re.compile(r"{{\s*(\w+)\s*}}")


def extract_template_fields(template: str) -> list[str]:
    return [m.group(1) for m in VAR_RE.finditer(template or "")]


def render_template(template: str, values: dict) -> str:
    def repl(m: re.Match[str]) -> str:
        k = m.group(1)
        v = values.get(k)
        return str(v or "")

    return VAR_RE.sub(repl, template)


def parse_prefix(term: str, config: dict[str, ModelCfg]) -> tuple[str | None, str]:
    t = (term or "").lstrip()
    if ":" in t:
        # short form: p: query, m: query, etc.
        pfx, rest = t.split(":", 1)
        key = pfx.lower().strip()
        if key in config:
            return config[key].model, rest.strip()
    parts = t.split(" ", 1)
    if len(parts) >= 2:
        key = parts[0].lower()
        if key in config:
            return config[key].model, parts[1]
        for k, c in config.items():
            if key in (k, c.label.lower()):
                return c.model, parts[1]
    return None, t
