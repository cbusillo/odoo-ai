from contextlib import contextmanager
from typing import Iterator, Any
import logging
import secrets
import string

from odoo.models import BaseModel
from odoo.api import Environment
from odoo.tests import HttpCase, TransactionCase
from ..common_imports import (
    MagicMock,
    patch,
    DEFAULT_TEST_CONTEXT,
    tagged,
    UNIT_TAGS,
    INTEGRATION_TAGS,
    TOUR_TAGS,
)

_logger = logging.getLogger(__name__)


class _ShopifyMockMixin:
    def _setup_shopify_mocks(self) -> None:
        self.shopify_service_patcher = patch("odoo.addons.product_connect.services.shopify.sync.base.ShopifyService")
        self.mock_shopify_service_class = self.shopify_service_patcher.start()

        self.mock_client = MagicMock()
        self.mock_service_instance = MagicMock()
        self.mock_service_instance.client = self.mock_client
        self.mock_service_instance.first_location_gid = "gid://shopify/Location/12345"
        self.mock_service_instance.get_first_location_gid.return_value = "gid://shopify/Location/12345"

        self.mock_shopify_service_class.return_value = self.mock_service_instance

    def _teardown_shopify_mocks(self) -> None:
        if hasattr(self, "shopify_service_patcher") and self.shopify_service_patcher:
            self.shopify_service_patcher.stop()


@tagged(*UNIT_TAGS)
class UnitTestCase(_ShopifyMockMixin, TransactionCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.env = cls.env(user=cls.env.ref("base.user_admin"))
        cls.env = cls.env(
            context=dict(
                cls.env.context,
                **DEFAULT_TEST_CONTEXT,
            )
        )
        cls._reset_sku_sequence()

    @classmethod
    def _reset_sku_sequence(cls) -> None:
        """Reset SKU sequence to avoid exhaustion during test runs"""
        sequence = cls.env["ir.sequence"].search([("code", "=", "product.template.default_code")], limit=1)
        if sequence:
            # Reset to 8000 to give plenty of room for test SKUs (991999 available)
            sequence.sudo().write({"number_next": 8000})

    def tearDown(self) -> None:
        self._teardown_shopify_mocks()
        super().tearDown()

    def mock_service(self, service_path: str) -> MagicMock:
        patcher = patch(service_path)
        mock = patcher.start()
        self.addCleanup(patcher.stop)
        return mock

    @contextmanager
    def mock_shopify_client(self) -> Iterator[MagicMock]:
        with patch("addons.product_connect.services.shopify.client.GraphQLClient") as mock_client:
            instance = MagicMock()
            mock_client.return_value = instance
            yield instance

    def assertRecordValues(self, record: BaseModel, expected_values: dict) -> None:
        for field, expected in expected_values.items():
            actual = record[field]
            if hasattr(actual, "id"):
                actual = actual.id
            elif hasattr(actual, "ids"):
                actual = actual.ids

            self.assertEqual(actual, expected, f"Field '{field}' mismatch: expected {expected}, got {actual}")


def _get_or_create_geo_data(env: Environment) -> tuple[Any, Any, Any]:
    usa_country = env["res.country"].search([("code", "=", "US")], limit=1)
    if not usa_country:
        usa_country = env["res.country"].create({"name": "United States", "code": "US", "phone_code": 1})

    ny_state = env["res.country.state"].search([("code", "=", "NY"), ("country_id", "=", usa_country.id)], limit=1)
    if not ny_state:
        ny_state = env["res.country.state"].create({"name": "New York", "code": "NY", "country_id": usa_country.id})

    shopify_category = env["res.partner.category"].search([("name", "=", "Shopify")], limit=1)
    if not shopify_category:
        shopify_category = env["res.partner.category"].create({"name": "Shopify"})

    return usa_country, ny_state, shopify_category


class _BaseDataMixin:
    env: Environment

    def _setup_base_data(self) -> None:
        self.usa_country, self.ny_state, self.shopify_category = _get_or_create_geo_data(self.env)

    @classmethod
    def _setup_class_base_data(cls) -> None:
        cls.usa_country, cls.ny_state, cls.shopify_category = _get_or_create_geo_data(cls.env)


@tagged(*INTEGRATION_TAGS)
class IntegrationTestCase(_ShopifyMockMixin, _BaseDataMixin, TransactionCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.env = cls.env(user=cls.env.ref("base.user_admin"))
        test_context = DEFAULT_TEST_CONTEXT.copy()
        test_context["skip_shopify_sync"] = True
        cls.env = cls.env(
            context=dict(
                cls.env.context,
                **test_context,
            )
        )
        cls._setup_test_data()

    @classmethod
    def _setup_test_data(cls) -> None:
        cls.test_company = cls.env.ref("base.main_company")

        cls.test_warehouse = cls.env["stock.warehouse"].search([("company_id", "=", cls.test_company.id)], limit=1)

        cls.test_pricelist = cls.env["product.pricelist"].search([("currency_id.name", "=", "USD")], limit=1)
        if not cls.test_pricelist:
            cls.test_pricelist = cls.env["product.pricelist"].create(
                {
                    "name": "Test Pricelist",
                    "currency_id": cls.env.ref("base.USD").id,
                }
            )

        cls._setup_class_base_data()
        cls._reset_sku_sequence()

    @classmethod
    def _reset_sku_sequence(cls) -> None:
        """Reset SKU sequence to avoid exhaustion during test runs"""
        sequence = cls.env["ir.sequence"].search([("code", "=", "product.template.default_code")], limit=1)
        if sequence:
            # Reset to 8000 to give plenty of room for test SKUs (991999 available)
            sequence.sudo().write({"number_next": 8000})

    def create_shopify_credentials(self) -> None:
        config_param = self.env["ir.config_parameter"].sudo()
        config_param.set_param("shopify.shop_url_key", "test-store.myshopify.com")
        config_param.set_param("shopify.webhook_key", "test_webhook_key")
        config_param.set_param("shopify.test_store", "1")

    @staticmethod
    def mock_shopify_response(
        data: dict[str, object] | None = None,
        errors: list[dict[str, str]] | None = None,
    ) -> dict[str, dict[str, object] | list[dict[str, str]]]:
        response: dict[str, dict[str, object] | list[dict[str, str]]] = {"data": data or {}}
        if errors is not None:
            response["errors"] = errors
        return response

    def tearDown(self) -> None:
        self._teardown_shopify_mocks()
        super().tearDown()


class MultiWorkerHttpCase(HttpCase):
    """HttpCase that works with multi-worker mode (--workers > 0)."""

    @classmethod
    def http_port(cls) -> int | None:
        """Override to work with PreforkServer in multi-worker mode."""
        import odoo.service.server

        if odoo.service.server.server is None:
            return None

        server = odoo.service.server.server

        # Handle single-worker mode (has httpd attribute)
        if hasattr(server, "httpd"):
            return server.httpd.server_port

        # Handle multi-worker mode (PreforkServer)
        # Use the configured port from tools.config
        from odoo.tools import config

        return int(config.get("http_port", 8069))


@tagged(*TOUR_TAGS)
class TourTestCase(MultiWorkerHttpCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param("ir_attachment.location", "db")
        cls.env["ir.attachment"].sudo().search([("url", "ilike", "/web/assets/")]).unlink()
        cls._setup_test_user()
        cls._cleanup_browser_processes()

    @classmethod
    def _cleanup_browser_processes(cls) -> None:
        """Clean up any existing browser processes to prevent accumulation."""
        import subprocess

        try:
            # Kill any zombie chromium processes
            subprocess.run(["pkill", "-f", "chromium"], capture_output=True, timeout=5)
            subprocess.run(["pkill", "-f", "chrome"], capture_output=True, timeout=5)
            _logger.info("Cleaned up existing browser processes")
        except Exception as e:
            _logger.warning(f"Failed to cleanup browser processes: {e}")

    @classmethod
    def _setup_test_user(cls) -> None:
        """Create or configure a secure test user with dynamically generated password."""
        # Generate cryptographically secure password
        password_chars = string.ascii_letters + string.digits
        cls.test_password = "".join(secrets.choice(password_chars) for _ in range(20))

        # Find or create test user
        test_user = cls.env["res.users"].search([("login", "=", "tour_test_user")], limit=1)

        if not test_user:
            # Create new test user
            system_group = cls.env.ref("base.group_system")
            # Some modules (e.g., discuss_record_links) reuse this base without 'stock' installed.
            # Make the stock manager group optional to avoid hard dependency in JS/tour tests.
            try:
                stock_manager = cls.env.ref("stock.group_stock_manager")
            except Exception:  # ValueError when external id not found
                stock_manager = None

            group_ids = [system_group.id] + ([stock_manager.id] if stock_manager else [])
            test_user = cls.env["res.users"].create(
                {
                    "name": "Tour Test User",
                    "login": "tour_test_user",
                    "email": "tour_test@example.com",
                    "password": cls.test_password,
                    # Ensure the user can access features used by tours; 'stock' is optional
                    "group_ids": [(6, 0, group_ids)],
                    "active": True,
                }
            )
            _logger.info("Created new tour test user with system permissions")
        else:
            # Update existing test user password
            test_user.sudo().write(
                {
                    "password": cls.test_password,
                    "active": True,
                }
            )
            # Ensure user has system permissions (stock group is optional)
            system_group = cls.env.ref("base.group_system")
            try:
                stock_manager = cls.env.ref("stock.group_stock_manager")
            except Exception:
                stock_manager = None
            to_add = []
            if system_group not in test_user.group_ids:
                to_add.append(system_group.id)
            if stock_manager and stock_manager not in test_user.group_ids:
                to_add.append(stock_manager.id)
            if to_add:
                test_user.sudo().write({"group_ids": [(4, gid) for gid in to_add]})
            _logger.info("Updated existing tour test user with new secure password")

        cls.test_user = test_user
        _logger.info("Tour test user configured successfully")

    def _get_test_login(self) -> str:
        """Get the secure test user login."""
        if hasattr(self, "test_user") and self.test_user:
            return self.test_user.login
        return "tour_test_user"

    def _with_db_param(self, url: str) -> str:
        if "db=" in url:
            return url
        from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query["db"] = self.env.cr.dbname
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))

    def setUp(self) -> None:
        super().setUp()
        self.browser_size = "1920x1080"
        # Allow overriding tour timeout via env var TOUR_TIMEOUT (seconds)
        import os as _os  # noqa: PLC0415

        self.tour_timeout = int(_os.environ.get("TOUR_TIMEOUT", "120"))
        self._setup_browser_environment()
        # Optional HTTP warmup: disabled by default to avoid long timeouts on busy CI.
        # Enable by setting TOUR_WARMUP=1 in environment.
        import os as _os

        if _os.environ.get("TOUR_WARMUP", "0") != "0":
            try:
                import requests
                import time

                port = self.http_port()
                base = f"http://127.0.0.1:{port}"

                # Fail fast: shorter per-attempt timeout and fewer retries
                def warm(url: str, retries: int = 2, timeout: int = 15, delay: float = 1.0) -> None:
                    for attempt in range(1, retries + 1):
                        try:
                            _logger.info(f"Warm-up [{attempt}/{retries}]: GET {url} (timeout={timeout}s)")
                            resp = requests.get(url, timeout=timeout)
                            if resp.status_code < 500:
                                return
                            _logger.warning(f"Warm-up {url} returned HTTP {resp.status_code}")
                        except Exception as e:
                            _logger.warning(f"Warm-up attempt {attempt} failed for {url}: {e}")
                        time.sleep(delay)

                # Warm minimal endpoints first, then the JS tests harness to avoid 20s DevTools navigate timeouts
                warm(base + self._with_db_param("/web"))
                # Preload the hoot/QUnit test harness & assets for our module
                warm(base + self._with_db_param("/web/tests?headless=1&filter=product_connect"))
            except Exception as outer:
                _logger.warning(f"Warm-up setup skipped due to error: {outer}")

    def _setup_browser_environment(self) -> None:
        """Configure browser environment for headless operation."""
        import os

        # Set essential browser environment variables for tour testing
        # Don't override existing container environment variables unless needed
        browser_env = {
            "HEADLESS_CHROMIUM": "1",
            "CHROMIUM_BIN": "/usr/bin/chromium",
            # Use more aggressive flags to prevent hangs in container environment
            "CHROMIUM_FLAGS": "--headless=new --no-sandbox --disable-gpu --disable-dev-shm-usage --disable-software-rasterizer --window-size=1920,1080 --no-first-run --no-default-browser-check --disable-web-security --disable-features=VizDisplayCompositor,TranslateUI,site-per-process,IsolateOrigins,BlockInsecurePrivateNetworkRequests --virtual-time-budget=30000 --run-all-compositor-stages-before-draw --disable-background-timer-throttling --disable-renderer-backgrounding --disable-backgrounding-occluded-windows",
        }
        for key, value in browser_env.items():
            # Only set if not already defined in container environment
            if key not in os.environ or not os.environ[key]:
                os.environ[key] = value

        # Optional extra Chrome verbosity for debugging DevTools navigation/connectivity issues
        # Enable via JS_DEBUG=1 in the environment.
        if os.environ.get("JS_DEBUG", "0") != "0":
            extra = "--enable-logging=stderr --v=1"
            current = os.environ.get("CHROMIUM_FLAGS", "").strip()
            if extra not in current:
                os.environ["CHROMIUM_FLAGS"] = (current + " " + extra).strip()

        _logger.info(f"Browser environment configured: CHROMIUM_FLAGS={os.environ.get('CHROMIUM_FLAGS', 'not set')}")

    def start_tour(
        self, url: str, tour_name: str, login: str | None = None, timeout: int | None = None, step_delay: float = 0.5
    ) -> None:
        """Start tour with improved error handling and timeout management."""
        if timeout is None:
            timeout = self.tour_timeout
        # Default to our prepared test user if none provided
        if login is None:
            login = self.test_user.login

        _logger.info(f"Starting tour '{tour_name}' at '{url}' with user '{login}' (timeout: {timeout}s)")

        try:
            # Clean up any existing browser processes before starting
            self._cleanup_browser_processes()

            # Optional warm-up: honor TOUR_WARMUP env (default disabled for speed/stability)
            import os as _os

            if _os.environ.get("TOUR_WARMUP", "0") != "0":
                try:
                    import requests

                    port = self.http_port()
                    base = f"http://127.0.0.1:{port}"
                    for path in ("/web",):
                        warm_url = base + path
                        _logger.info(f"Warming up server with GET {warm_url}")
                        requests.get(warm_url, timeout=30)
                except Exception as warm_err:
                    _logger.warning(f"Warm-up request failed (will proceed anyway): {warm_err}")

            # Use Odoo's built-in implementation with timeout handling
            url_with_db = self._with_db_param(url)
            super().start_tour(url_with_db, tour_name, login=login, timeout=timeout, step_delay=step_delay)

        except Exception as e:
            _logger.error(f"Tour '{tour_name}' failed: {e}")
            # Clean up after failure
            self._cleanup_browser_processes()
            raise
        finally:
            # Always clean up browser processes after tour completes
            self._cleanup_browser_processes()

    def register_tour(self, tour_definition: dict) -> None:
        """Register a tour definition (placeholder for compatibility)."""
        pass

    def take_screenshot(self, name: str = "screenshot") -> None:
        """Take a screenshot during tour execution (placeholder for compatibility)."""
        pass
