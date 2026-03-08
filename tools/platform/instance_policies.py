from __future__ import annotations

import click

LOCAL_INSTANCE_NAME = "local"


def is_local_instance(instance_name: str) -> bool:
    return instance_name == LOCAL_INSTANCE_NAME


def assert_local_instance_for_local_runtime(*, instance_name: str, operation_name: str) -> None:
    if is_local_instance(instance_name):
        return
    raise click.ClickException(
        f"{operation_name} manages local host runtime only and requires --instance {LOCAL_INSTANCE_NAME}. "
        "Use Dokploy workflows (ship/rollback/gate/promote) for remote instances."
    )

