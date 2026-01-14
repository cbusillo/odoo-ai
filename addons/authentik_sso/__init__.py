from odoo import SUPERUSER_ID, api

from . import models


def post_init_hook(cr_or_env, registry=None) -> None:
    if registry is None:
        env = cr_or_env
        if not hasattr(env, "registry"):
            return
        if "authentik.sso.config" in env.registry:
            env["authentik.sso.config"].sudo().apply_from_env()
            env.cr.commit()
        return

    env = api.Environment(cr_or_env, SUPERUSER_ID, {})
    if "authentik.sso.config" in env.registry:
        env["authentik.sso.config"].sudo().apply_from_env()
        cr_or_env.commit()
