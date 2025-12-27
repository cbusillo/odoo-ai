from odoo import api, fields, models
from typing import Any
from .config_util import load_config


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    discuss_record_links_summary = fields.Char(
        string="Record Link Prefixes",
        help="Quick summary of configured prefixes.",
        compute="_compute_drl_summary",
    )

    @api.model
    def get_values(self) -> dict[str, Any]:
        return super().get_values()

    @api.depends()
    def _compute_drl_summary(self) -> None:
        for s in self:
            cfg = load_config(self.env)
            keys = list(cfg.keys())
            if not keys:
                s.discuss_record_links_summary = "No prefixes configured"
            else:
                preview = ", ".join(keys[:6]) + ("…" if len(keys) > 6 else "")
                s.discuss_record_links_summary = f"Prefixes: {preview}"
