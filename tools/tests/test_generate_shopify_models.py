"""Regression tests for Shopify codegen environment loading."""

from __future__ import annotations

import importlib.util
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Protocol
from unittest import mock


class GenerateShopifyModelsModule(Protocol):
    def load_runtime_env_values(
        self,
        *,
        repository_root: Path,
        env_file: Path | None,
        context_name: str,
        instance_name: str,
    ) -> dict[str, str]: ...


def _load_generate_shopify_models_module() -> GenerateShopifyModelsModule:
    module_path = Path(__file__).resolve().parents[2] / "docker" / "scripts" / "generate_shopify_models.py"
    module_specification = importlib.util.spec_from_file_location("generate_shopify_models", module_path)
    assert module_specification is not None
    assert module_specification.loader is not None
    loaded_module = importlib.util.module_from_spec(module_specification)
    module_specification.loader.exec_module(loaded_module)
    return loaded_module  # type: ignore[return-value]


class GenerateShopifyModelsEnvironmentTests(unittest.TestCase):
    def test_load_runtime_env_values_reads_scoped_shopify_values_from_platform_secrets(self) -> None:
        generate_shopify_models = _load_generate_shopify_models_module()

        with TemporaryDirectory() as temporary_directory_name:
            repository_root = Path(temporary_directory_name)
            (repository_root / ".env").write_text("ODOO_DB_USER=odoo\n", encoding="utf-8")

            platform_directory = repository_root / "platform"
            platform_directory.mkdir(parents=True, exist_ok=True)
            (platform_directory / "secrets.toml").write_text(
                "\n".join(
                    (
                        "schema_version = 1",
                        "",
                        "[contexts.opw.instances.local.env]",
                        'ENV_OVERRIDE_SHOPIFY__SHOP_URL_KEY = "opw-local"',
                        'ENV_OVERRIDE_SHOPIFY__API_TOKEN = "token-123"',
                        'ENV_OVERRIDE_SHOPIFY__API_VERSION = "2026-01"',
                    )
                )
                + "\n",
                encoding="utf-8",
            )

            runtime_env_values = generate_shopify_models.load_runtime_env_values(
                repository_root=repository_root,
                env_file=None,
                context_name="opw",
                instance_name="local",
            )

        self.assertEqual(runtime_env_values["ENV_OVERRIDE_SHOPIFY__SHOP_URL_KEY"], "opw-local")
        self.assertEqual(runtime_env_values["ENV_OVERRIDE_SHOPIFY__API_TOKEN"], "token-123")
        self.assertEqual(runtime_env_values["ENV_OVERRIDE_SHOPIFY__API_VERSION"], "2026-01")

    def test_load_runtime_env_values_uses_process_environment_when_no_env_file_exists(self) -> None:
        generate_shopify_models = _load_generate_shopify_models_module()

        with TemporaryDirectory() as temporary_directory_name:
            repository_root = Path(temporary_directory_name)
            with mock.patch.dict(os.environ, {"ENV_OVERRIDE_SHOPIFY__SHOP_URL_KEY": "env-store"}, clear=False):
                runtime_env_values = generate_shopify_models.load_runtime_env_values(
                    repository_root=repository_root,
                    env_file=None,
                    context_name="opw",
                    instance_name="local",
                )

        self.assertEqual(runtime_env_values, {})
