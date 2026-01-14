from odoo import SUPERUSER_ID, api

from . import controllers, models

TEMPLATE_LOGIN = "authentik_template_user"


def pre_init_hook(cr_or_env) -> None:
    if hasattr(cr_or_env, "registry"):
        env = cr_or_env
    else:
        env = api.Environment(cr_or_env, SUPERUSER_ID, {})
    existing_user = (
        env["res.users"]
        .sudo()
        .with_context(active_test=False)
        .search(
            [
                ("login", "=", TEMPLATE_LOGIN),
            ],
            limit=1,
        )
    )
    if not existing_user:
        return
    model_data = env["ir.model.data"].sudo()
    existing_xml_id = model_data.search(
        [
            ("module", "=", "authentik_sso"),
            ("name", "=", "authentik_template_user"),
        ],
        limit=1,
    )
    if existing_xml_id:
        return
    model_data.create(
        {
            "module": "authentik_sso",
            "name": "authentik_template_user",
            "model": "res.users",
            "res_id": existing_user.id,
            "noupdate": False,
        }
    )


def post_init_hook(cr_or_env, registry=None) -> None:
    if registry is None:
        env = cr_or_env
        if not hasattr(env, "registry"):
            return
        if "authentik.sso.config" in env.registry:
            env["authentik.sso.config"].sudo().apply_from_env()
        if "authentik.sso.group.mapping" in env.registry:
            env["authentik.sso.group.mapping"].sudo().ensure_default_mappings()
        env.cr.commit()
        return

    env = api.Environment(cr_or_env, SUPERUSER_ID, {})
    if "authentik.sso.config" in env.registry:
        env["authentik.sso.config"].sudo().apply_from_env()
    if "authentik.sso.group.mapping" in env.registry:
        env["authentik.sso.group.mapping"].sudo().ensure_default_mappings()
    cr_or_env.commit()
