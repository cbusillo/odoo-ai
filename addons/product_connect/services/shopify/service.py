import logging
from time import sleep
from httpx import Client, Timeout, Limits, Request, Response
from odoo.api import Environment

from .helpers import ShopifyApiError
from .gql import Client as ShopifyClient

THROTTLE_TRANSIENT_STATUS: set[int] = {429, 500, 502, 503, 504}

_logger = logging.getLogger(__name__)


class ShopifyService:
    MIN_API_POINTS = 500
    MAX_RETRY_ATTEMPTS = 10
    MIN_SLEEP_TIME = 1.0
    MAX_SLEEP_TIME = 60.0
    API_VERSION = "2026-01"

    def __init__(self, env: Environment, sync_record: "odoo.model.shopify_sync") -> None:
        self.env = env
        self._client: ShopifyClient | None = None
        self.sync_record = sync_record
        self.first_location_gid: str | None = None

    @property
    def client(self) -> ShopifyClient:
        if self._client is None:
            self._create_client()

        return self._client

    def get_first_location_gid(self, client: ShopifyClient | None = None) -> str:
        shopify = client or self.client
        shopify_response = shopify.get_locations()
        locations = shopify_response.nodes
        if not locations:
            raise ShopifyApiError("No locations found in the Shopify store.")

        location_gid = locations[0].id
        if not location_gid:
            raise ShopifyApiError("Location GID not found in the Shopify response.")

        return location_gid

    def _create_client(self) -> ShopifyClient:
        shop_url_key = self.env["ir.config_parameter"].sudo().get_param("shopify.shop_url_key")
        api_token = self.env["ir.config_parameter"].sudo().get_param("shopify.api_token")
        api_version = self.API_VERSION

        if not all([shop_url_key, api_token, api_version]):
            raise ShopifyApiError(
                "Shopify API credentials (shopify.shop_url_key, and shopify.api_token) are not set. Please configure them in the Odoo settings."
            )

        endpoint = f"https://{shop_url_key}.myshopify.com/admin/api/{api_version}/graphql.json"
        http_client = self._create_http_client(api_token)
        client = ShopifyClient(http_client=http_client, url=endpoint)
        first_location_gid = self.get_first_location_gid(client)
        self._client = client
        self.first_location_gid = first_location_gid
        return client

    def _create_http_client(self, api_token: str) -> Client:
        headers = {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": api_token,
        }
        timeout = Timeout(30.0, connect=10.0)
        limits = Limits(max_connections=25, max_keepalive_connections=25)

        def rate_limit_hook(response: Response) -> None:
            if not response.headers.get("content-type", "").startswith("application/json"):
                return

            if not response.is_closed:
                response.read()
            data = response.json()

            if "extensions" in data:
                throttle_status = data.get("extensions", {}).get("cost", {}).get("throttleStatus", {})
                currently_available = throttle_status.get("currentlyAvailable", 0)
                restore_rate = throttle_status.get("restoreRate", 1) or 1
                _logger.debug(f"Shopify API rate limit status: {throttle_status}")

                if currently_available < self.MIN_API_POINTS:
                    deficit = self.MIN_API_POINTS - currently_available
                    wait_time = min(self.MAX_SLEEP_TIME, max(deficit / restore_rate, self.MIN_SLEEP_TIME))
                    _logger.info(f"Low API points. Waiting for {wait_time:.2f} seconds...")
                    sleep(wait_time)

        client = Client(
            headers=headers,
            timeout=timeout,
            limits=limits,
            event_hooks={"response": [rate_limit_hook]},
            http2=True,
        )

        original_send = client.send

        def send_with_retry(request: Request, **kwargs: object) -> Response:
            transient = THROTTLE_TRANSIENT_STATUS

            for attempt in range(self.MAX_RETRY_ATTEMPTS + 1):
                response = original_send(request, **kwargs)
                status = response.status_code
                try:
                    if response.headers.get("content-type", "").startswith("application/json") and status == 200:
                        data = response.json()
                        hard_throttled, retry_after_seconds = self._throttle_info(data)

                        has_delay = retry_after_seconds is not None and retry_after_seconds > 0
                        should_retry = hard_throttled or has_delay

                        if should_retry:
                            if not retry_after_seconds or retry_after_seconds <= 0:
                                retry_after_seconds = min(
                                    self.MAX_SLEEP_TIME,
                                    max(self.MIN_SLEEP_TIME * 2**attempt, self.MIN_SLEEP_TIME),
                                )
                            _logger.info(f"GraphQL throttled – sync {self.sync_record.id} retrying in {retry_after_seconds:.2f}s")
                            response.close()
                            sleep(retry_after_seconds)
                            if hard_throttled:
                                self.sync_record.hard_throttle_count += 1
                            continue
                        return response
                    if status not in transient:
                        return response
                except ValueError:
                    if status not in transient:
                        return response
                response.close()
                if attempt == self.MAX_RETRY_ATTEMPTS:
                    break
                wait_time = min(self.MAX_SLEEP_TIME, self.MIN_SLEEP_TIME * 2**attempt)
                _logger.warning(
                    f"Retry {attempt + 1} for sync {self.sync_record.id} {request.url} ({status}); sleeping {wait_time:.2f}s"
                )
                sleep(wait_time)
            raise ShopifyApiError(f"Max retries reached for {request.url}")

        client.send = send_with_retry
        return client

    def _compute_throttle_delay(self, throttle_data: dict) -> float | None:
        throttle = throttle_data.get("extensions", {}).get("cost", {}).get("throttleStatus", {})
        if not throttle:
            return None
        available = throttle.get("currentlyAvailable", 0)
        if available >= self.MIN_API_POINTS:
            return 0.0
        rate = throttle.get("restoreRate", 1) or 1
        return max(
            min((self.MIN_API_POINTS - available) / rate, self.MAX_SLEEP_TIME),
            self.MIN_SLEEP_TIME,
        )

    def _throttle_info(self, response_data: dict) -> tuple[bool, float | None]:
        errors = response_data.get("errors", [])

        def _is_throttled(err: dict) -> bool:
            return err.get("extensions", {}).get("code", "").upper() == "THROTTLED" or str(
                err.get("message", "")
            ).strip().lower().startswith("throttled")

        throttled = any(_is_throttled(e) for e in errors)
        return throttled, self._compute_throttle_delay(response_data)
