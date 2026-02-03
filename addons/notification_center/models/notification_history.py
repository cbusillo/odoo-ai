from odoo import api, fields, models


class NotificationHistory(models.Model):
    _name = "notification.history"
    _description = "Notification History"

    subject = fields.Char(required=True)
    timestamp = fields.Datetime(default=fields.Datetime.now, required=True)
    channel = fields.Many2one("discuss.channel", required=True)

    @api.model_create_multi
    def create(self, vals_list: list["odoo.values.notification_history"]) -> "odoo.model.notification_history":
        history_records = super().create(vals_list)
        self.cleanup()
        return history_records

    @api.model
    def cleanup(self) -> None:
        cutoff = fields.Datetime.subtract(fields.Datetime.now(), days=1)
        channels = self.env["discuss.channel"].sudo().search([("name", "in", ["errors", "shopify_sync"])])
        for channel in channels:
            self.search([("timestamp", "<", cutoff), ("channel", "=", channel.id)]).unlink()

        self.search([("timestamp", "<", cutoff)]).unlink()

    @api.model
    def count_of_recent_notifications(self, subject: str, channel: "odoo.model.discuss_channel", hours: int) -> int:
        cleanup_cutoff = fields.Datetime.subtract(fields.Datetime.now(), hours=hours)
        count = self.search_count(
            [
                ("timestamp", ">=", cleanup_cutoff),
                ("subject", "ilike", subject),
                ("channel", "=", channel.id),
            ]
        )
        return count

    @api.model
    def recent_notifications(self, subject: str, channel: "odoo.model.discuss_channel", hours: int) -> "NotificationHistory":
        time_frame = fields.Datetime.subtract(fields.Datetime.now(), hours=hours)
        return self.search([("timestamp", ">=", time_frame), ("subject", "ilike", subject), ("channel", "=", channel.id)])
