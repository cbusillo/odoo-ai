from . import runtime
from .models import (
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
    RuntimeSelection,
)


def parse_artifact_addon_source(repository_reference: str) -> ArtifactAddonSource:
    cleaned_reference = repository_reference.strip()
    repository_name, separator, source_ref = cleaned_reference.rpartition("@")
    if separator != "@" or not repository_name or not source_ref:
        raise ValueError(f"Addon repository reference must use <repository>@<ref>: {repository_reference}")
    return ArtifactAddonSource(repository=repository_name, ref=source_ref)


def _split_addon_skip_flags(source_environment: dict[str, str]) -> tuple[str, ...]:
    raw_value = source_environment.get("ODOO_PYTHON_SYNC_SKIP_ADDONS", "")
    return tuple(flag for flag in (part.strip() for part in raw_value.split(",")) if flag)


def build_artifact_identity_manifest(
    *,
    odoo_ai_commit: str,
    enterprise_base_digest: str,
    image_repository: str,
    image_digest: str,
    image_tags: tuple[str, ...],
    runtime_selection: RuntimeSelection,
    source_environment: dict[str, str],
) -> ArtifactIdentityManifest:
    addon_sources = tuple(
        parse_artifact_addon_source(repository_reference)
        for repository_reference in runtime.effective_runtime_addon_repositories(
            runtime_selection=runtime_selection,
            source_environment=source_environment,
        )
    )

    openupgrade_inputs = ArtifactOpenUpgradeInputs(
        addon_repository=source_environment.get("OPENUPGRADE_ADDON_REPOSITORY", "").strip(),
        install_spec=source_environment.get("OPENUPGRADELIB_INSTALL_SPEC", "").strip(),
    )
    build_flags = ArtifactBuildFlags(
        addon_skip_flags=_split_addon_skip_flags(source_environment),
        values={
            key_name: source_environment[key_name].strip()
            for key_name in ("OPENUPGRADE_ENABLED", "OPENUPGRADE_SKIP_UPDATE_ADDONS")
            if source_environment.get(key_name, "").strip()
        },
    )

    return ArtifactIdentityManifest(
        odoo_ai_commit=odoo_ai_commit,
        enterprise_base_digest=enterprise_base_digest,
        addon_sources=addon_sources,
        openupgrade_inputs=openupgrade_inputs,
        build_flags=build_flags,
        image=ArtifactImageReference(
            repository=image_repository,
            digest=image_digest,
            tags=image_tags,
        ),
    )


def build_promotion_record(
    *,
    artifact_id: str,
    context_name: str,
    from_instance_name: str,
    to_instance_name: str,
    deploy: DeploymentEvidence,
    source_health: HealthcheckEvidence | None = None,
    backup_gate: BackupGateEvidence | None = None,
    post_deploy_update: PostDeployUpdateEvidence | None = None,
    destination_health: HealthcheckEvidence | None = None,
) -> PromotionRecord:
    return PromotionRecord(
        artifact_identity=ArtifactIdentityReference(artifact_id=artifact_id),
        context=context_name,
        from_instance=from_instance_name,
        to_instance=to_instance_name,
        source_health=source_health or HealthcheckEvidence(),
        backup_gate=backup_gate or BackupGateEvidence(),
        deploy=deploy,
        post_deploy_update=post_deploy_update or PostDeployUpdateEvidence(),
        destination_health=destination_health or HealthcheckEvidence(),
    )
