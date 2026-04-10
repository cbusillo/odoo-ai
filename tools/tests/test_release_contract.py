import unittest
from pathlib import Path

from tools.platform.models import (
    BackupGateEvidence,
    ContextDefinition,
    DeploymentEvidence,
    DokployTargetDefinition,
    HealthcheckEvidence,
    InstanceDefinition,
    PostDeployUpdateEvidence,
    RuntimeSelection,
)
from tools.platform.release_contract import (
    build_compatibility_artifact_id,
    build_compatibility_promotion_request,
    build_artifact_identity_manifest,
    build_compatibility_promotion_record,
    build_promotion_record,
    parse_artifact_addon_source,
)


def _sample_runtime_selection() -> RuntimeSelection:
    context_definition = ContextDefinition()
    instance_definition = InstanceDefinition()
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


class ReleaseContractTests(unittest.TestCase):
    def test_parse_artifact_addon_source_requires_repository_and_ref(self) -> None:
        source = parse_artifact_addon_source("cbusillo/disable_odoo_online@main")

        self.assertEqual(source.repository, "cbusillo/disable_odoo_online")
        self.assertEqual(source.ref, "main")

        with self.assertRaises(ValueError):
            parse_artifact_addon_source("cbusillo/disable_odoo_online")

    def test_build_artifact_identity_manifest_collects_current_release_inputs(self) -> None:
        manifest = build_artifact_identity_manifest(
            odoo_ai_commit="f45db648",
            enterprise_base_digest="sha256:enterprise123",
            image_repository="ghcr.io/cbusillo/odoo-ai-private",
            image_digest="sha256:image456",
            image_tags=("sha-f45db648", "prod-candidate"),
            runtime_selection=_sample_runtime_selection(),
            source_environment={
                "OPENUPGRADE_ENABLED": "true",
                "OPENUPGRADE_ADDON_REPOSITORY": "OCA/OpenUpgrade@89e649728027a8ab656b3aa4be18f4bd364db417",
                "OPENUPGRADELIB_INSTALL_SPEC": "git+https://github.com/OCA/openupgradelib.git@46d66ff5ed6a99481f84d3c79fc6e50835da7286",
                "OPENUPGRADE_SKIP_UPDATE_ADDONS": "True",
                "ODOO_PYTHON_SYNC_SKIP_ADDONS": "openupgrade_framework,openupgrade_scripts,openupgrade_scripts_custom",
            },
        )

        self.assertEqual(manifest.odoo_ai_commit, "f45db648")
        self.assertEqual(manifest.enterprise_base_digest, "sha256:enterprise123")
        self.assertEqual(
            manifest.addon_sources,
            (
                parse_artifact_addon_source("cbusillo/disable_odoo_online@main"),
                parse_artifact_addon_source("OCA/OpenUpgrade@89e649728027a8ab656b3aa4be18f4bd364db417"),
            ),
        )
        self.assertEqual(
            manifest.build_flags.addon_skip_flags,
            ("openupgrade_framework", "openupgrade_scripts", "openupgrade_scripts_custom"),
        )
        self.assertEqual(manifest.build_flags.values["OPENUPGRADE_ENABLED"], "true")
        self.assertEqual(manifest.image.tags, ("sha-f45db648", "prod-candidate"))

    def test_build_promotion_record_applies_defaults_and_nested_evidence(self) -> None:
        record = build_promotion_record(
            artifact_id="artifact-20260410-f45db648",
            context_name="opw",
            from_instance_name="testing",
            to_instance_name="prod",
            deploy=DeploymentEvidence(
                target_name="opw-prod",
                target_type="compose",
                deploy_mode="artifact-promotion",
                deployment_id="deploy-123",
                status="pass",
            ),
            source_health=HealthcheckEvidence(
                verified=True,
                urls=("https://testing.example.com/web/health",),
                timeout_seconds=30,
                status="pass",
            ),
            backup_gate=BackupGateEvidence(required=True, status="pass", evidence={"snapshot": "snap-1"}),
            post_deploy_update=PostDeployUpdateEvidence(attempted=True, status="pass", detail="updated modules"),
        )

        self.assertEqual(record.artifact_identity.artifact_id, "artifact-20260410-f45db648")
        self.assertEqual(record.deploy.target_name, "opw-prod")
        self.assertEqual(record.backup_gate.evidence["snapshot"], "snap-1")
        self.assertEqual(record.destination_health.status, "skipped")

    def test_build_compatibility_promotion_record_maps_pending_promote_checkpoints(self) -> None:
        record = build_compatibility_promotion_record(
            artifact_id="artifact-20260410-f45db648",
            context_name="opw",
            from_instance_name="testing",
            to_instance_name="prod",
            destination_target_definition=DokployTargetDefinition(
                context="opw",
                instance="prod",
                target_type="compose",
                target_name="",
            ),
            deploy_mode="dokploy-compose-api",
            source_health_urls=("https://testing.example.com/web/health",),
            source_health_timeout_seconds=30,
            source_health_status="pending",
            backup_gate_status="pending",
            post_deploy_update_status="pending",
            post_deploy_update_detail="compose update will run after deploy",
            destination_health_urls=("https://prod.example.com/web/health",),
            destination_health_timeout_seconds=45,
            destination_health_status="pending",
        )

        self.assertEqual(record.deploy.target_name, "opw-prod")
        self.assertEqual(record.deploy.deploy_mode, "dokploy-compose-api")
        self.assertFalse(record.source_health.verified)
        self.assertEqual(record.source_health.status, "pending")
        self.assertEqual(record.source_health.urls, ("https://testing.example.com/web/health",))
        self.assertTrue(record.post_deploy_update.attempted)
        self.assertEqual(record.post_deploy_update.status, "pending")
        self.assertEqual(record.destination_health.timeout_seconds, 45)

    def test_build_compatibility_promotion_request_captures_handoff_contract(self) -> None:
        request = build_compatibility_promotion_request(
            artifact_id=build_compatibility_artifact_id(context_name="opw", source_commit="abc123"),
            source_git_ref="abc123",
            context_name="opw",
            from_instance_name="testing",
            to_instance_name="prod",
            target_name="opw-prod",
            target_type="compose",
            deploy_mode="dokploy-compose-api",
            wait=True,
            timeout_seconds=600,
            verify_health=True,
            health_timeout_seconds=45,
            dry_run=False,
            no_cache=False,
            allow_dirty=False,
            source_health_urls=("https://testing.example.com/web/health",),
            source_health_timeout_seconds=30,
            source_health_status="pass",
            backup_gate_required=True,
            backup_gate_status="pass",
            destination_health_urls=("https://prod.example.com/web/health",),
            destination_health_timeout_seconds=45,
            destination_health_status="pending",
        )

        self.assertEqual(request.artifact_id, "compatibility-opw-abc123")
        self.assertEqual(request.source_git_ref, "abc123")
        self.assertEqual(request.source_health.status, "pass")
        self.assertEqual(request.destination_health.status, "pending")


if __name__ == "__main__":
    unittest.main()
