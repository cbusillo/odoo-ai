from . import runtime
from .models import (
    ArtifactAddonSource,
    ArtifactBuildFlags,
    CompatibilityPromotionRequest,
    ArtifactIdentityManifest,
    ArtifactIdentityReference,
    ArtifactImageReference,
    ArtifactOpenUpgradeInputs,
    BackupGateEvidence,
    DeploymentEvidence,
    DokployTargetDefinition,
    HealthcheckEvidence,
    PostDeployUpdateEvidence,
    PromotionRecord,
    ReleaseStatus,
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


def build_compatibility_artifact_id(*, context_name: str, source_commit: str) -> str:
    return f"compatibility-{context_name}-{source_commit}"


def _build_healthcheck_evidence(
    *,
    urls: tuple[str, ...],
    timeout_seconds: int | None,
    status: ReleaseStatus,
) -> HealthcheckEvidence:
    if status == "skipped":
        return HealthcheckEvidence()
    if status == "pending":
        return HealthcheckEvidence(
            verified=False,
            urls=urls,
            timeout_seconds=timeout_seconds,
            status=status,
        )
    return HealthcheckEvidence(
        verified=True,
        urls=urls,
        timeout_seconds=timeout_seconds,
        status=status,
    )


def _build_post_deploy_update_evidence(
    *,
    status: ReleaseStatus,
    detail: str,
) -> PostDeployUpdateEvidence:
    if status == "skipped":
        return PostDeployUpdateEvidence()
    return PostDeployUpdateEvidence(
        attempted=True,
        status=status,
        detail=detail,
    )


def build_compatibility_promotion_record(
    *,
    artifact_id: str,
    context_name: str,
    from_instance_name: str,
    to_instance_name: str,
    destination_target_definition: DokployTargetDefinition,
    deploy_mode: str,
    deployment_id: str = "",
    deploy_status: ReleaseStatus = "pending",
    deploy_started_at: str = "",
    deploy_finished_at: str = "",
    source_health_urls: tuple[str, ...] = (),
    source_health_timeout_seconds: int | None = None,
    source_health_status: ReleaseStatus = "skipped",
    backup_gate_required: bool = True,
    backup_gate_status: ReleaseStatus = "pending",
    backup_gate_evidence: dict[str, str] | None = None,
    post_deploy_update_status: ReleaseStatus = "skipped",
    post_deploy_update_detail: str = "",
    destination_health_urls: tuple[str, ...] = (),
    destination_health_timeout_seconds: int | None = None,
    destination_health_status: ReleaseStatus = "skipped",
) -> PromotionRecord:
    resolved_target_name = destination_target_definition.target_name.strip() or f"{context_name}-{to_instance_name}"
    return build_promotion_record(
        artifact_id=artifact_id,
        context_name=context_name,
        from_instance_name=from_instance_name,
        to_instance_name=to_instance_name,
        deploy=DeploymentEvidence(
            target_name=resolved_target_name,
            target_type=destination_target_definition.target_type,
            deploy_mode=deploy_mode,
            deployment_id=deployment_id,
            status=deploy_status,
            started_at=deploy_started_at,
            finished_at=deploy_finished_at,
        ),
        source_health=_build_healthcheck_evidence(
            urls=source_health_urls,
            timeout_seconds=source_health_timeout_seconds,
            status=source_health_status,
        ),
        backup_gate=BackupGateEvidence(
            required=backup_gate_required,
            status=backup_gate_status,
            evidence=backup_gate_evidence or {},
        ),
        post_deploy_update=_build_post_deploy_update_evidence(
            status=post_deploy_update_status,
            detail=post_deploy_update_detail,
        ),
        destination_health=_build_healthcheck_evidence(
            urls=destination_health_urls,
            timeout_seconds=destination_health_timeout_seconds,
            status=destination_health_status,
        ),
    )


def build_compatibility_promotion_request(
    *,
    artifact_id: str,
    source_git_ref: str,
    context_name: str,
    from_instance_name: str,
    to_instance_name: str,
    target_name: str,
    target_type: str,
    deploy_mode: str,
    wait: bool,
    timeout_seconds: int | None,
    verify_health: bool,
    health_timeout_seconds: int | None,
    dry_run: bool,
    no_cache: bool,
    allow_dirty: bool,
    source_health_urls: tuple[str, ...],
    source_health_timeout_seconds: int | None,
    source_health_status: ReleaseStatus,
    backup_gate_required: bool,
    backup_gate_status: ReleaseStatus,
    backup_gate_evidence: dict[str, str] | None = None,
    destination_health_urls: tuple[str, ...],
    destination_health_timeout_seconds: int | None,
    destination_health_status: ReleaseStatus,
) -> CompatibilityPromotionRequest:
    return CompatibilityPromotionRequest(
        artifact_id=artifact_id,
        source_git_ref=source_git_ref,
        context=context_name,
        from_instance=from_instance_name,
        to_instance=to_instance_name,
        target_name=target_name,
        target_type=target_type,
        deploy_mode=deploy_mode,
        wait=wait,
        timeout_seconds=timeout_seconds,
        verify_health=verify_health,
        health_timeout_seconds=health_timeout_seconds,
        dry_run=dry_run,
        no_cache=no_cache,
        allow_dirty=allow_dirty,
        source_health=_build_healthcheck_evidence(
            urls=source_health_urls,
            timeout_seconds=source_health_timeout_seconds,
            status=source_health_status,
        ),
        backup_gate=BackupGateEvidence(
            required=backup_gate_required,
            status=backup_gate_status,
            evidence=backup_gate_evidence or {},
        ),
        destination_health=_build_healthcheck_evidence(
            urls=destination_health_urls,
            timeout_seconds=destination_health_timeout_seconds,
            status=destination_health_status,
        ),
    )
