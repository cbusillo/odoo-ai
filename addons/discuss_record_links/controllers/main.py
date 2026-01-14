from odoo import http
from odoo.http import request

from ..models.config_util import load_config, extract_template_fields, render_template, parse_prefix, ModelCfg


class DiscussRecordLinks(http.Controller):
    @http.route("/discuss_record_links/search", type="jsonrpc", auth="user", methods=["POST"])
    def search(self, term: str = ""):
        env = request.env
        cfg = load_config(env)

        model_filter, query = parse_prefix(term or "", cfg)
        tokens = [t for t in (query or "").strip().split() if t]

        def build_domain(model_cfg: ModelCfg) -> list:
            if not tokens:
                return []
            search_domain: list = []
            search_fields = model_cfg.search or ["name"]
            for t in tokens:
                # OR across all fields for this single token
                leaves: list = [[f, "ilike", t] for f in search_fields]
                if len(leaves) > 1:
                    sub = ["|"] * (len(leaves) - 1) + leaves
                else:
                    sub = leaves[0]
                search_domain = ["&", search_domain, sub] if search_domain else sub
            return search_domain

        suggestions = []
        for key, model_cfg in cfg.items():
            if model_filter and model_cfg.model != model_filter:
                continue
            domain = build_domain(model_cfg)
            # fields needed for display template + display_name fallback
            display_fields = {"display_name"}
            display_fields.update(extract_template_fields(model_cfg.display_template))
            rows = env[model_cfg.model].sudo().search_read(domain, list(display_fields), limit=model_cfg.limit)
            for r in rows:
                # render label per model config
                label = render_template(model_cfg.display_template or "{{ display_name }}", r) or r.get("display_name")
                suggestions.append(
                    {
                        "group": model_cfg.label,
                        "model": model_cfg.model,
                        "id": r["id"],
                        "label": label,
                    }
                )

        # Return a single flat list; client groups by .group
        return {"suggestions": suggestions}

    @http.route("/discuss_record_links/labels", type="jsonrpc", auth="user", methods=["POST"])
    def labels(self, targets: list[dict] | None = None):
        """Return rendered labels for a list of {model, id} using configured templates.

        targets example: [{"model": "motor", "id": 42}, ...]
        """
        env = request.env
        cfg = load_config(env)
        # Build map model -> cfg
        by_model_cfg: dict[str, ModelCfg] = {}
        for model_cfg in cfg.values():
            by_model_cfg[model_cfg.model] = model_cfg

        result: list[dict] = []
        if not targets:
            return result
        # Group ids by model
        by_model: dict[str, set[int]] = {}
        for t in targets:
            model = (t or {}).get("model")
            rid = (t or {}).get("id")
            if not model or not rid:
                continue
            by_model.setdefault(model, set()).add(int(rid))

        for model, idset in by_model.items():
            model_cfg = by_model_cfg.get(model)
            if not model_cfg:
                # Fallback to display_name only
                rows = env[model].sudo().browse(list(idset)).read(["display_name"])
                for r in rows:
                    result.append({"model": model, "id": r["id"], "label": r.get("display_name")})
                continue
            display_fields = {"display_name"}
            display_fields.update(extract_template_fields(model_cfg.display_template))
            rows = env[model].sudo().browse(list(idset)).read(list(display_fields))
            for r in rows:
                label = render_template(model_cfg.display_template or "{{ display_name }}", r) or r.get("display_name")
                result.append({"model": model, "id": r["id"], "label": label})

        return result
