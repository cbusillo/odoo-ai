import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.platform import commands_release_contract
from tools.platform.models import (
    ContextDefinition,
    DokploySourceOfTruth,
    DokployTargetDefinition,
    InstanceDefinition,
    LoadedStack,
    RuntimeSelection,
    StackDefinition,
)
from tools.platform.release_contract import build_compatibility_promotion_record, build_compatibility_ship_request


def _sample_runtime_selection() -> RuntimeSelection:
    context_definition = ContextDefinition(instances={"prod": InstanceDefinition()})
    instance_definition = context_definition.instances["prod"]
    return RuntimeSelection(
        context_name="opw",
        instance_name="prod",
        context_definition=context_definition,
        instance_definition=instance_definition,
        database_name="opw",
        project_name="odoo-opw-prod",
        state_path=Path("/tmp/opw-prod"),
        data_mount=Path("/tmp/opw-prod/data"),
        runtime_conf_host_path=Path("/tmp/opw-prod/platform.odoo.conf"),
        data_volume_name="odoo-opw-prod-data",
        log_volume_name="odoo-opw-prod-logs",
        db_volume_name="odoo-opw-prod-db",
        web_host_port=8369,
        longpoll_host_port=8372,
        db_host_port=15732,
        runtime_odoo_conf_path="/tmp/platform.odoo.conf",
        effective_install_modules=("opw_custom",),
        effective_addon_repositories=("cbusillo/disable_odoo_online@main",),
        effective_runtime_env={},
    )


class PlatformReleaseContractCommandTests(unittest.TestCase):
    def test_execute_export_artifact_identity_emits_manifest_payload(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            stack_file_path = repo_root / "platform" / "stack.toml"
            stack_file_path.parent.mkdir(parents=True, exist_ok=True)
            stack_file_path.write_text("schema_version = 1\n", encoding="utf-8")
            loaded_stack = LoadedStack(
                stack_file_path=stack_file_path,
                stack_definition=StackDefinition(
                    schema_version=1,
                    odoo_version="19.0",
                    addons_path=("/odoo/addons",),
                    contexts={"opw": ContextDefinition(instances={"prod": InstanceDefinition()})},
                ),
            )
            captured_payload: dict[str, object] = {}

            commands_release_contract.execute_export_artifact_identity(
                stack_file=Path("platform/stack.toml"),
                context_name="opw",
                instance_name="prod",
                env_file=None,
                git_reference="HEAD",
                enterprise_base_digest="sha256:enterprise123",
                image_repository="ghcr.io/cbusillo/odoo-ai-private",
                image_digest="sha256:image456",
                image_tags=("sha-f45db648",),
                discover_repo_root_fn=lambda _path: repo_root,
                load_stack_fn=lambda _path: loaded_stack,
                resolve_runtime_selection_fn=lambda _stack, _context, _instance: _sample_runtime_selection(),
                load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (
                    repo_root / ".env",
                    {
                        "OPENUPGRADE_ENABLED": "true",
                        "OPENUPGRADE_ADDON_REPOSITORY": "OCA/OpenUpgrade@89e649728027a8ab656b3aa4be18f4bd364db417",
                        "OPENUPGRADELIB_INSTALL_SPEC": "git+https://github.com/OCA/openupgradelib.git@46d66ff5ed6a99481f84d3c79fc6e50835da7286",
                    },
                ),
                resolve_local_git_commit_fn=lambda git_reference: f"resolved-{git_reference}",
                build_artifact_identity_manifest_fn=lambda **payload: type(
                    "_Manifest",
                    (),
                    {
                        "model_dump": staticmethod(
                            lambda mode="json": {
                                **payload,
                                "artifact_id": "artifact-sha256-image456",
                            }
                        )
                    },
                )(),
                emit_payload_fn=lambda payload: captured_payload.update(payload),
            )

        self.assertEqual(captured_payload["artifact_id"], "artifact-sha256-image456")
        self.assertEqual(captured_payload["odoo_ai_commit"], "resolved-HEAD")
        self.assertEqual(captured_payload["enterprise_base_digest"], "sha256:enterprise123")
        self.assertEqual(captured_payload["image_repository"], "ghcr.io/cbusillo/odoo-ai-private")

    def test_execute_handoff_artifact_identity_invokes_control_plane_with_manifest(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            stack_file_path = repo_root / "platform" / "stack.toml"
            stack_file_path.parent.mkdir(parents=True, exist_ok=True)
            stack_file_path.write_text("schema_version = 1\n", encoding="utf-8")
            loaded_stack = LoadedStack(
                stack_file_path=stack_file_path,
                stack_definition=StackDefinition(
                    schema_version=1,
                    odoo_version="19.0",
                    addons_path=("/odoo/addons",),
                    contexts={"opw": ContextDefinition(instances={"prod": InstanceDefinition()})},
                ),
            )
            captured_manifest: dict[str, object] = {}

            commands_release_contract.execute_handoff_artifact_identity(
                stack_file=Path("platform/stack.toml"),
                context_name="opw",
                instance_name="prod",
                env_file=None,
                git_reference="HEAD",
                enterprise_base_digest="sha256:enterprise123",
                image_repository="ghcr.io/cbusillo/odoo-ai-private",
                image_digest="sha256:image456",
                image_tags=("sha-f45db648",),
                discover_repo_root_fn=lambda _path: repo_root,
                load_stack_fn=lambda _path: loaded_stack,
                resolve_runtime_selection_fn=lambda _stack, _context, _instance: _sample_runtime_selection(),
                load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (
                    repo_root / ".env",
                    {
                        "OPENUPGRADE_ENABLED": "true",
                        "OPENUPGRADE_ADDON_REPOSITORY": "OCA/OpenUpgrade@89e649728027a8ab656b3aa4be18f4bd364db417",
                        "OPENUPGRADELIB_INSTALL_SPEC": "git+https://github.com/OCA/openupgradelib.git@46d66ff5ed6a99481f84d3c79fc6e50835da7286",
                    },
                ),
                resolve_local_git_commit_fn=lambda git_reference: f"resolved-{git_reference}",
                build_artifact_identity_manifest_fn=lambda **payload: type(
                    "_Manifest",
                    (),
                    {
                        "model_dump": staticmethod(
                            lambda mode="json": {
                                **payload,
                                "artifact_id": "artifact-sha256-image456",
                            }
                        ),
                    },
                )(),
                invoke_control_plane_artifact_handoff_fn=lambda manifest: captured_manifest.update(manifest.model_dump(mode="json")),
            )

        self.assertEqual(captured_manifest["artifact_id"], "artifact-sha256-image456")
        self.assertEqual(captured_manifest["image_digest"], "sha256:image456")

    def test_execute_export_promotion_record_emits_compatibility_payload(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            source_of_truth = DokploySourceOfTruth(
                schema_version=1,
                targets=(
                    DokployTargetDefinition(
                        context="opw",
                        instance="testing",
                        target_type="compose",
                        target_name="opw-testing",
                        domains=("testing.example.com",),
                    ),
                    DokployTargetDefinition(
                        context="opw",
                        instance="prod",
                        target_type="compose",
                        target_name="opw-prod",
                        domains=("prod.example.com",),
                    ),
                ),
            )
            captured_payload: dict[str, object] = {}

            commands_release_contract.execute_export_promotion_record(
                context_name="opw",
                from_instance_name="testing",
                to_instance_name="prod",
                env_file=None,
                artifact_id="artifact-20260410-f45db648",
                wait=True,
                verify_health=True,
                health_timeout_override_seconds=None,
                verify_source_health=True,
                source_health_timeout_override_seconds=None,
                deployment_id="",
                deploy_started_at="",
                deploy_finished_at="",
                deploy_status="pending",
                source_health_status=None,
                backup_gate_status=None,
                backup_evidence_items=("snapshot=snap-123",),
                post_deploy_update_status=None,
                post_deploy_update_detail="",
                destination_health_status=None,
                assert_promote_path_allowed_fn=lambda **_kwargs: None,
                discover_repo_root_fn=lambda _path: repo_root,
                load_dokploy_source_of_truth_if_present_fn=lambda _path: source_of_truth,
                find_dokploy_target_definition_fn=lambda source_of_truth, context_name, instance_name: next(
                    (
                        target_definition
                        for target_definition in source_of_truth.targets
                        if target_definition.context == context_name and target_definition.instance == instance_name
                    ),
                    None,
                ),
                load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (repo_root / ".env", {}),
                resolve_ship_health_timeout_seconds_fn=lambda health_timeout_override_seconds, target_definition: (
                    health_timeout_override_seconds or (25 if target_definition.instance == "testing" else 45)
                ),
                resolve_ship_healthcheck_urls_fn=lambda target_definition, environment_values: tuple(
                    f"https://{domain_name}{target_definition.healthcheck_path}" for domain_name in target_definition.domains
                ),
                resolve_dokploy_ship_mode_fn=lambda _context_name, _instance_name, _environment_values: "auto",
                build_compatibility_promotion_record_fn=build_compatibility_promotion_record,
                emit_payload_fn=lambda payload: captured_payload.update(payload),
            )

        self.assertEqual(captured_payload["artifact_identity"]["artifact_id"], "artifact-20260410-f45db648")
        self.assertEqual(captured_payload["deploy"]["target_name"], "opw-prod")
        self.assertEqual(captured_payload["deploy"]["deploy_mode"], "dokploy-compose-api")
        self.assertEqual(captured_payload["source_health"]["status"], "pending")
        self.assertEqual(captured_payload["backup_gate"]["evidence"], {"snapshot": "snap-123"})
        self.assertEqual(captured_payload["destination_health"]["status"], "pending")
        self.assertEqual(captured_payload["post_deploy_update"]["status"], "pending")

    def test_execute_export_ship_request_emits_compatibility_payload(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            source_of_truth = DokploySourceOfTruth(
                schema_version=1,
                targets=(
                    DokployTargetDefinition(
                        context="opw",
                        instance="prod",
                        target_type="compose",
                        target_name="opw-prod",
                        source_git_ref="origin/opw-prod",
                        domains=("prod.example.com",),
                    ),
                ),
            )
            captured_payload: dict[str, object] = {}

            commands_release_contract.execute_export_ship_request(
                context_name="opw",
                instance_name="prod",
                env_file=None,
                source_git_ref="",
                wait=True,
                timeout_override_seconds=600,
                verify_health=True,
                health_timeout_override_seconds=None,
                dry_run=False,
                no_cache=False,
                allow_dirty=False,
                default_source_git_ref="origin/main",
                discover_repo_root_fn=lambda _path: repo_root,
                load_dokploy_source_of_truth_if_present_fn=lambda _path: source_of_truth,
                find_dokploy_target_definition_fn=lambda source_of_truth, context_name, instance_name: next(
                    (
                        target_definition
                        for target_definition in source_of_truth.targets
                        if target_definition.context == context_name and target_definition.instance == instance_name
                    ),
                    None,
                ),
                load_environment_fn=lambda _repo_root, _env_file, **_kwargs: (repo_root / ".env", {}),
                resolve_ship_health_timeout_seconds_fn=lambda health_timeout_override_seconds, target_definition: 45,
                resolve_ship_healthcheck_urls_fn=lambda target_definition, environment_values: tuple(
                    f"https://{domain_name}{target_definition.healthcheck_path}" for domain_name in target_definition.domains
                ),
                resolve_dokploy_ship_mode_fn=lambda _context_name, _instance_name, _environment_values: "auto",
                build_compatibility_ship_request_fn=build_compatibility_ship_request,
                emit_payload_fn=lambda payload: captured_payload.update(payload),
            )

        self.assertEqual(captured_payload["context"], "opw")
        self.assertEqual(captured_payload["instance"], "prod")
        self.assertEqual(captured_payload["source_git_ref"], "origin/opw-prod")
        self.assertEqual(captured_payload["deploy_mode"], "dokploy-compose-api")


if __name__ == "__main__":
    unittest.main()
