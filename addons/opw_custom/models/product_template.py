import logging
import re
from typing import Any, Self

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _name = "product.template"
    _inherit = ["product.template", "label.mixin", "notification.manager.mixin", "transaction.mixin"]
    _description = "Product"
    _order = "create_date desc"
    _default_code_uniq = models.Constraint("unique(default_code)", "SKU must be unique.")

    SKU_PATTERN = re.compile(r"^\d{4,8}$")

    is_ready_for_sale_last_enabled_date = fields.Datetime(index=True, help="Timestamp when this product was last enabled for sale")

    default_code = fields.Char("SKU", index=True, copy=False)
    standard_price = fields.Float(
        string="Cost",
        tracking=True,
        help="Cost that was paid for the product, normally calculated from the motor cost.  Must be at least $0.01 for "
        "enabling motor products.",
    )
    initial_cost_total = fields.Float(compute="_compute_initial_cost_total", store=True)
    list_price = fields.Float(string="Price", tracking=True, default=0)
    initial_price_total = fields.Float(compute="_compute_initial_price_total", store=True)

    create_date = fields.Datetime(index=True)


    @api.model
    def default_get(self, fields_list: list[str]) -> "odoo.values.product_template":
        defaults = super().default_get(fields_list)

        source = self.env.context.get("default_source")
        if "default_code" in fields_list and source == "import":
            defaults["default_code"] = self.get_next_sku()

        return defaults

    # noinspection PyShadowingNames
    @api.model
    def _read_group(
        self,
        domain: fields.Domain,
        groupby: tuple[str, ...] | list[str] = (),
        aggregates: tuple[str, ...] | list[str] = (),
        having: fields.Domain = (),
        offset: int = 0,
        limit: int | None = None,
        order: str | None = None,
    ) -> list[tuple[object, ...]]:
        if self.env.context.get("skip_weighted_read_group"):
            return super()._read_group(
                domain,
                groupby,
                aggregates,
                having=having,
                offset=offset,
                limit=limit,
                order=order,
            )
        groups: list[tuple[object, ...]] = super()._read_group(
            domain,
            groupby,
            aggregates,
            having=having,
            offset=offset,
            limit=limit,
            order=order,
        )
        return self._apply_quantity_sums_to_read_group(
            groups,
            groupby,
            aggregates,
            base_domain=domain,
            having=having,
            offset=offset,
            limit=limit,
            order=order,
        )

    # noinspection PyShadowingNames
    @api.model
    def formatted_read_group(
        self,
        domain: fields.Domain,
        groupby: tuple[str, ...] | list[str] = (),
        aggregates: tuple[str, ...] | list[str] = (),
        having: fields.Domain = (),
        offset: int = 0,
        limit: int | None = None,
        order: str | None = None,
    ) -> list[dict[str, Any]]:
        groups: list[dict[str, Any]] = super().formatted_read_group(
            domain,
            groupby,
            aggregates,
            having=having,
            offset=offset,
            limit=limit,
            order=order,
        )
        return groups

    def _apply_quantity_sums(
        self,
        groups: list[dict[str, Any]],
        field_names: tuple[str, ...] | list[str],
        base_domain: fields.Domain | None = None,
    ) -> list[dict[str, Any]]:
        requested_field_names = set(field_names)
        weighted_list_price_requested = "list_price" in requested_field_names or "list_price:sum" in requested_field_names
        weighted_standard_price_requested = (
            "standard_price" in requested_field_names or "standard_price:sum" in requested_field_names
        )
        if not weighted_list_price_requested and not weighted_standard_price_requested:
            return groups
        for group in groups:
            group_domain: fields.Domain | None = group.get("__domain")
            output_prefix = ""
            if group_domain is None:
                extra_domain: fields.Domain | None = group.get("__extra_domain")
                if extra_domain is None or base_domain is None:
                    continue
                group_domain = fields.Domain(extra_domain) & fields.Domain(base_domain)
                output_prefix = ":sum"

            products = self.search(group_domain)
            if weighted_list_price_requested:
                group[f"list_price{output_prefix}"] = sum(product.list_price * product.initial_quantity for product in products)

            if weighted_standard_price_requested:
                group[f"standard_price{output_prefix}"] = sum(
                    product.standard_price * product.initial_quantity for product in products
                )

        return groups

    def _apply_quantity_sums_to_read_group(
        self,
        groups: list[tuple[object, ...]],
        groupby: tuple[str, ...] | list[str],
        aggregates: tuple[str, ...] | list[str],
        *,
        base_domain: fields.Domain,
        having: fields.Domain,
        offset: int,
        limit: int | None,
        order: str | None,
    ) -> list[tuple[object, ...]]:
        aggregate_set = set(aggregates)
        weighted_fields = {"list_price", "list_price:sum", "standard_price", "standard_price:sum"}
        if not aggregate_set.intersection(weighted_fields):
            return groups

        formatted_groups = super(
            ProductTemplate,
            self.with_context(skip_weighted_read_group=True),
        ).formatted_read_group(
            base_domain,
            groupby,
            aggregates,
            having=having,
            offset=offset,
            limit=limit,
            order=order,
        )
        formatted_groups = self._apply_quantity_sums(formatted_groups, aggregates, base_domain=base_domain)
        groupby_fields = list(groupby)
        groupby_count = len(groupby_fields)

        weighted_by_key: dict[tuple[object, ...], dict[str, Any]] = {}
        for formatted_group in formatted_groups:
            key = tuple(
                self._normalize_group_value(formatted_group.get(field_name))
                for field_name in groupby_fields
            )
            weighted_by_key[key] = formatted_group

        aggregate_indexes = {
            aggregate_name: groupby_count + index
            for index, aggregate_name in enumerate(aggregates)
        }
        updated_groups: list[tuple[object, ...]] = []
        for group in groups:
            group_values = list(group)
            key = tuple(
                self._normalize_group_value(value)
                for value in group_values[:groupby_count]
            )
            weighted_group = weighted_by_key.get(key)
            if weighted_group:
                for field_name in ("list_price", "standard_price"):
                    for aggregate_key in (field_name, f"{field_name}:sum"):
                        aggregate_index = aggregate_indexes.get(aggregate_key)
                        if aggregate_index is None:
                            continue
                        if aggregate_key in weighted_group:
                            group_values[aggregate_index] = weighted_group[aggregate_key]
            updated_groups.append(tuple(group_values))
        return updated_groups

    @staticmethod
    def _normalize_group_value(value: object) -> object:
        if isinstance(value, models.BaseModel):
            return value.id
        if isinstance(value, (list, tuple)) and value:
            return value[0]
        return value

    @api.model_create_multi
    def create(self, vals_list: list["odoo.values.product_template"]) -> Self:
        defaults = self.default_get(["is_ready_for_sale"])
        default_is_ready_for_sale = defaults.get("is_ready_for_sale")
        if default_is_ready_for_sale is None:
            default_is_ready_for_sale = False

        for vals in vals_list:
            source = self.env.context.get("default_source") or vals.get("source")
            if source:
                vals["source"] = source
                if source == "import":
                    vals["type"] = "consu"
                    vals["is_ready_for_sale"] = False
                    vals["is_ready_to_list"] = True
                    vals["is_storable"] = True

            if "type" in vals and vals["type"] == "service":
                vals["is_ready_for_sale"] = False
                vals["is_ready_to_list"] = False
                continue

            if not vals.get("default_code") and vals.get("type") == "consu":
                vals["default_code"] = self.get_next_sku()

            is_ready_for_sale = vals.get("is_ready_for_sale", default_is_ready_for_sale)
            if is_ready_for_sale and not vals.get("is_ready_for_sale_last_enabled_date"):
                vals["is_ready_for_sale_last_enabled_date"] = fields.Datetime.now()

        products = super().create(vals_list)
        products._post_create_actions()

        return products

    def write(self, vals: "odoo.values.product_template") -> bool:
        write_results: list[bool] = []

        for product in self:
            vals_to_write = vals.copy()
            if vals_to_write.get("is_ready_for_sale") and not product.is_ready_for_sale:
                vals_to_write["is_ready_for_sale_last_enabled_date"] = fields.Datetime.now()
            write_results.append(super(ProductTemplate, product).write(vals_to_write))

        self._post_write_actions()

        return all(write_results)

    @api.depends("initial_quantity", "list_price")
    def _compute_initial_price_total(self) -> None:
        for product in self:
            product.initial_price_total = product.initial_quantity * product.list_price

    @api.depends("initial_quantity", "standard_price")
    def _compute_initial_cost_total(self) -> None:
        for product in self:
            product.initial_cost_total = product.initial_quantity * product.standard_price

    @api.constrains("default_code")
    def check_sku(self) -> None:
        if self.env.context.get("skip_sku_check"):
            return
        for product in self:
            if not product.default_code or product.type != "consu":
                continue
            if not self.SKU_PATTERN.fullmatch(product.default_code):
                raise ValidationError(self.env._("SKU must be 4-8 digits."))

    @api.constrains("source", "type")
    def _check_source_required_for_consumable(self) -> None:
        for product in self:
            if product.type == "consu" and not product.source:
                raise ValidationError(self.env._("Source is required for consumable products."))

    def get_next_sku(self) -> str:
        sequence_model: "odoo.model.ir_sequence" = self.env["ir.sequence"]
        sequence = sequence_model.search([("code", "=", "product.template.default_code")], limit=1)
        if not sequence:
            raise ValidationError("SKU sequence missing.")

        max_sku = "9" * sequence.padding
        new_sku = sequence_model.next_by_code("product.template.default_code")
        while new_sku and new_sku <= max_sku:
            # sometimes sudo or with_context trigger even though they are correct.
            # noinspection PyUnresolvedReferences
            if not (
                self.env["product.template"].sudo().with_context(active_test=False).search([("default_code", "=", new_sku)], limit=1)
            ):
                return new_sku
            new_sku = sequence_model.next_by_code("product.template.default_code")

        raise ValidationError("SKU limit reached.")

    @api.constrains("bin")
    def _check_bin_format(self) -> None:
        self._onchange_format_bin_upper()

    @api.onchange("bin")
    def _onchange_format_bin_upper(self) -> None:
        for product in self.filtered(lambda p: p.bin and p.bin.upper() != p.bin):
            product.bin = product.bin.upper()

    def find_new_products_with_same_mpn(self) -> "odoo.model.product_template":
        existing_products = self.filtered(lambda p: p.default_code != self.default_code and p.mpn == self.mpn)
        return existing_products

    def check_for_conflicting_products(self) -> None:
        for product in self:
            existing_products = product.find_new_products_with_same_mpn()
            if existing_products:
                raise UserError(f"Product(s) with the same MPN already exist: {', '.join(existing_products.mapped('default_code'))}")

    @api.model
    def _check_fields_and_images(self, product: "odoo.model.product_template") -> list[str]:
        missing_fields = self._check_missing_fields(product)
        missing_fields += self._check_missing_images_or_small_images(product.images)
        return missing_fields

    @api.model
    def _check_missing_fields(self, product: "odoo.model.product_template") -> list[str]:
        required_fields = [
            product._fields["default_code"].name,
            product._fields["name"].name,
            product._fields["website_description"].name,
            product._fields["standard_price"].name,
            product._fields["list_price"].name,
            product._fields["initial_quantity"].name,
            product._fields["bin"].name,
            product._fields["weight"].name,
            product._fields["manufacturer"].name,
        ]

        missing_fields = [field for field in required_fields if not product[field]]

        return missing_fields

    @staticmethod
    def _check_missing_images_or_small_images(all_images: "odoo.model.product_image") -> list[str]:
        min_image_size = 50
        min_image_resolution = 1920
        missing_fields = []
        images_with_data = all_images.filtered(lambda image_candidate: image_candidate.image_1920)

        if not images_with_data:
            missing_fields.append("images")

        for image_record in images_with_data:
            if image_record.image_1920_file_size_kb < min_image_size:
                missing_fields.append(
                    f"Image ({image_record.initial_index}) too small ("
                    f"{image_record.image_1920_file_size_kb}kB < {min_image_size}kB minimum size)"
                )
            if (
                image_record.image_1920_width < min_image_resolution - 1
                and image_record.image_1920_height < min_image_resolution - 1
            ):
                missing_fields.append(
                    f"Image ({image_record.initial_index}) too small ("
                    f"{image_record.image_1920_width}x{image_record.image_1920_height} < "
                    f"{min_image_resolution}x{min_image_resolution} minimum size)"
                )

        return missing_fields

    def _post_missing_data_message(self, products: "odoo.model.product_template") -> None:
        for product in products:
            missing_fields = self._check_fields_and_images(product)
            if missing_fields:
                missing_fields_display = ", ".join(self._fields[f].string if "image" not in f.lower() else f for f in missing_fields)
                product.message_post(
                    body=f"Missing data: {missing_fields_display}",
                    subject="Import Error",
                    subtype_id=self.env.ref("mail.mt_note").id,
                    partner_ids=[self.env.user.partner_id.id],
                )

        self._safe_commit()

    def enable_ready_for_sale(self) -> None:
        products_missing_data = self.filtered(lambda p: p._check_fields_and_images(p))
        self._post_missing_data_message(products_missing_data)
        products_to_enable = self.filtered(lambda p: p.is_ready_to_list or p.source == "import")
        ready_to_enable_products = products_to_enable - products_missing_data

        if not ready_to_enable_products:
            raise UserError("No products are ready to sell. Check messages for details.")

        if products_missing_data:
            message = f"{len(products_missing_data)} product(s) are not ready to sell. Check messages for details."
            self.env["bus.bus"]._sendone(
                self.env.user.partner_id,
                "simple_notification",
                {"title": "Import Warning", "message": message, "sticky": False},
            )

        ready_to_enable_products.filtered(lambda p: p.condition and p.condition.name == "new").check_for_conflicting_products()

        for product in ready_to_enable_products:
            website_description = product.replace_template_tags(product.website_description or "")
            website_description = website_description.replace("{mpn}", " ".join(product.get_list_of_mpns()))
            product.website_description = website_description

            name = product.replace_template_tags(product.name or "")
            name = name.replace("{mpn}", product.first_mpn)
            product.name = name
            product.is_published = True

            product_variant = self.env["product.product"].search([("product_tmpl_id", "=", product.id)], limit=1)
            if product_variant:
                product_variant.update_quantity(product.initial_quantity)
            product.is_ready_for_sale = True
