import click

from tools.docker_runner import restore_stack


def _print_usage() -> None:
    click.echo("Usage:")
    click.echo("  uv run restore <stack> [--init]")
    click.echo("")
    click.echo("Examples:")
    click.echo("  uv run restore opw-dev")
    click.echo("  uv run restore opw-testing")
    click.echo("  uv run restore cm-dev")
    click.echo("  uv run restore cm-testing")
    click.echo("  uv run restore opw-local --init")


@click.command()
@click.argument("stack", required=False)
@click.option("--init", "bootstrap_only", is_flag=True, help="Bootstrap only (skip upstream restore)")
@click.option("--no-sanitize", is_flag=True, help="Skip sanitization during restore")
def main(stack: str | None, bootstrap_only: bool, no_sanitize: bool) -> int:
    if not stack:
        _print_usage()
        return 2
    return restore_stack(stack, bootstrap_only=bootstrap_only, no_sanitize=no_sanitize)
