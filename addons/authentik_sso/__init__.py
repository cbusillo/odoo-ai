from odoo import SUPERUSER_ID, api

from . import models


def post_init_hook(cr, registry) -> None:
    env = api.Environment(cr, SUPERUSER_ID, {})
    if "authentik.sso.config" in env.registry:
        env["authentik.sso.config"].sudo().apply_from_env()
        cr.commit()
