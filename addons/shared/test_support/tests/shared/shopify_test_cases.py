import contextlib
import logging
import secrets
import string
from typing import Any, ClassVar, Iterator
from unittest.mock import MagicMock, patch

from odoo.api import Environment
from odoo.models import BaseModel
from odoo.tests import HttpCase, TransactionCase

_logger = logging.getLogger(__name__)


def _build_admin_test_environment(
    environment: Environment,
    context_values: dict[str, Any],
) -> Environment:
    admin_environment = environment(user=environment.ref("base.user_admin"))
    return admin_environment(context=dict(admin_environment.context, **context_values))


def _reset_default_code_sequence(environment: Environment) -> None:
    """Reset SKU sequence to avoid exhaustion during repeated test runs."""
    sequence_record = environment["ir.sequence"].search(
        [("code", "=", "product.template.default_code")],
        limit=1,
    )
    if sequence_record:
        sequence_record.sudo().write({"number_next": 8000})


def _get_or_create_geo_data(environment: Environment) -> tuple[Any, Any, Any]:
    usa_country = environment["res.country"].search([("code", "=", "US")], limit=1)
    if not usa_country:
        usa_country = environment["res.country"].create(
            {
                "name": "United States",
                "code": "US",
                "phone_code": 1,
            }
        )

    new_york_state = environment["res.country.state"].search(
        [("code", "=", "NY"), ("country_id", "=", usa_country.id)],
        limit=1,
    )
    if not new_york_state:
        new_york_state = environment["res.country.state"].create(
            {
                "name": "New York",
                "code": "NY",
                "country_id": usa_country.id,
            }
        )

    shopify_category = environment["res.partner.category"].search([("name", "=", "Shopify")], limit=1)
    if not shopify_category:
        shopify_category = environment["res.partner.category"].create({"name": "Shopify"})

    return usa_country, new_york_state, shopify_category


class ShopifyMockMixin:
    shopify_service_patcher: Any

    def _setup_shopify_mocks(self) -> None:
        self.shopify_service_patcher = patch("odoo.addons.shopify_sync.services.shopify.sync.base.ShopifyService")
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


class ShopifyBaseDataMixin:
    env: Environment

    def _setup_base_data(self) -> None:
        self.usa_country, self.ny_state, self.shopify_category = _get_or_create_geo_data(self.env)

    @classmethod
    def _setup_class_base_data(cls) -> None:
        cls.usa_country, cls.ny_state, cls.shopify_category = _get_or_create_geo_data(cls.env)


class ShopifyUnitTestCaseBase(ShopifyMockMixin, TransactionCase):
    default_test_context: ClassVar[dict[str, Any]] = {}

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.env = _build_admin_test_environment(
            cls.env,
            dict(cls.default_test_context),
        )
        cls._reset_sku_sequence()

    @classmethod
    def _reset_sku_sequence(cls) -> None:
        _reset_default_code_sequence(cls.env)

    def tearDown(self) -> None:
        self._teardown_shopify_mocks()
        super().tearDown()

    def mock_service(self, service_path: str) -> MagicMock:
        service_patcher = patch(service_path)
        mocked_service = service_patcher.start()
        self.addCleanup(service_patcher.stop)
        return mocked_service

    @contextlib.contextmanager
    def mock_shopify_client(self) -> Iterator[MagicMock]:
        with patch("odoo.addons.shopify_sync.services.shopify.service.ShopifyClient") as mock_client_class:
            client_instance = MagicMock()
            mock_client_class.return_value = client_instance
            yield client_instance

    def assertRecordValues(
        self,
        record: BaseModel,
        expected_values: dict[str, Any],
        msg: str | None = None,
    ) -> None:
        for field_name, expected_value in expected_values.items():
            actual_value = record[field_name]
            if hasattr(actual_value, "id"):
                actual_value = actual_value.id
            elif hasattr(actual_value, "ids"):
                actual_value = actual_value.ids

            message = msg or f"Field '{field_name}' mismatch: expected {expected_value}, got {actual_value}"
            self.assertEqual(actual_value, expected_value, message)


class ShopifyIntegrationTestCaseBase(ShopifyMockMixin, ShopifyBaseDataMixin, TransactionCase):
    default_test_context: ClassVar[dict[str, Any]] = {}
    enforce_test_company_country: ClassVar[bool] = True

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        integration_context = dict(cls.default_test_context)
        integration_context["skip_shopify_sync"] = True
        cls.env = _build_admin_test_environment(cls.env, integration_context)
        cls._setup_test_data()

    @classmethod
    def _setup_test_data(cls) -> None:
        cls.test_company = cls.env.ref("base.main_company")
        cls.test_warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.test_company.id)],
            limit=1,
        )

        cls.test_pricelist = cls.env["product.pricelist"].search([("currency_id.name", "=", "USD")], limit=1)
        if not cls.test_pricelist:
            cls.test_pricelist = cls.env["product.pricelist"].create(
                {
                    "name": "Test Pricelist",
                    "currency_id": cls.env.ref("base.USD").id,
                }
            )

        cls._setup_class_base_data()
        if cls.enforce_test_company_country and cls.test_company.country_id != cls.usa_country:
            cls.test_company.write({"country_id": cls.usa_country.id})
        cls._reset_sku_sequence()

    @classmethod
    def _reset_sku_sequence(cls) -> None:
        _reset_default_code_sequence(cls.env)

    def create_shopify_credentials(self) -> None:
        config_parameter = self.env["ir.config_parameter"].sudo()
        config_parameter.set_param("shopify.shop_url_key", "test-store.myshopify.com")
        config_parameter.set_param("shopify.webhook_key", "test_webhook_key")
        config_parameter.set_param("shopify.test_store", "1")

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


class MultiWorkerHttpCaseBase(HttpCase):
    """HttpCase that works with multi-worker mode (--workers > 0)."""

    @classmethod
    def http_port(cls) -> int | None:
        """Resolve HTTP port for both single-worker and PreforkServer modes."""
        import odoo.service.server

        if odoo.service.server.server is None:
            return None

        server = odoo.service.server.server
        if hasattr(server, "httpd"):
            return server.httpd.server_port

        from odoo.tools import config

        return int(config.get("http_port", 8069))


class ShopifyTourTestCaseBase(MultiWorkerHttpCaseBase):
    reset_assets_per_database: ClassVar[bool] = False
    optional_group_xmlids: ClassVar[tuple[str, ...]] = ("stock.group_stock_manager",)
    assets_reset_db_names: ClassVar[set[str]] = set()

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param("ir_attachment.location", "db")
        cls._reset_web_assets_cache()
        cls._setup_test_user()
        cls._ensure_required_domain_data()
        cls._cleanup_browser_processes()

    @classmethod
    def _reset_web_assets_cache(cls) -> None:
        if cls.reset_assets_per_database:
            database_name = cls.env.cr.dbname
            if database_name in cls.assets_reset_db_names:
                return
            cls.env["ir.attachment"].sudo().search([("url", "ilike", "/web/assets/")]).unlink()
            cls.assets_reset_db_names.add(database_name)
            return

        cls.env["ir.attachment"].sudo().search([("url", "ilike", "/web/assets/")]).unlink()

    @classmethod
    def _ensure_required_domain_data(cls) -> None:
        """Hook for addons that need extra domain records before tours run."""

    @classmethod
    def _cleanup_browser_processes(cls) -> None:
        """Clean up existing browser processes to prevent accumulation."""
        import subprocess

        try:
            subprocess.run(["pkill", "-f", "chromium"], capture_output=True, timeout=5)
            subprocess.run(["pkill", "-f", "chrome"], capture_output=True, timeout=5)
            _logger.info("Cleaned up existing browser processes")
        except Exception as cleanup_error:  # pragma: no cover - defensive logging
            _logger.warning(f"Failed to cleanup browser processes: {cleanup_error}")

    @classmethod
    def _resolve_optional_group_ids(cls) -> list[int]:
        group_ids: list[int] = []
        for group_xmlid in cls.optional_group_xmlids:
            try:
                group_record = cls.env.ref(group_xmlid)
            except ValueError:
                _logger.debug("Skipping optional group xmlid %s (not installed)", group_xmlid)
                continue
            group_ids.append(group_record.id)
        return group_ids

    @classmethod
    def _setup_test_user(cls) -> None:
        """Create or configure a secure test user with dynamically generated password."""
        password_characters = string.ascii_letters + string.digits
        cls.test_password = "".join(secrets.choice(password_characters) for _ in range(20))

        test_user = cls.env["res.users"].search([("login", "=", "tour_test_user")], limit=1)
        required_group_ids = [cls.env.ref("base.group_system").id] + cls._resolve_optional_group_ids()

        if not test_user:
            test_user = cls.env["res.users"].create(
                {
                    "name": "Tour Test User",
                    "login": "tour_test_user",
                    "email": "tour_test@example.com",
                    "password": cls.test_password,
                    "group_ids": [(6, 0, required_group_ids)],
                    "active": True,
                }
            )
            _logger.info("Created new tour test user with system permissions")
        else:
            test_user.sudo().write(
                {
                    "password": cls.test_password,
                    "active": True,
                }
            )
            missing_group_commands = [(4, group_id) for group_id in required_group_ids if group_id not in test_user.group_ids.ids]
            if missing_group_commands:
                test_user.sudo().write({"group_ids": missing_group_commands})
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

        from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

        url_parts = urlsplit(url)
        query_values = dict(parse_qsl(url_parts.query, keep_blank_values=True))
        query_values["db"] = self.env.cr.dbname
        return urlunsplit(
            (
                url_parts.scheme,
                url_parts.netloc,
                url_parts.path,
                urlencode(query_values),
                url_parts.fragment,
            )
        )

    def _browser_http_url(self, path_or_url: str) -> str:
        from ..fixtures.base_cases import browser_http_url

        return browser_http_url(self, path_or_url)

    def wait_for_browser_endpoint(self, path_or_url: str, timeout_seconds: int = 60) -> None:
        from ..fixtures.base_cases import wait_for_browser_endpoint

        wait_for_browser_endpoint(self, path_or_url, timeout_seconds)

    @staticmethod
    def preflight_get(path_or_url: str, timeout_seconds: int = 10) -> tuple[int, float, int, str]:
        from ..fixtures.base_cases import preflight_get

        return preflight_get(path_or_url, timeout_seconds)

    def run_browser_js_suite(
        self,
        url: str,
        *,
        success_signal: str,
        error_checker: Any,
        timeout: int = 900,
        retry_timeout: int | None = None,
        recoverable_exceptions: tuple[type[BaseException], ...] = (Exception,),
    ) -> None:
        from ..fixtures.base_cases import run_browser_js_suite

        run_browser_js_suite(
            self,
            url,
            success_signal=success_signal,
            error_checker=error_checker,
            timeout=timeout,
            retry_timeout=retry_timeout,
            recoverable_exceptions=recoverable_exceptions,
        )

    def setUp(self) -> None:
        super().setUp()
        self.browser_size = "1920x1080"

        import os as os_module

        self.tour_timeout = int(os_module.environ.get("TOUR_TIMEOUT", "120"))
        self.tour_step_delay_seconds = float(os_module.environ.get("TOUR_STEP_DELAY_SECONDS", "0"))
        self._setup_browser_environment()

    @staticmethod
    def _setup_browser_environment() -> None:
        """Configure browser environment for headless operation."""
        import os

        browser_environment = {
            "HEADLESS_CHROMIUM": "1",
            "CHROMIUM_BIN": "/usr/bin/chromium",
            "CHROMIUM_FLAGS": "--headless=new --no-sandbox --disable-gpu --disable-dev-shm-usage --disable-software-rasterizer --window-size=1920,1080 --no-first-run --no-default-browser-check --disable-web-security --disable-features=VizDisplayCompositor,TranslateUI,site-per-process,IsolateOrigins,BlockInsecurePrivateNetworkRequests --virtual-time-budget=30000 --run-all-compositor-stages-before-draw --disable-background-timer-throttling --disable-renderer-backgrounding --disable-backgrounding-occluded-windows",
        }
        for environment_key, environment_value in browser_environment.items():
            if environment_key not in os.environ or not os.environ[environment_key]:
                os.environ[environment_key] = environment_value

        if os.environ.get("JS_DEBUG", "0") != "0":
            extra_flags = "--enable-logging=stderr --v=1"
            current_flags = os.environ.get("CHROMIUM_FLAGS", "").strip()
            if extra_flags not in current_flags:
                os.environ["CHROMIUM_FLAGS"] = (current_flags + " " + extra_flags).strip()

        _logger.info("Browser environment configured: CHROMIUM_FLAGS=%s", os.environ.get("CHROMIUM_FLAGS", "not set"))

    def start_tour(
        self,
        url: str,
        tour_name: str,
        login: str | None = None,
        timeout: int | None = None,
        step_delay: float | None = None,
    ) -> None:
        """Start tour with improved error handling and timeout management."""
        if timeout is None:
            timeout = self.tour_timeout
        if step_delay is None:
            step_delay = self.tour_step_delay_seconds
        if login is None:
            login = self.test_user.login

        _logger.info("Starting tour '%s' at '%s' with user '%s' (timeout: %ss)", tour_name, url, login, timeout)

        try:
            self._cleanup_browser_processes()
            url_with_database = self._with_db_param(url)
            super().start_tour(url_with_database, tour_name, login=login, timeout=timeout, step_delay=step_delay)
        except Exception as tour_error:
            _logger.error("Tour '%s' failed: %s", tour_name, tour_error)
            self._cleanup_browser_processes()
            raise
        finally:
            self._cleanup_browser_processes()

    def register_tour(self, tour_definition: dict[str, Any]) -> None:  # noqa: ARG002
        """Register a tour definition (placeholder for compatibility)."""

    def take_screenshot(self, name: str = "screenshot") -> None:  # noqa: ARG002
        """Take a screenshot during tour execution (placeholder for compatibility)."""


__all__ = [
    "ShopifyIntegrationTestCaseBase",
    "ShopifyTourTestCaseBase",
    "ShopifyUnitTestCaseBase",
]
