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

        def build_domain(c: ModelCfg):
            if not tokens:
                return []
            domain: list = []
            fields = c.search or ["name"]
            for t in tokens:
                # OR across all fields for this single token
                leaves: list = [[f, "ilike", t] for f in fields]
                if len(leaves) > 1:
                    sub = ["|"] * (len(leaves) - 1) + leaves
                else:
                    sub = leaves[0]
                domain = ["&", domain, sub] if domain else sub
            return domain

        suggestions = []
        for key, c in cfg.items():
            if model_filter and c.model != model_filter:
                continue
            domain = build_domain(c)
            # fields needed for display template + display_name fallback
            fields = {"display_name"}
            fields.update(extract_template_fields(c.display_template))
            rows = env[c.model].sudo().search_read(domain, list(fields), limit=c.limit)
            for r in rows:
                # render label per model config
                label = render_template(c.display_template or "{{ display_name }}", r) or r.get("display_name")
                suggestions.append(
                    {
                        "group": c.label,
                        "model": c.model,
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
        for c in cfg.values():
            by_model_cfg[c.model] = c

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
            c = by_model_cfg.get(model)
            if not c:
                # Fallback to display_name only
                rows = env[model].sudo().read(list(idset), ["display_name"])
                for r in rows:
                    result.append({"model": model, "id": r["id"], "label": r.get("display_name")})
                continue
            fields = {"display_name"}
            fields.update(extract_template_fields(c.display_template))
            rows = env[model].sudo().read(list(idset), list(fields))
            for r in rows:
                label = render_template(c.display_template or "{{ display_name }}", r) or r.get("display_name")
                result.append({"model": model, "id": r["id"], "label": label})

        return result
