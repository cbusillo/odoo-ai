import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.platform import commands_release_contract
from tools.platform.models import ContextDefinition, InstanceDefinition, LoadedStack, RuntimeSelection, StackDefinition


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
                    {"model_dump": staticmethod(lambda mode="json": payload)},
                )(),
                emit_payload_fn=lambda payload: captured_payload.update(payload),
            )

        self.assertEqual(captured_payload["odoo_ai_commit"], "resolved-HEAD")
        self.assertEqual(captured_payload["enterprise_base_digest"], "sha256:enterprise123")
        self.assertEqual(captured_payload["image_repository"], "ghcr.io/cbusillo/odoo-ai-private")


if __name__ == "__main__":
    unittest.main()
