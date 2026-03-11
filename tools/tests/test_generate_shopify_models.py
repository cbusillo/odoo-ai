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

    def sync_graphql_ide_api_version(self, *, graphql_path: Path, shopify_api_version: str) -> None: ...


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

    def test_sync_graphql_ide_api_version_updates_dot_env_when_present(self) -> None:
        generate_shopify_models = _load_generate_shopify_models_module()

        with TemporaryDirectory() as temporary_directory_name:
            graphql_path = Path(temporary_directory_name) / "addons" / "shopify_sync" / "graphql"
            graphql_path.mkdir(parents=True, exist_ok=True)
            graphql_env_file = graphql_path / ".env"
            graphql_env_file.write_text(
                "\n".join(
                    (
                        "SHOPIFY_GRAPHQL_SHOP_URL_KEY=opw-local",
                        "SHOPIFY_GRAPHQL_API_VERSION=2025-10",
                        "SHOPIFY_GRAPHQL_API_TOKEN=token-123",
                    )
                )
                + "\n",
                encoding="utf-8",
            )

            generate_shopify_models.sync_graphql_ide_api_version(
                graphql_path=graphql_path,
                shopify_api_version="2026-01",
            )

            graphql_env_text = graphql_env_file.read_text(encoding="utf-8")

        self.assertEqual(
            graphql_env_text,
            "\n".join(
                (
                    "SHOPIFY_GRAPHQL_SHOP_URL_KEY=opw-local",
                    "SHOPIFY_GRAPHQL_API_VERSION=2026-01",
                    "SHOPIFY_GRAPHQL_API_TOKEN=token-123",
                    "",
                )
            ),
        )

    def test_sync_graphql_ide_api_version_falls_back_to_dot_env_local(self) -> None:
        generate_shopify_models = _load_generate_shopify_models_module()

        with TemporaryDirectory() as temporary_directory_name:
            graphql_path = Path(temporary_directory_name) / "addons" / "shopify_sync" / "graphql"
            graphql_path.mkdir(parents=True, exist_ok=True)
            graphql_env_file = graphql_path / ".env.local"
            graphql_env_file.write_text(
                "SHOPIFY_GRAPHQL_API_TOKEN=token-123\n",
                encoding="utf-8",
            )

            generate_shopify_models.sync_graphql_ide_api_version(
                graphql_path=graphql_path,
                shopify_api_version="2026-01",
            )

            graphql_env_text = graphql_env_file.read_text(encoding="utf-8")

        self.assertEqual(
            graphql_env_text,
            "\n".join(
                (
                    "SHOPIFY_GRAPHQL_API_TOKEN=token-123",
                    "SHOPIFY_GRAPHQL_API_VERSION=2026-01",
                    "",
                )
            ),
        )
