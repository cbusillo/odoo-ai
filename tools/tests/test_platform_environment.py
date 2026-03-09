"""Regression tests for platform environment layering behavior."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import click

from tools.platform import environment


class PlatformEnvironmentTests(unittest.TestCase):
    def test_parse_env_file_reads_all_keys(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            env_file_path = repo_root / ".env"
            env_file_path.write_text(
                "\n".join(
                    (
                        "OPERATOR_KEY=operator",
                        "ENV_OVERRIDE_SHOPIFY__TEST_STORE=False",
                    )
                )
                + "\n",
                encoding="utf-8",
            )

            parsed_values = environment.parse_env_file(env_file_path)

            self.assertEqual(
                parsed_values,
                {
                    "OPERATOR_KEY": "operator",
                    "ENV_OVERRIDE_SHOPIFY__TEST_STORE": "False",
                },
            )

    def test_load_environment_with_details_reports_collisions_for_overlapping_keys(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            env_file_path = repo_root / ".env"
            env_file_path.write_text(
                "\n".join(
                    (
                        "OPERATOR_KEY=operator",
                        "ENV_OVERRIDE_SHOPIFY__TEST_STORE=False",
                    )
                )
                + "\n",
                encoding="utf-8",
            )

            platform_directory = repo_root / "platform"
            platform_directory.mkdir(parents=True, exist_ok=True)
            (platform_directory / "secrets.toml").write_text(
                "\n".join(
                    (
                        "schema_version = 1",
                        "",
                        "[contexts.opw.shared]",
                        'ENV_OVERRIDE_SHOPIFY__TEST_STORE = true',
                    )
                )
                + "\n",
                encoding="utf-8",
            )

            loaded_environment = environment.load_environment_with_details(
                repo_root,
                None,
                context_name="opw",
                instance_name="local",
                collision_mode="warn",
            )

            self.assertEqual(len(loaded_environment.collisions), 1)
            self.assertEqual(loaded_environment.merged_values["ENV_OVERRIDE_SHOPIFY__TEST_STORE"], "True")
            self.assertEqual(
                loaded_environment.source_by_key["ENV_OVERRIDE_SHOPIFY__TEST_STORE"],
                "secrets.contexts.opw.shared",
            )

    def test_load_environment_with_details_raises_when_collision_mode_is_error(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            env_file_path = repo_root / ".env"
            env_file_path.write_text("ENV_OVERRIDE_SHOPIFY__TEST_STORE=False\n", encoding="utf-8")

            platform_directory = repo_root / "platform"
            platform_directory.mkdir(parents=True, exist_ok=True)
            (platform_directory / "secrets.toml").write_text(
                "\n".join(
                    (
                        "schema_version = 1",
                        "",
                        "[shared]",
                        'ENV_OVERRIDE_SHOPIFY__TEST_STORE = true',
                    )
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaises(click.ClickException):
                environment.load_environment_with_details(repo_root, None, collision_mode="error")

    def test_load_environment_with_details_requires_existing_env_file(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)

            with self.assertRaises(click.ClickException):
                environment.load_environment_with_details(
                    repo_root,
                    None,
                    context_name="opw",
                    instance_name="local",
                    collision_mode="warn",
                )

    @staticmethod
    def test_resolve_stack_runtime_scope_handles_context_and_instance_names() -> None:
        assert environment.resolve_stack_runtime_scope("opw") == ("opw", "local")
        assert environment.resolve_stack_runtime_scope("opw-local") == ("opw", "local")
        assert environment.resolve_stack_runtime_scope("cm-dev") == ("cm", "dev")

    @staticmethod
    def test_resolve_stack_runtime_scope_rejects_legacy_aliases() -> None:
        assert environment.resolve_stack_runtime_scope("opw-ci-local") is None
        assert environment.resolve_stack_runtime_scope("cm-ci") is None

    def test_resolve_stack_env_file_raises_when_runtime_env_missing(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            with self.assertRaises(click.ClickException):
                environment.resolve_stack_env_file(
                    repo_root=repo_root,
                    stack_name="opw-local",
                    explicit_env_file=None,
                    require_runtime_env=True,
                )

    def test_resolve_stack_env_file_prefers_runtime_env_when_available(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            runtime_env_file = repo_root / ".platform" / "env" / "opw.local.env"
            runtime_env_file.parent.mkdir(parents=True, exist_ok=True)
            runtime_env_file.write_text("ODOO_PROJECT_NAME=odoo-opw-local\n", encoding="utf-8")

            resolved_env_file = environment.resolve_stack_env_file(
                repo_root=repo_root,
                stack_name="opw-local",
                explicit_env_file=None,
                require_runtime_env=True,
            )

            self.assertEqual(resolved_env_file, runtime_env_file.resolve())

    def test_resolve_stack_env_file_rejects_legacy_ci_stack_alias(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            with self.assertRaises(click.ClickException):
                environment.resolve_stack_env_file(
                    repo_root=repo_root,
                    stack_name="cm-ci",
                    explicit_env_file=None,
                    require_runtime_env=True,
                )

    def test_resolve_stack_env_file_uses_explicit_override(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            explicit_env_file = repo_root / "tmp" / "explicit.env"
            explicit_env_file.parent.mkdir(parents=True, exist_ok=True)
            explicit_env_file.write_text("ODOO_PROJECT_NAME=override\n", encoding="utf-8")

            resolved_env_file = environment.resolve_stack_env_file(
                repo_root=repo_root,
                stack_name="opw-local",
                explicit_env_file=Path("tmp/explicit.env"),
                require_runtime_env=True,
            )

            self.assertEqual(resolved_env_file, explicit_env_file.resolve())

    def test_load_environment_with_details_raises_for_missing_env_file(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)

            with self.assertRaises(click.ClickException):
                environment.load_environment_with_details(
                    repo_root,
                    repo_root / "missing.env",
                    context_name="opw",
                    instance_name="local",
                )

    def test_load_dokploy_source_of_truth_resolves_profiles_projects_and_env_inheritance(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            source_file_path = Path(temporary_directory_name) / "dokploy.toml"
            source_file_path.write_text(
                "\n".join(
                    (
                        "schema_version = 2",
                        "",
                        "[defaults]",
                        'source_git_ref = "origin/main"',
                        "",
                        "[projects.primary]",
                        'project_name = "odoo-ai"',
                        "",
                        "[profiles.odoo]",
                        'project = "primary"',
                        'healthcheck_path = "/web/health"',
                        "",
                        "[profiles.odoo.env]",
                        'ODOO_WEB_COMMAND = "startup"',
                        "",
                        "[profiles.opw]",
                        'extends = "odoo"',
                        "deploy_timeout_seconds = 7200",
                        "",
                        "[profiles.opw.env]",
                        'OPENUPGRADE_ENABLED = "True"',
                        "",
                        "[[targets]]",
                        'profile = "opw"',
                        'context = "opw"',
                        'instance = "testing"',
                        'git_branch = "opw-testing"',
                        'domains = ["opw-testing.example.com"]',
                        "",
                        "[targets.env]",
                        'ENV_OVERRIDE_CONFIG_PARAM__WEB__BASE__URL = "https://opw-testing.example.com"',
                    )
                )
                + "\n",
                encoding="utf-8",
            )

            source_of_truth = environment.load_dokploy_source_of_truth(source_file_path)

            self.assertEqual(len(source_of_truth.targets), 1)
            target = source_of_truth.targets[0]
            self.assertEqual(target.project_name, "odoo-ai")
            self.assertEqual(target.source_git_ref, "origin/main")
            self.assertEqual(target.deploy_timeout_seconds, 7200)
            self.assertEqual(target.healthcheck_path, "/web/health")
            self.assertEqual(target.env["ODOO_WEB_COMMAND"], "startup")
            self.assertEqual(target.env["OPENUPGRADE_ENABLED"], "True")
            self.assertEqual(
                target.env["ENV_OVERRIDE_CONFIG_PARAM__WEB__BASE__URL"],
                "https://opw-testing.example.com",
            )


if __name__ == "__main__":
    unittest.main()
