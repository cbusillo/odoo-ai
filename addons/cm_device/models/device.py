from odoo import api, fields, models


class Device(models.Model):
    _name = "service.device"
    _description = "Service Device"
    _inherit = ["mail.thread", "mail.activity.mixin", "external.id.mixin"]
    _order = "serial_number asc, id desc"
    _rec_name = "serial_number"

    serial_number = fields.Char(tracking=True)
    asset_tag = fields.Char(tracking=True)
    asset_tag_secondary = fields.Char(tracking=True)
    imei = fields.Char(tracking=True)
    is_serial_unavailable = fields.Boolean(tracking=True)
    model = fields.Many2one(
        "service.device.model",
        required=True,
        ondelete="restrict",
    )
    owner = fields.Many2one(
        "res.partner",
        required=True,
        ondelete="restrict",
    )
    payer = fields.Many2one(
        "res.partner",
        ondelete="set null",
    )
    bin = fields.Char()
    is_in_manufacturer_warranty = fields.Boolean()
    invoices = fields.Many2many(
        "account.move",
        "device_account_move_rel",
        "device_id",
        "move_id",
        domain="[('move_type', 'in', ['out_invoice', 'out_refund'])]",
    )

    @api.model
    def cleanup_identifiers(self, *, batch_size: int = 5000, commit_interval: int = 5000) -> dict[str, int]:
        device_model = self.sudo()
        last_id = 0
        processed_count = 0
        updated_count = 0

        while True:
            devices = device_model.search([("id", ">", last_id)], order="id", limit=batch_size)
            if not devices:
                break
            for device in devices:
                update_values = self._build_cleanup_values(device)
                if update_values:
                    device.write(update_values)
                    updated_count += 1
                processed_count += 1
                if commit_interval and processed_count % commit_interval == 0:
                    self.env.cr.commit()
                    self.env.clear()
                    device_model = self.sudo()
            last_id = devices[-1].id

        return {
            "processed": processed_count,
            "updated": updated_count,
        }

    @classmethod
    def _build_cleanup_values(cls, device: "Device") -> dict[str, object]:
        serial_number = cls._clean_identifier_value(device.serial_number, identifier_type="serial")
        asset_tag = cls._clean_identifier_value(device.asset_tag, identifier_type="asset_tag")
        asset_tag_secondary = cls._clean_identifier_value(
            device.asset_tag_secondary,
            identifier_type="asset_tag",
        )
        imei = cls._clean_identifier_value(device.imei, identifier_type="imei")

        if asset_tag and serial_number and asset_tag == serial_number:
            asset_tag = None
        if asset_tag_secondary and serial_number and asset_tag_secondary == serial_number:
            asset_tag_secondary = None
        if asset_tag_secondary and asset_tag and asset_tag_secondary == asset_tag:
            asset_tag_secondary = None
        if imei and serial_number and imei == serial_number:
            imei = None
        if imei and asset_tag and imei == asset_tag:
            imei = None

        update_values: dict[str, object] = {}
        existing_serial = device.serial_number or None
        existing_asset = device.asset_tag or None
        existing_asset_secondary = device.asset_tag_secondary or None
        existing_imei = device.imei or None

        if existing_serial != serial_number:
            update_values["serial_number"] = serial_number
        if existing_asset != asset_tag:
            update_values["asset_tag"] = asset_tag
        if existing_asset_secondary != asset_tag_secondary:
            update_values["asset_tag_secondary"] = asset_tag_secondary
        if existing_imei != imei:
            update_values["imei"] = imei

        has_identifier = any([serial_number, asset_tag, asset_tag_secondary, imei])
        if not has_identifier and not device.is_serial_unavailable:
            update_values["is_serial_unavailable"] = True
        if has_identifier and device.is_serial_unavailable:
            update_values["is_serial_unavailable"] = False

        return update_values

    @staticmethod
    def _clean_identifier_value(value: str | None, *, identifier_type: str) -> str | None:
        if not value:
            return None
        cleaned = " ".join(str(value).strip().split())
        if not cleaned:
            return None
        normalized = cleaned.lower()
        if normalized in {"n/a", "na", "none", "unknown", "unk", "tbd", "null", "-"}:
            return None
        if identifier_type == "imei":
            digits = "".join(ch for ch in cleaned if ch.isdigit())
            return digits if len(digits) >= 8 else None
        if identifier_type in {"serial", "asset_tag"}:
            if len(cleaned) < 4:
                return None
            if not any(ch.isdigit() for ch in cleaned):
                return None
        return cleaned
