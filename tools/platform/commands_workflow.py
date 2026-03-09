from __future__ import annotations

import io
import json
import sys
from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path

import click

try:
    import questionary
except ImportError:  # pragma: no cover - optional interactive dependency
    questionary = None

from .instance_policies import LOCAL_INSTANCE_NAME, assert_local_instance_for_local_runtime
from .models import ContextDefinition, LoadedStack

WILDCARD_TOKENS = frozenset({"all", "*"})
WILDCARD_SAFE_WORKFLOWS = ("status", "info")
SHIP_WORKFLOW_NAME = "ship"
SHIP_INSTANCE_NAMES = frozenset({"dev", "testing", "prod"})
LOCAL_RUNTIME_WORKFLOWS = frozenset(
    {
        "init",
        "update",
        "openupgrade",
        "select",
        "up",
        "build",
    }
)


@dataclass(frozen=True)
class WorkflowRunResult:
    context_name: str
    instance_name: str
    status: str
    detail: str


def _is_wildcard(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in WILDCARD_TOKENS


def _parse_selector_values(*, raw_value: str | None, option_name: str) -> tuple[str, ...] | None:
    if raw_value is None:
        return None

    parsed_values: list[str] = []
    seen_values: set[str] = set()
    for raw_segment in raw_value.split(","):
        normalized_value = raw_segment.strip().lower()
        if not normalized_value:
            continue
        canonical_value = "all" if _is_wildcard(normalized_value) else normalized_value
        if canonical_value in seen_values:
            continue
        seen_values.add(canonical_value)
        parsed_values.append(canonical_value)

    if not parsed_values:
        raise click.ClickException(
            f"Invalid {option_name} selector '{raw_value}'. Provide at least one non-empty value."
        )

    wildcard_count = len([value for value in parsed_values if _is_wildcard(value)])
    if wildcard_count > 0 and len(parsed_values) > 1:
        raise click.ClickException(
            f"{option_name} selector cannot mix wildcard values (all/*) with named values."
        )

    return tuple(parsed_values)


def _workflow_requires_local_instance(workflow_name: str) -> bool:
    return workflow_name.strip().lower() in LOCAL_RUNTIME_WORKFLOWS


def _assert_workflow_target_allowed(*, workflow_name: str, instance_name: str) -> None:
    if not _workflow_requires_local_instance(workflow_name):
        return
    assert_local_instance_for_local_runtime(
        instance_name=instance_name,
        operation_name=f"platform {workflow_name.strip().lower()}",
    )


def _run_workflow_for_targets(
    *,
    stack_file: Path,
    env_file: Path | None,
    workflow: str,
    dry_run: bool,
    no_cache: bool,
    no_sanitize: bool,
    force: bool,
    reset_versions: bool,
    allow_prod_data_workflow: bool,
    target_pairs: tuple[tuple[str, str], ...],
    run_workflow_fn: Callable[..., None],
    echo_fn: Callable[[str], None],
    json_output: bool,
) -> None:
    run_results: list[WorkflowRunResult] = []
    normalized_workflow_name = workflow.strip().lower()
    workflow_echo_fn: Callable[[str], None] = (lambda _line: None) if json_output else echo_fn
    for context_name, instance_name in target_pairs:
        if not json_output:
            echo_fn(f"tui_run context={context_name} instance={instance_name} workflow={workflow}")
        try:
            _assert_workflow_target_allowed(workflow_name=normalized_workflow_name, instance_name=instance_name)
            if json_output:
                with (
                    redirect_stdout(io.StringIO()),
                    redirect_stderr(io.StringIO()),
                ):
                    run_workflow_fn(
                        stack_file=stack_file,
                        context_name=context_name,
                        instance_name=instance_name,
                        env_file=env_file,
                        workflow=workflow,
                        dry_run=dry_run,
                        no_cache=no_cache,
                        no_sanitize=no_sanitize,
                        force=force,
                        reset_versions=reset_versions,
                        allow_prod_data_workflow=allow_prod_data_workflow,
                        echo_fn=workflow_echo_fn,
                    )
            else:
                run_workflow_fn(
                    stack_file=stack_file,
                    context_name=context_name,
                    instance_name=instance_name,
                    env_file=env_file,
                    workflow=workflow,
                    dry_run=dry_run,
                    no_cache=no_cache,
                    no_sanitize=no_sanitize,
                    force=force,
                    reset_versions=reset_versions,
                    allow_prod_data_workflow=allow_prod_data_workflow,
                    echo_fn=workflow_echo_fn,
                )
        except click.ClickException as error:
            run_results.append(
                WorkflowRunResult(
                    context_name=context_name,
                    instance_name=instance_name,
                    status="failed",
                    detail=error.message,
                )
            )
            continue
        run_results.append(
            WorkflowRunResult(
                context_name=context_name,
                instance_name=instance_name,
                status="ok",
                detail="completed",
            )
        )

    if json_output:
        failed_run_count = len([result for result in run_results if result.status == "failed"])
        summary_payload = {
            "total_runs": len(run_results),
            "failed_runs": failed_run_count,
            "runs": [
                {
                    "context": result.context_name,
                    "instance": result.instance_name,
                    "status": result.status,
                    "detail": result.detail,
                }
                for result in run_results
            ],
        }
        echo_fn(json.dumps(summary_payload, indent=2))
    else:
        _emit_tui_run_summary(run_results, echo_fn=echo_fn)

    failed_runs = [result for result in run_results if result.status == "failed"]
    if failed_runs:
        failed_targets = ", ".join(
            sorted(f"{result.context_name}/{result.instance_name}" for result in failed_runs)
        )
        raise click.ClickException(f"{len(failed_runs)} target run(s) failed: {failed_targets}")


def _emit_tui_run_summary(run_results: list[WorkflowRunResult], *, echo_fn: Callable[[str], None]) -> None:
    if not run_results:
        return

    context_column_width = max(len("Context"), *(len(result.context_name) for result in run_results))
    instance_column_width = max(len("Instance"), *(len(result.instance_name) for result in run_results))
    status_column_width = max(len("Status"), *(len(result.status) for result in run_results))

    header_row = (
        f"{'Context'.ljust(context_column_width)}  "
        f"{'Instance'.ljust(instance_column_width)}  "
        f"{'Status'.ljust(status_column_width)}  Detail"
    )
    separator_row = (
        f"{'-' * context_column_width}  "
        f"{'-' * instance_column_width}  "
        f"{'-' * status_column_width}  {'-' * len('Detail')}"
    )

    echo_fn("tui_summary")
    echo_fn(header_row)
    echo_fn(separator_row)
    for result in run_results:
        data_row = (
            f"{result.context_name.ljust(context_column_width)}  "
            f"{result.instance_name.ljust(instance_column_width)}  "
            f"{result.status.ljust(status_column_width)}  "
            f"{result.detail}"
        )
        echo_fn(data_row)


def _prompt_choice(*, prompt_text: str, choices: tuple[str, ...], default_choice: str | None = None) -> str:
    if default_choice is not None and default_choice not in choices:
        raise click.ClickException(f"Invalid default choice '{default_choice}' for prompt '{prompt_text}'.")

    if questionary is not None and sys.stdin.isatty() and sys.stdout.isatty():
        prompt = questionary.select(
            prompt_text,
            choices=list(choices),
            default=default_choice,
            use_shortcuts=True,
        )
        answer = prompt.ask()
        if answer is None:
            raise click.Abort()
        selected_choice = str(answer)
        if selected_choice in choices:
            return selected_choice

    return click.prompt(
        prompt_text,
        type=click.Choice(choices, case_sensitive=False),
        default=default_choice,
    )


def _prompt_confirm(*, prompt_text: str, default_choice: bool = False) -> bool:
    if questionary is not None and sys.stdin.isatty() and sys.stdout.isatty():
        prompt = questionary.confirm(prompt_text, default=default_choice)
        answer = prompt.ask()
        if answer is None:
            raise click.Abort()
        return bool(answer)

    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise click.ClickException(
            "Interactive confirmation is required for this TUI workflow in the current context."
        )

    return bool(click.confirm(prompt_text, default=default_choice))


def execute_run_workflow_command(
    *,
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    workflow: str,
    dry_run: bool,
    no_cache: bool,
    no_sanitize: bool,
    force: bool,
    reset_versions: bool,
    allow_prod_data_workflow: bool,
    run_workflow_fn: Callable[..., None],
) -> None:
    _assert_workflow_target_allowed(workflow_name=workflow, instance_name=instance_name)
    run_workflow_fn(
        stack_file=stack_file,
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        workflow=workflow,
        dry_run=dry_run,
        no_cache=no_cache,
        no_sanitize=no_sanitize,
        force=force,
        reset_versions=reset_versions,
        allow_prod_data_workflow=allow_prod_data_workflow,
    )


def _execute_destructive_data_workflow_command(
    *,
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    workflow_name: str,
    dry_run: bool,
    no_sanitize: bool,
    allow_prod_data_workflow: bool,
    run_workflow_fn: Callable[..., None],
) -> None:
    _assert_workflow_target_allowed(workflow_name=workflow_name, instance_name=instance_name)
    run_workflow_fn(
        stack_file=stack_file,
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        workflow=workflow_name,
        dry_run=dry_run,
        no_cache=False,
        no_sanitize=no_sanitize,
        force=False,
        reset_versions=False,
        allow_prod_data_workflow=allow_prod_data_workflow,
    )


def execute_tui_command(
    *,
    stack_file: Path,
    context_name: str | None,
    instance_name: str | None,
    workflow: str | None,
    env_file: Path | None,
    dry_run: bool,
    no_cache: bool,
    no_sanitize: bool,
    force: bool,
    reset_versions: bool,
    allow_prod_data_workflow: bool,
    json_output: bool,
    platform_tui_workflows: tuple[str, ...],
    discover_repo_root_fn: Callable[[Path], Path],
    load_stack_fn: Callable[[Path], LoadedStack],
    ordered_instance_names_fn: Callable[[ContextDefinition], list[str]],
    run_workflow_fn: Callable[..., None],
    run_ship_fn: Callable[..., None] | None = None,
    check_dirty_working_tree_fn: Callable[[], tuple[str, ...]] | None = None,
) -> None:
    repo_root = discover_repo_root_fn(Path.cwd())
    stack_file_path = stack_file if stack_file.is_absolute() else (repo_root / stack_file)
    if not stack_file_path.exists():
        raise click.ClickException(f"Stack file not found: {stack_file_path}")

    loaded_stack = load_stack_fn(stack_file_path)
    context_names = sorted(loaded_stack.stack_definition.contexts)
    if not context_names:
        raise click.ClickException("No contexts found in stack definition.")

    selected_context_values = _parse_selector_values(raw_value=context_name, option_name="--context")
    if selected_context_values is None:
        selected_context_value = _prompt_choice(
            prompt_text="Select context",
            choices=("all", *tuple(context_names)),
        )
        selected_context_values = _parse_selector_values(raw_value=selected_context_value, option_name="--context")
    if selected_context_values is None:
        raise click.ClickException("Failed to resolve context selector values.")

    if _is_wildcard(selected_context_values[0]):
        target_context_names = tuple(context_names)
    else:
        unknown_context_names = [
            context_value
            for context_value in selected_context_values
            if context_value not in loaded_stack.stack_definition.contexts
        ]
        if unknown_context_names:
            unknown_context_list = ", ".join(sorted(unknown_context_names))
            raise click.ClickException(f"Unknown context selector value(s): {unknown_context_list}.")
        target_context_names = selected_context_values

    context_fanout_requested = len(target_context_names) > 1

    selected_workflow = workflow.strip().lower() if workflow is not None else None
    if selected_workflow is None:
        workflow_choices = platform_tui_workflows
        if context_fanout_requested:
            workflow_choices = tuple(
                workflow_name
                for workflow_name in platform_tui_workflows
                if workflow_name in WILDCARD_SAFE_WORKFLOWS
            )
            if not workflow_choices:
                raise click.ClickException("No wildcard-safe workflows are configured for TUI.")
        selected_workflow = _prompt_choice(
            prompt_text="Select workflow",
            choices=workflow_choices,
            default_choice="status" if "status" in workflow_choices else workflow_choices[0],
        ).strip().lower()

    if context_fanout_requested and selected_workflow not in WILDCARD_SAFE_WORKFLOWS:
        raise click.ClickException(
            "Fan-out context runs are limited to status/info workflows for safety."
        )

    selected_instance_values = _parse_selector_values(raw_value=instance_name, option_name="--instance")
    if selected_instance_values is None:
        if context_fanout_requested:
            all_instance_names = sorted(
                {
                    instance_name_item
                    for context_name_item in target_context_names
                    for instance_name_item in ordered_instance_names_fn(
                        loaded_stack.stack_definition.contexts[context_name_item]
                    )
                }
            )
            if not all_instance_names:
                raise click.ClickException("No instances found across selected contexts in stack definition.")
            default_instance_name = LOCAL_INSTANCE_NAME if LOCAL_INSTANCE_NAME in all_instance_names else "all"
            selected_instance_value = _prompt_choice(
                prompt_text="Select instance",
                choices=("all", *tuple(all_instance_names)),
                default_choice=default_instance_name,
            )
            selected_instance_values = _parse_selector_values(
                raw_value=selected_instance_value,
                option_name="--instance",
            )
        else:
            selected_context_name = target_context_names[0]
            context_definition = loaded_stack.stack_definition.contexts[selected_context_name]
            available_instance_names = ordered_instance_names_fn(context_definition)
            if not available_instance_names:
                raise click.ClickException(f"Context '{selected_context_name}' has no instances.")
            default_instance_name = (
                LOCAL_INSTANCE_NAME if LOCAL_INSTANCE_NAME in available_instance_names else available_instance_names[0]
            )
            selected_instance_value = _prompt_choice(
                prompt_text="Select instance",
                choices=("all", *tuple(available_instance_names)),
                default_choice=default_instance_name,
            )
            selected_instance_values = _parse_selector_values(
                raw_value=selected_instance_value,
                option_name="--instance",
            )
    if selected_instance_values is None:
        raise click.ClickException("Failed to resolve instance selector values.")

    instance_selector_is_wildcard = _is_wildcard(selected_instance_values[0])
    target_pairs: list[tuple[str, str]] = []
    missing_contexts_for_instance: list[str] = []
    missing_instances_by_context: dict[str, tuple[str, ...]] = {}
    for context_name_item in target_context_names:
        context_definition = loaded_stack.stack_definition.contexts[context_name_item]
        available_instance_names = ordered_instance_names_fn(context_definition)
        if not available_instance_names:
            raise click.ClickException(f"Context '{context_name_item}' has no instances.")

        if instance_selector_is_wildcard:
            for instance_name_item in available_instance_names:
                target_pairs.append((context_name_item, instance_name_item))
            continue

        missing_instances = tuple(
            instance_value
            for instance_value in selected_instance_values
            if instance_value not in context_definition.instances
        )
        if missing_instances:
            missing_instances_by_context[context_name_item] = missing_instances
            if len(selected_instance_values) == 1:
                missing_contexts_for_instance.append(context_name_item)
            continue

        for instance_value in selected_instance_values:
            target_pairs.append((context_name_item, instance_value))

    if missing_contexts_for_instance:
        selected_instance_name = selected_instance_values[0]
        missing_context_list = ", ".join(sorted(missing_contexts_for_instance))
        if context_fanout_requested:
            raise click.ClickException(
                f"Instance '{selected_instance_name}' is not available in contexts: {missing_context_list}. "
                "Use --instance all to fan out across each context's configured instances."
            )
        raise click.ClickException(
            f"Unknown instance '{selected_instance_name}' for context '{target_context_names[0]}'."
        )

    if missing_instances_by_context:
        detail_lines = []
        for context_name_item in sorted(missing_instances_by_context):
            missing_instance_list = ", ".join(missing_instances_by_context[context_name_item])
            detail_lines.append(f"{context_name_item}: {missing_instance_list}")
        details = "; ".join(detail_lines)
        raise click.ClickException(
            f"Instance selector values are not available for selected contexts ({details})."
        )

    if not target_pairs:
        raise click.ClickException("No target context/instance pairs resolved for TUI run.")

    if len(target_pairs) > 1 and selected_workflow not in WILDCARD_SAFE_WORKFLOWS:
        raise click.ClickException(
            "Fan-out runs are limited to status/info workflows for safety."
        )

    if selected_workflow == SHIP_WORKFLOW_NAME:
        if run_ship_fn is None:
            raise click.ClickException("Ship workflow is not configured for TUI execution.")
        if json_output:
            raise click.ClickException(
                "JSON output is not supported for TUI ship workflow. "
                "Use `platform ship` directly for scripted release automation."
            )
        if len(target_pairs) != 1:
            raise click.ClickException("TUI ship requires a single explicit context/instance target.")

        ship_context_name, ship_instance_name = target_pairs[0]
        if ship_instance_name not in SHIP_INSTANCE_NAMES:
            allowed_instances = ", ".join(sorted(SHIP_INSTANCE_NAMES))
            raise click.ClickException(
                f"TUI ship supports only deploy instances: {allowed_instances}."
            )

        allow_dirty_ship_run = False
        dirty_tracked_files = ()
        if check_dirty_working_tree_fn is not None:
            dirty_tracked_files = tuple(
                cleaned_line.strip()
                for cleaned_line in check_dirty_working_tree_fn()
                if cleaned_line.strip()
            )

        if dirty_tracked_files:
            click.echo("warning=dirty working tree detected; uncommitted changes are not deployable")
            for dirty_entry in dirty_tracked_files[:10]:
                click.echo(f"dirty_file={dirty_entry}")
            if len(dirty_tracked_files) > 10:
                click.echo(f"dirty_file_count={len(dirty_tracked_files)}")

            if not (sys.stdin.isatty() and sys.stdout.isatty()):
                raise click.ClickException(
                    "Working tree has uncommitted tracked changes and TUI ship requires interactive confirmation. "
                    "Use `platform ship --allow-dirty` for non-interactive overrides."
                )

            confirmation_text = (
                "Continue ship with dirty tracked changes? "
                "Uncommitted changes will be ignored by deploy."
            )
            allow_dirty_ship_run = _prompt_confirm(prompt_text=confirmation_text)
            if not allow_dirty_ship_run:
                raise click.Abort()

        run_ship_fn(
            context_name=ship_context_name,
            instance_name=ship_instance_name,
            env_file=env_file,
            dry_run=dry_run,
            no_cache=no_cache,
            allow_dirty=allow_dirty_ship_run,
            echo_fn=click.echo,
        )
        return

    _run_workflow_for_targets(
        stack_file=stack_file,
        env_file=env_file,
        workflow=selected_workflow,
        dry_run=dry_run,
        no_cache=no_cache,
        no_sanitize=no_sanitize,
        force=force,
        reset_versions=reset_versions,
        allow_prod_data_workflow=allow_prod_data_workflow,
        target_pairs=tuple(target_pairs),
        run_workflow_fn=run_workflow_fn,
        echo_fn=click.echo,
        json_output=json_output,
    )


def execute_init_command(
    *,
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    dry_run: bool,
    allow_prod_data_workflow: bool,
    assert_prod_data_workflow_allowed_fn: Callable[..., None],
    run_init_workflow_fn: Callable[..., None],
) -> None:
    assert_local_instance_for_local_runtime(instance_name=instance_name, operation_name="platform init")
    assert_prod_data_workflow_allowed_fn(
        instance_name=instance_name,
        workflow="init",
        allow_prod_data_workflow=allow_prod_data_workflow,
    )
    run_init_workflow_fn(
        stack_file=stack_file,
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        dry_run=dry_run,
    )


def execute_restore_command(
    *,
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    dry_run: bool,
    no_sanitize: bool,
    allow_prod_data_workflow: bool,
    run_workflow_fn: Callable[..., None],
) -> None:
    _execute_destructive_data_workflow_command(
        stack_file=stack_file,
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        workflow_name="restore",
        dry_run=dry_run,
        no_sanitize=no_sanitize,
        allow_prod_data_workflow=allow_prod_data_workflow,
        run_workflow_fn=run_workflow_fn,
    )


def execute_bootstrap_command(
    *,
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    dry_run: bool,
    no_sanitize: bool,
    allow_prod_data_workflow: bool,
    run_workflow_fn: Callable[..., None],
) -> None:
    _execute_destructive_data_workflow_command(
        stack_file=stack_file,
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        workflow_name="bootstrap",
        dry_run=dry_run,
        no_sanitize=no_sanitize,
        allow_prod_data_workflow=allow_prod_data_workflow,
        run_workflow_fn=run_workflow_fn,
    )


def execute_openupgrade_command(
    *,
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    force: bool,
    reset_versions: bool,
    dry_run: bool,
    run_openupgrade_command_fn: Callable[..., None],
) -> None:
    assert_local_instance_for_local_runtime(instance_name=instance_name, operation_name="platform openupgrade")
    run_openupgrade_command_fn(
        stack_file=stack_file,
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        force=force,
        reset_versions=reset_versions,
        dry_run=dry_run,
    )


def execute_update_command(
    *,
    stack_file: Path,
    context_name: str,
    instance_name: str,
    env_file: Path | None,
    dry_run: bool,
    run_update_workflow_fn: Callable[..., None],
) -> None:
    assert_local_instance_for_local_runtime(instance_name=instance_name, operation_name="platform update")
    run_update_workflow_fn(
        stack_file=stack_file,
        context_name=context_name,
        instance_name=instance_name,
        env_file=env_file,
        dry_run=dry_run,
    )
