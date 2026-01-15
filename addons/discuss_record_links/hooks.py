from dataclasses import dataclass

from odoo.api import Environment


@dataclass(frozen=True)
class DefaultLinkConfig:
    prefix: str
    label: str
    model: str
    limit: int = 8
    display_template: str | None = None


DEFAULT_LINK_CONFIGS: tuple[DefaultLinkConfig, ...] = (
    DefaultLinkConfig(prefix="inv", label="Invoices", model="account.move"),
    DefaultLinkConfig(prefix="po", label="Purchase Orders", model="purchase.order"),
)


def _get_existing_prefixes(env: Environment) -> set[str]:
    config_model = env["discuss.record.link.config"].with_context(active_test=False).sudo()
    return set(config_model.search([]).mapped("prefix"))


def _resolve_model_id(env: Environment, model_name: str) -> int | None:
    model_record = env["ir.model"].sudo().search([("model", "=", model_name)], limit=1)
    return model_record.id or None


def _seed_optional_configs(env: Environment) -> None:
    existing_prefixes = _get_existing_prefixes(env)
    config_model = env["discuss.record.link.config"].sudo()
    for default_config in DEFAULT_LINK_CONFIGS:
        if default_config.prefix in existing_prefixes:
            continue
        model_id = _resolve_model_id(env, default_config.model)
        if not model_id:
            continue
        values = {
            "active": True,
            "prefix": default_config.prefix,
            "label": default_config.label,
            "model_id": model_id,
            "limit": default_config.limit,
        }
        if default_config.display_template:
            values["display_template"] = default_config.display_template
        config_model.create(values)


def post_init_hook(env: Environment) -> None:
    _seed_optional_configs(env)
