import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager

from odoo.exceptions import ValidationError

from ...models.environment_overrides import _normalize_config_param_value, _parse_boolean
from ..common_imports import UNIT_TAGS, tagged
from ..fixtures.base import UnitTestCase


@contextmanager
def _set_env(values: Mapping[str, str | None]) -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in values}
    for key, value in values.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@tagged(*UNIT_TAGS)
class TestEnvironmentOverrides(UnitTestCase):
    def test_normalize_config_param_value(self) -> None:
        self.assertEqual(_normalize_config_param_value(" true "), "True")
        self.assertEqual(_normalize_config_param_value("false"), "False")
        self.assertEqual(_normalize_config_param_value(" 123 "), "123")

    def test_normalize_config_param_value_preserves_json_like_values(self) -> None:
        self.assertEqual(_normalize_config_param_value("[1, 2]"), "[1, 2]")
        self.assertEqual(_normalize_config_param_value('{"mode": "test"}'), '{"mode": "test"}')
        self.assertEqual(_normalize_config_param_value("{not json}"), "{not json}")

    def test_parse_boolean(self) -> None:
        self.assertTrue(_parse_boolean(None, default=True))
        self.assertFalse(_parse_boolean(None, default=False))
        self.assertTrue(_parse_boolean("yes", default=False))
        self.assertFalse(_parse_boolean("0", default=True))

    def test_parse_boolean_uses_default_for_unknown_values(self) -> None:
        self.assertTrue(_parse_boolean("maybe", default=True))
        self.assertFalse(_parse_boolean("maybe", default=False))

    def test_apply_config_param_overrides(self) -> None:
        with _set_env({"ENV_OVERRIDE_CONFIG_PARAM__TEST__VALUE": "true"}):
            self.Overrides._apply_config_param_overrides()

        self.assertEqual(self.ConfigParameter.get_param("test.value"), "True")

    def test_shopify_overrides_rejects_production_urls(self) -> None:
        env_values = {
            "ENV_OVERRIDE_SHOPIFY__SHOP_URL_KEY": "prod-store",
            "ENV_OVERRIDE_SHOPIFY__API_TOKEN": "token",
            "ENV_OVERRIDE_SHOPIFY__WEBHOOK_KEY": "hook",
            "ENV_OVERRIDE_SHOPIFY__API_VERSION": "2025-01",
            "ENV_OVERRIDE_SHOPIFY__TEST_STORE": "true",
            "ENV_OVERRIDE_SHOPIFY__PRODUCTION_INDICATORS": "prod",
        }
        with _set_env(env_values):
            with self.assertRaises(ValidationError):
                self.Overrides._apply_shopify_overrides()
