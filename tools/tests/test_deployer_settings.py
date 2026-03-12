import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import click

from tools.deployer import settings
from tools.tests.platform_test_helpers import write_compose_stack_files


class DeployerSettingsTests(unittest.TestCase):
    def test_compute_compose_files_uses_base_then_override_precedence(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            write_compose_stack_files(repo_root)

            compose_files = settings.compute_compose_files(
                "opw-local",
                repo_root,
                settings.StackConfig.model_validate({}),
            )

            self.assertEqual(
                [path.name for path in compose_files],
                ["docker-compose.yml", "base.yaml", "docker-compose.override.yml"],
            )

    def test_compute_compose_files_includes_project_layer_and_explicit_files(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            compose_directory = repo_root / "platform" / "compose"
            write_compose_stack_files(repo_root)
            (compose_directory / "opw.yaml").write_text("services: {}\n", encoding="utf-8")
            (repo_root / "docker" / "config").mkdir(parents=True, exist_ok=True)
            (repo_root / "docker" / "config" / "extra.yaml").write_text("services: {}\n", encoding="utf-8")

            config = settings.StackConfig.model_validate(
                {
                    "DEPLOY_COMPOSE_FILES": "docker/config/extra.yaml",
                }
            )
            compose_files = settings.compute_compose_files("opw-local", repo_root, config)

            self.assertEqual(
                [path.name for path in compose_files],
                [
                    "docker-compose.yml",
                    "base.yaml",
                    "docker-compose.override.yml",
                    "opw.yaml",
                    "extra.yaml",
                ],
            )

    def test_select_env_file_prefers_platform_runtime_env_file(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            runtime_env_file = repo_root / ".platform" / "env" / "opw.local.env"
            runtime_env_file.parent.mkdir(parents=True, exist_ok=True)
            runtime_env_file.write_text("ODOO_PROJECT_NAME=odoo-opw-local\n", encoding="utf-8")
            (repo_root / ".env").write_text("DOKPLOY_HOST=example\n", encoding="utf-8")

            selected_file = settings.select_env_file("opw-local", repo_root, None)

            self.assertEqual(selected_file, runtime_env_file.resolve())

    def test_select_env_file_rejects_legacy_ci_local_stack_alias(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            (repo_root / ".env").write_text("DOKPLOY_HOST=example\n", encoding="utf-8")

            with self.assertRaises(click.ClickException):
                settings.select_env_file("cm-ci-local", repo_root, None)

    def test_select_env_file_rejects_legacy_ci_stack_alias(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            (repo_root / ".env").write_text("DOKPLOY_HOST=example\n", encoding="utf-8")

            with self.assertRaises(click.ClickException):
                settings.select_env_file("cm-ci", repo_root, None)

    def test_select_env_file_requires_runtime_env_when_no_explicit_file(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            hidden_stack_env_file = repo_root / "docker" / "config" / ".env.opw-local"
            hidden_stack_env_file.parent.mkdir(parents=True, exist_ok=True)
            hidden_stack_env_file.write_text("ODOO_PROJECT_NAME=legacy\n", encoding="utf-8")
            root_env_file = repo_root / ".env"
            root_env_file.write_text("DOKPLOY_HOST=example\n", encoding="utf-8")

            with self.assertRaises(click.ClickException):
                settings.select_env_file("opw-local", repo_root, None)

    def test_select_env_file_uses_explicit_env_file_when_runtime_env_missing(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            explicit_env_file = repo_root / "tmp" / "override.env"
            explicit_env_file.parent.mkdir(parents=True, exist_ok=True)
            explicit_env_file.write_text("ODOO_PROJECT_NAME=override\n", encoding="utf-8")

            selected_file = settings.select_env_file("opw-local", repo_root, explicit_env_file)

            self.assertEqual(selected_file, explicit_env_file.resolve())

    def test_select_env_file_requires_supported_locations(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            hidden_stack_env_file = repo_root / "docker" / "config" / ".env.opw-local"
            hidden_stack_env_file.parent.mkdir(parents=True, exist_ok=True)
            hidden_stack_env_file.write_text("ODOO_PROJECT_NAME=legacy\n", encoding="utf-8")

            with self.assertRaises(click.ClickException):
                settings.select_env_file("opw-local", repo_root, None)

    def test_load_stack_settings_defaults_state_root_under_platform_directory(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            write_compose_stack_files(repo_root)
            runtime_env_file = repo_root / ".platform" / "env" / "opw.local.env"
            runtime_env_file.parent.mkdir(parents=True, exist_ok=True)
            runtime_env_file.write_text(
                "\n".join(
                    (
                        "ODOO_PROJECT_NAME=odoo-opw-local",
                        "DOCKER_IMAGE=odoo-ai",
                        "ODOO_DB_PASSWORD=database-password",
                        "ODOO_MASTER_PASSWORD=master-password",
                        "ENV_OVERRIDE_CONFIG_PARAM__WEB__BASE__URL=https://opw-local.example.com",
                    )
                )
                + "\n",
                encoding="utf-8",
            )
            (repo_root / ".env").write_text("DOKPLOY_HOST=example\n", encoding="utf-8")

            stack_settings = settings.load_stack_settings("opw-local", base_directory=repo_root)

        self.assertEqual(stack_settings.state_root, (repo_root / ".platform" / "state" / "opw-local").resolve())
        self.assertEqual(
            stack_settings.env_file,
            (repo_root / ".platform" / "state" / "opw-local" / ".compose.env").resolve(),
        )

    @staticmethod
    def test_validate_base_env_defaults_allows_matching_overlaps() -> None:
        settings._validate_base_env_defaults(
            base_env_values={
                "ODOO_LIST_DB": "False",
                "ODOO_PROXY_MODE": "True",
            },
            resolved_environment={
                "ODOO_LIST_DB": "False",
                "ODOO_DB_USER": "odoo",
            },
        )

    def test_validate_base_env_defaults_raises_on_conflicting_overlaps(self) -> None:
        with self.assertRaises(click.ClickException):
            settings._validate_base_env_defaults(
                base_env_values={
                    "ODOO_LIST_DB": "False",
                    "ODOO_PROXY_MODE": "True",
                },
                resolved_environment={
                    "ODOO_LIST_DB": "True",
                    "ODOO_DB_USER": "odoo",
                },
            )


if __name__ == "__main__":
    unittest.main()
