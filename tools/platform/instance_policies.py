import click

LOCAL_INSTANCE_NAME = "local"

LOCAL_DESTRUCTIVE_WORKFLOW_REPLACEMENTS = {
    "restore": "uv --directory /path/to/odoo-devkit run platform runtime restore --manifest /path/to/workspace.toml",
    "bootstrap": (
        "uv --directory /path/to/odoo-devkit run platform runtime workflow --manifest /path/to/workspace.toml --workflow bootstrap"
    ),
}


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
    if not is_local_instance(instance_name):
        return

    replacement_command = LOCAL_DESTRUCTIVE_WORKFLOW_REPLACEMENTS.get(workflow_name)
    message_lines = [
        f"Local 'platform {workflow_name}' is retired in odoo-ai.",
        "Local destructive runtime ownership moved to odoo-devkit plus tenant workspace.toml manifests.",
    ]
    if replacement_command is not None:
        message_lines.extend(
            (
                "Run the manifest-backed replacement from your tenant repo or from odoo-devkit:",
                replacement_command,
            )
        )
    message_lines.append(
        "The surviving odoo-ai data-workflow surface is now remote-only for Dokploy-managed dev/testing/prod targets."
    )
    raise click.ClickException("\n".join(message_lines))
