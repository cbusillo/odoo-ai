import unittest

from pydantic import ValidationError

from tools.platform.models import (
    ArtifactAddonSource,
    ArtifactBuildFlags,
    ArtifactIdentityManifest,
    ArtifactIdentityReference,
    ArtifactImageReference,
    ArtifactOpenUpgradeInputs,
    BackupGateEvidence,
    DeploymentEvidence,
    HealthcheckEvidence,
    PostDeployUpdateEvidence,
    PromotionRecord,
)


class ArtifactIdentityManifestTests(unittest.TestCase):
    def test_artifact_identity_manifest_accepts_explicit_release_inputs(self) -> None:
        manifest = ArtifactIdentityManifest(
            odoo_ai_commit="f45db648",
            enterprise_base_digest="sha256:abc123",
            addon_sources=(
                ArtifactAddonSource(repository="cbusillo/private-addon-a", ref="refs/tags/v1.2.3"),
                ArtifactAddonSource(repository="cbusillo/private-addon-b", ref="9f8e7d6c"),
            ),
            openupgrade_inputs=ArtifactOpenUpgradeInputs(
                addon_repository="oca/openupgrade@19.0",
                install_spec="openupgradelib==3.11.2",
            ),
            build_flags=ArtifactBuildFlags(
                addon_skip_flags=("skip_shopify_sync",),
                values={"SHIP_MODE": "compose"},
            ),
            image=ArtifactImageReference(
                repository="ghcr.io/cbusillo/odoo-ai-private",
                digest="sha256:def456",
                tags=("sha-f45db648",),
            ),
        )

        self.assertEqual(manifest.schema_version, 1)
        self.assertEqual(manifest.odoo_ai_commit, "f45db648")
        self.assertEqual(manifest.addon_sources[0].repository, "cbusillo/private-addon-a")
        self.assertEqual(manifest.build_flags.addon_skip_flags, ("skip_shopify_sync",))
        self.assertEqual(manifest.image.tags, ("sha-f45db648",))

    def test_artifact_identity_manifest_rejects_unknown_fields(self) -> None:
        with self.assertRaises(ValidationError):
            ArtifactIdentityManifest(
                odoo_ai_commit="f45db648",
                enterprise_base_digest="sha256:abc123",
                image=ArtifactImageReference(
                    repository="ghcr.io/cbusillo/odoo-ai-private",
                    digest="sha256:def456",
                ),
                branch_name="main",
            )


class HealthcheckEvidenceTests(unittest.TestCase):
    def test_verified_healthcheck_requires_urls_timeout_and_terminal_status(self) -> None:
        with self.assertRaises(ValidationError):
            HealthcheckEvidence(verified=True, urls=(), timeout_seconds=30, status="pass")

        with self.assertRaises(ValidationError):
            HealthcheckEvidence(verified=True, urls=("https://example.com/web/health",), status="pass")

        with self.assertRaises(ValidationError):
            HealthcheckEvidence(
                verified=True,
                urls=("https://example.com/web/health",),
                timeout_seconds=30,
                status="pending",
            )

        evidence = HealthcheckEvidence(
            verified=True,
            urls=("https://example.com/web/health",),
            timeout_seconds=30,
            status="pass",
        )

        self.assertEqual(evidence.status, "pass")


class PostDeployUpdateEvidenceTests(unittest.TestCase):
    def test_post_deploy_update_requires_status_to_match_attempted_flag(self) -> None:
        with self.assertRaises(ValidationError):
            PostDeployUpdateEvidence(attempted=False, status="pass")

        with self.assertRaises(ValidationError):
            PostDeployUpdateEvidence(attempted=True, status="skipped")

        evidence = PostDeployUpdateEvidence(attempted=True, status="pass", detail="updated modules")

        self.assertEqual(evidence.detail, "updated modules")


class PromotionRecordTests(unittest.TestCase):
    def test_promotion_record_accepts_auditable_release_evidence(self) -> None:
        record = PromotionRecord(
            artifact_identity=ArtifactIdentityReference(artifact_id="artifact-20260410-f45db648"),
            context="opw",
            from_instance="testing",
            to_instance="prod",
            source_health=HealthcheckEvidence(
                verified=True,
                urls=("https://testing.example.com/web/health",),
                timeout_seconds=30,
                status="pass",
            ),
            backup_gate=BackupGateEvidence(
                required=True,
                status="pass",
                evidence={"snapshot": "backup-20260410-010203"},
            ),
            deploy=DeploymentEvidence(
                target_name="opw-prod",
                target_type="compose",
                deploy_mode="artifact-promotion",
                deployment_id="deploy-123",
                status="pass",
                started_at="2026-04-10T10:00:00Z",
                finished_at="2026-04-10T10:02:00Z",
            ),
            post_deploy_update=PostDeployUpdateEvidence(attempted=True, status="pass", detail="module update ok"),
            destination_health=HealthcheckEvidence(
                verified=True,
                urls=("https://prod.example.com/web/health",),
                timeout_seconds=60,
                status="pass",
            ),
        )

        self.assertEqual(record.context, "opw")
        self.assertEqual(record.backup_gate.evidence["snapshot"], "backup-20260410-010203")
        self.assertEqual(record.deploy.deployment_id, "deploy-123")

    def test_promotion_record_rejects_same_source_and_destination(self) -> None:
        with self.assertRaises(ValidationError):
            PromotionRecord(
                artifact_identity=ArtifactIdentityReference(artifact_id="artifact-20260410-f45db648"),
                context="cm",
                from_instance="testing",
                to_instance="testing",
                deploy=DeploymentEvidence(
                    target_name="cm-testing",
                    target_type="compose",
                    deploy_mode="artifact-promotion",
                ),
            )


if __name__ == "__main__":
    unittest.main()
