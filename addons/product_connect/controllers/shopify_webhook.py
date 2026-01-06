import hmac, hashlib, base64, json

from odoo import http
from odoo.http import Response
from werkzeug.exceptions import Unauthorized, BadRequest

from ..services.shopify.helpers import SyncMode, ShopifyApiError


class ShopifyWebhook(http.Controller):
    PRODUCT_TOPICS = ("products/",)
    INVENTORY_TOPICS = ("inventory_items/", "inventory_levels/", "inventory/")
    ORDER_TOPICS = ("orders/",)
    CUSTOMER_TOPICS = ("customers/",)

    STATE_DOMAIN = ("state", "in", ["queued", "running"])
    SHOPIFY_LOGIN = "shopify@outboardpartswarehouse.com"

    @http.route("/shopify/webhook", type="http", auth="public", csrf=False, methods=["POST"])
    def webhook(self) -> Response:
        raw_body = http.request.httprequest.get_data()
        secret = http.request.env["ir.config_parameter"].sudo().get_param("shopify.webhook_key") or ""
        digest = hmac.new(
            secret.encode(),
            raw_body,
            hashlib.sha256,
        ).digest()
        signature_header = http.request.httprequest.headers.get("X-Shopify-Hmac-Sha256", "")
        if not hmac.compare_digest(base64.b64encode(digest).decode(), signature_header):
            raise Unauthorized()

        shopify_user = http.request.env["res.users"].sudo().search([("login", "=", self.SHOPIFY_LOGIN)], limit=1)
        if not shopify_user:
            message = f"Shopify user not found for login: {self.SHOPIFY_LOGIN}"
            exception = ShopifyApiError(message)
            http.request.env["notification.manager.mixin"].sudo().notify_channel_on_error(
                "Shopify Webhook Error", message, error=exception
            )
            raise exception
        env = http.request.env(user=shopify_user.id)

        topic = http.request.httprequest.headers.get("X-Shopify-Topic", "")
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError as decode_error:
            raise BadRequest() from decode_error
        if not payload.get("id"):
            raise BadRequest()

        if topic.startswith(self.PRODUCT_TOPICS + self.INVENTORY_TOPICS):
            env["shopify.sync"].create_and_run_async({"mode": SyncMode.IMPORT_THEN_EXPORT_PRODUCTS.value, "user": shopify_user.id})

        elif topic.startswith(self.ORDER_TOPICS):
            env["shopify.sync"].create_and_run_async({"mode": SyncMode.IMPORT_CHANGED_ORDERS.value, "user": shopify_user.id})

        elif topic.startswith(self.CUSTOMER_TOPICS):
            env["shopify.sync"].create_and_run_async({"mode": SyncMode.IMPORT_CHANGED_CUSTOMERS.value, "user": shopify_user.id})

        return http.Response(json.dumps({"status": "ok"}), content_type="application/json")
