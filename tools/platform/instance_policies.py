import click

LOCAL_INSTANCE_NAME = "local"


def _destructive_workflow_replacement_command(*, workflow_name: str, instance_name: str) -> str | None:
    normalized_instance = instance_name.strip().lower() or LOCAL_INSTANCE_NAME
    if workflow_name == "restore":
        return (
            "uv --directory /path/to/odoo-devkit run platform runtime restore "
            f"--manifest /path/to/workspace.toml --instance {normalized_instance}"
        )
    if workflow_name == "bootstrap":
        return (
            "uv --directory /path/to/odoo-devkit run platform runtime workflow "
            f"--manifest /path/to/workspace.toml --workflow bootstrap --instance {normalized_instance}"
        )
    return None


def is_local_instance(instance_name: str) -> bool:
    return instance_name == LOCAL_INSTANCE_NAME


def assert_local_instance_for_local_runtime(*, instance_name: str, operation_name: str) -> None:
    if is_local_instance(instance_name):
        return
    raise click.ClickException(
        f"{operation_name} manages local host runtime only and requires --instance {LOCAL_INSTANCE_NAME}. "
        "Use Dokploy workflows (ship/rollback/gate) for remote instances."
    )


def assert_destructive_data_workflow_supported(*, instance_name: str, workflow_name: str) -> None:
    replacement_command = _destructive_workflow_replacement_command(
        workflow_name=workflow_name,
        instance_name=instance_name,
    )
    message_lines = [
        f"'platform {workflow_name}' is retired in odoo-ai.",
        "Destructive runtime ownership moved to odoo-devkit plus tenant workspace.toml manifests.",
    ]
    if replacement_command is not None:
        message_lines.extend(
            (
                "Run the manifest-backed replacement from your tenant repo or from odoo-devkit:",
                replacement_command,
            )
        )
    message_lines.append(
        "Use the tenant's tracked workspace.toml and pass --instance explicitly when targeting dev/testing/prod."
    )
    raise click.ClickException("\n".join(message_lines))
