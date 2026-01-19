import logging
import traceback

from odoo import api, fields, models
from odoo.addons.mail.models.mail_thread import MailThread
from pydantic import BaseModel

_logger = logging.getLogger(__name__)


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


class NotificationManagerMixin(models.AbstractModel):
    _name = "notification.manager.mixin"
    _inherit = ["transaction.mixin"]
    _description = "Notification Manager Mixin"

    ADMIN_EMAIL = "info@shinycomputers.com"

    def notify_channel(
        self,
        subject: str,
        body: str,
        channel_name: str,
        record: models.Model | None = None,
        shopify_record: BaseModel | None = None,
        env: api.Environment | None = None,
        error: Exception | str | None = None,
    ) -> None:
        error_traceback = (
            "".join(traceback.format_exception(type(error), error, error.__traceback__)) if isinstance(error, Exception) else error
        )
        env = env or self.env
        notification_history = env["notification.history"].sudo()
        channel = env["discuss.channel"].sudo().search([("name", "=", channel_name)], limit=1)
        if not channel:
            channel = env["discuss.channel"].sudo().create({"name": channel_name})

        if notification_history.count_of_recent_notifications(subject, channel, 1) >= 5:
            _logger.info(f"Too many notifications for {subject} in the last hour.")
            return

        if error_traceback:
            body += "\n\nError traceback:\n"
            body += error_traceback

        _logger.debug(
            "Sending message to channel %s with message %s for record %s and shopify record %s",
            channel,
            body,
            record,
            shopify_record,
        )
        if shopify_record:
            body += f"\nShopify record: {shopify_record}"

        body = body.replace("\n", "<br/>")
        post_values: "odoo.values.mail_message" = {
            "body": body,
            "subject": subject,
            "message_type": "comment",
            "subtype_id": self.env.ref("mail.mt_comment").id,
        }

        if record and isinstance(record, MailThread):
            record.sudo().message_post(body_is_html=True, **post_values)
        channel.sudo().message_post(body_is_html=True, **post_values)

        notification_history.create({"subject": subject, "channel": channel.id})

    def notify_channel_on_error(
        self,
        subject: str,
        body: str,
        record: models.Model | None = None,
        shopify_record: BaseModel | None = None,
        error: Exception | None = None,
    ) -> None:
        self._safe_rollback()
        error_traceback = "".join(traceback.format_exception(type(error), error, error.__traceback__)) if error else ""

        with self._new_cursor_context() as new_env:
            self.notify_channel(subject, body, "errors", record, shopify_record, new_env, error)
            message = f"{body}"
            if record:
                message += f"\nRecord: {record}"
            if shopify_record:
                message += f"\nShopify record: {shopify_record}"
            if error_traceback:
                message += f"\nError traceback:\n{error_traceback}"
            self.send_email_notification_to_admin(subject, message)

    def send_email_notification_to_admin(self, subject: str, body: str) -> None:
        recipient_user = self.env["res.users"].sudo().search([("login", "=", self.ADMIN_EMAIL)], limit=1)
        if not recipient_user:
            _logger.error("Recipient email %s not found among partners.", self.ADMIN_EMAIL)
            return

        mail_values = {
            "subject": subject,
            "body_html": f"<div>{body}</div>",
            "recipient_ids": [(4, recipient_user.id)],
            "email_from": self.env["ir.mail_server"].sudo().search([], limit=1).smtp_user,
        }
        mail = self.env["mail.mail"].sudo().create(mail_values)
        mail.send()
