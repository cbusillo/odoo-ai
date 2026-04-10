from typing import ClassVar

from test_support.tests.fixtures.base_cases import SharedTourTestCase

from ..common_imports import common


@common.tagged(*common.TOUR_TAGS)
class TourTestCase(SharedTourTestCase):
    reset_assets_per_database = True
    assets_reset_db_names: ClassVar[set[str]] = set()
    optional_group_xmlids = ("mail.group_mail_user",)

    @classmethod
    def ensure_tour_product(
        cls,
        *,
        default_code: str,
        name: str,
    ) -> "odoo.model.product_product":
        product_model = cls.env["product.product"].with_context(skip_sku_check=True)
        product_record = product_model.search([("default_code", "=", default_code)], limit=1)
        if not product_record:
            product_record = product_model.create({"name": name, "default_code": default_code})
        return product_record

    @classmethod
    def ensure_discuss_channel(cls, channel_name: str = "DRL Tour") -> "odoo.model.discuss_channel":
        channel_record = cls.env["discuss.channel"].search([("name", "=", channel_name)], limit=1)
        if not channel_record:
            channel_record = cls.env["discuss.channel"].create({"name": channel_name})

        channel_record.add_members(
            partner_ids=[cls.test_user.partner_id.id],
            post_joined_message=False,
        )
        channel_record.with_user(cls.test_user).channel_pin(pinned=True)
        return channel_record

    @classmethod
    def ensure_discuss_channel_active_id(cls, channel_name: str = "DRL Tour") -> str:
        return f"discuss.channel_{cls.ensure_discuss_channel(channel_name).id}"

    @classmethod
    def set_config_parameter(cls, parameter_name: str, value: str | int) -> None:
        cls.env["ir.config_parameter"].sudo().set_param(parameter_name, str(value))

    @classmethod
    def ensure_record_link_config(
        cls,
        *,
        prefix: str,
        label: str = "Products",
        model_name: str = "product.product",
        search_field_names: tuple[str, ...] = ("name",),
        display_template: str = "[{{ default_code }}] {{ name }}",
        limit: int = 8,
    ) -> "odoo.model.discuss_record_link_config":
        config_model = cls.env["discuss.record.link.config"]
        existing_config = config_model.search([("prefix", "=", prefix)], limit=1)
        if existing_config:
            return existing_config

        model_record = cls.env["ir.model"].search([("model", "=", model_name)], limit=1)
        search_fields = cls.env["ir.model.fields"].search(
            [("model_id", "=", model_record.id), ("name", "in", list(search_field_names))]
        )
        return config_model.create(
            {
                "active": True,
                "prefix": prefix,
                "label": label,
                "model_id": model_record.id,
                "search_field_ids": [(6, 0, search_fields.ids)],
                "display_template": display_template,
                "limit": limit,
            }
        )
