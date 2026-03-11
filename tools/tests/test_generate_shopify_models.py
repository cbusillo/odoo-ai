"""Regression tests for Shopify codegen environment loading."""

from __future__ import annotations

import importlib.util
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Protocol
from unittest import mock

import click


class GenerateShopifyModelsModule(Protocol):
    def load_runtime_env_values(
        self,
        *,
        repository_root: Path,
        env_file: Path | None,
        context_name: str,
        instance_name: str,
    ) -> dict[str, str]: ...

    def update_graphql_config(self, *, config_file_path: Path, schema_file_path: Path) -> None: ...


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
            with mock.patch.dict(os.environ, {"ENV_OVERRIDE_SHOPIFY__SHOP_URL_KEY": "env-store"}):
                runtime_env_values = generate_shopify_models.load_runtime_env_values(
                    repository_root=repository_root,
                    env_file=None,
                    context_name="opw",
                    instance_name="local",
                )

        self.assertEqual(runtime_env_values, {})

    def test_load_runtime_env_values_reads_platform_secrets_without_root_env_file(self) -> None:
        generate_shopify_models = _load_generate_shopify_models_module()

        with TemporaryDirectory() as temporary_directory_name:
            repository_root = Path(temporary_directory_name)
            platform_directory = repository_root / "platform"
            platform_directory.mkdir(parents=True, exist_ok=True)
            (platform_directory / "secrets.toml").write_text(
                "\n".join(
                    (
                        "schema_version = 1",
                        "",
                        "[contexts.opw.instances.local.env]",
                        'ENV_OVERRIDE_SHOPIFY__SHOP_URL_KEY = "platform-only-store"',
                        'ENV_OVERRIDE_SHOPIFY__API_TOKEN = "platform-only-token"',
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

        self.assertEqual(runtime_env_values["ENV_OVERRIDE_SHOPIFY__SHOP_URL_KEY"], "platform-only-store")
        self.assertEqual(runtime_env_values["ENV_OVERRIDE_SHOPIFY__API_TOKEN"], "platform-only-token")
        self.assertEqual(runtime_env_values["ENV_OVERRIDE_SHOPIFY__API_VERSION"], "2026-01")

    def test_load_runtime_env_values_warns_but_does_not_fail_on_env_secret_collisions(self) -> None:
        generate_shopify_models = _load_generate_shopify_models_module()

        with TemporaryDirectory() as temporary_directory_name:
            repository_root = Path(temporary_directory_name)
            (repository_root / ".env").write_text(
                "\n".join(
                    (
                        "ENV_OVERRIDE_SHOPIFY__SHOP_URL_KEY=env-store",
                        "ENV_OVERRIDE_SHOPIFY__API_TOKEN=env-token",
                        "ENV_OVERRIDE_SHOPIFY__API_VERSION=2026-01",
                    )
                )
                + "\n",
                encoding="utf-8",
            )
            platform_directory = repository_root / "platform"
            platform_directory.mkdir(parents=True, exist_ok=True)
            (platform_directory / "secrets.toml").write_text(
                "\n".join(
                    (
                        "schema_version = 1",
                        "",
                        "[contexts.opw.instances.local.env]",
                        'ENV_OVERRIDE_SHOPIFY__SHOP_URL_KEY = "secret-store"',
                        'ENV_OVERRIDE_SHOPIFY__API_TOKEN = "secret-token"',
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

        self.assertEqual(runtime_env_values["ENV_OVERRIDE_SHOPIFY__SHOP_URL_KEY"], "secret-store")
        self.assertEqual(runtime_env_values["ENV_OVERRIDE_SHOPIFY__API_TOKEN"], "secret-token")
        self.assertEqual(runtime_env_values["ENV_OVERRIDE_SHOPIFY__API_VERSION"], "2026-01")

    def test_load_runtime_env_values_respects_error_collision_mode_for_env_file_layers(self) -> None:
        generate_shopify_models = _load_generate_shopify_models_module()

        with TemporaryDirectory() as temporary_directory_name:
            repository_root = Path(temporary_directory_name)
            (repository_root / ".env").write_text(
                "\n".join(
                    (
                        "ENV_OVERRIDE_SHOPIFY__SHOP_URL_KEY=env-store",
                        "ENV_OVERRIDE_SHOPIFY__API_TOKEN=env-token",
                        "ENV_OVERRIDE_SHOPIFY__API_VERSION=2026-01",
                    )
                )
                + "\n",
                encoding="utf-8",
            )
            platform_directory = repository_root / "platform"
            platform_directory.mkdir(parents=True, exist_ok=True)
            (platform_directory / "secrets.toml").write_text(
                "\n".join(
                    (
                        "schema_version = 1",
                        "",
                        "[contexts.opw.instances.local.env]",
                        'ENV_OVERRIDE_SHOPIFY__SHOP_URL_KEY = "secret-store"',
                    )
                )
                + "\n",
                encoding="utf-8",
            )

            with mock.patch.dict(os.environ, {"PLATFORM_ENV_COLLISION_MODE": "error"}):
                with self.assertRaises(click.ClickException):
                    generate_shopify_models.load_runtime_env_values(
                        repository_root=repository_root,
                        env_file=None,
                        context_name="opw",
                        instance_name="local",
                    )

    def test_update_graphql_config_points_ide_to_local_introspection_snapshot(self) -> None:
        generate_shopify_models = _load_generate_shopify_models_module()

        with TemporaryDirectory() as temporary_directory_name:
            repository_root = Path(temporary_directory_name)
            config_file_path = repository_root / "addons" / "shopify_sync" / "graphql" / "graphql.config.yml"
            config_file_path.parent.mkdir(parents=True, exist_ok=True)
            schema_file_path = repository_root / "addons" / "shopify_sync" / "graphql" / "schema" / "shopify_schema_2026-01.json"
            schema_file_path.parent.mkdir(parents=True, exist_ok=True)
            schema_file_path.write_text('{"__schema": {}}\n', encoding="utf-8")

            generate_shopify_models.update_graphql_config(
                config_file_path=config_file_path,
                schema_file_path=schema_file_path,
            )

            graphql_config_text = config_file_path.read_text(encoding="utf-8")

        self.assertEqual(graphql_config_text, 'schema: "schema/shopify_schema_2026-01.json"\ndocuments:\n  - "shopify/**/*.graphql"\n')
