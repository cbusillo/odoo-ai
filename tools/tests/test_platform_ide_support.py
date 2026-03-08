"""Regression tests for platform IDE configuration helpers."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.platform import ide_support
from tools.platform.models import ContextDefinition, InstanceDefinition, RuntimeSelection, StackDefinition


class PlatformIdeSupportTests(unittest.TestCase):
    def test_write_pycharm_odoo_conf_avoids_local_source_mirror_paths(self) -> None:
        with TemporaryDirectory() as temporary_directory_name:
            repo_root = Path(temporary_directory_name)
            stack_definition = StackDefinition(
                schema_version=1,
                odoo_version="19.0",
                addons_path=(
                    "/odoo/addons",
                    "/odoo/odoo/addons",
                    "/opt/project/addons",
                    "/opt/extra_addons",
                    "/opt/enterprise",
                ),
                contexts={"cm": ContextDefinition(instances={"local": InstanceDefinition()})},
            )
            runtime_selection = RuntimeSelection(
                context_name="cm",
                instance_name="local",
                context_definition=stack_definition.contexts["cm"],
                instance_definition=stack_definition.contexts["cm"].instances["local"],
                database_name="cm",
                project_name="odoo-cm-local",
                state_path=repo_root / ".platform" / "state" / "cm-local",
                data_mount=repo_root / ".platform" / "state" / "cm-local" / "data",
                runtime_conf_host_path=repo_root / ".platform" / "state" / "cm-local" / "data" / "platform.odoo.conf",
                data_volume_name="odoo-cm-local-data",
                log_volume_name="odoo-cm-local-logs",
                db_volume_name="odoo-cm-local-db",
                web_host_port=8069,
                longpoll_host_port=8072,
                db_host_port=5432,
                runtime_odoo_conf_path="/tmp/platform.odoo.conf",
                effective_install_modules=("cm_custom",),
                effective_addon_repositories=(),
                effective_runtime_env={},
            )

            written_conf = ide_support.write_pycharm_odoo_conf(
                repo_root=repo_root,
                runtime_selection=runtime_selection,
                stack_definition=stack_definition,
                source_environment={"ODOO_DB_USER": "odoo", "ODOO_DB_PASSWORD": "pw"},
            )

            self.assertEqual(written_conf, repo_root / ".platform" / "ide" / "cm.local.odoo.conf")
            rendered_conf = written_conf.read_text(encoding="utf-8")
            self.assertIn(
                "addons_path = /odoo/addons,/odoo/odoo/addons,"
                f"{repo_root / 'addons'},/opt/extra_addons,/opt/enterprise",
                rendered_conf,
            )
            self.assertNotIn("/.platform/ide/", rendered_conf)
            self.assertIn(f"db_port = {runtime_selection.db_host_port}", rendered_conf)


if __name__ == "__main__":
    unittest.main()
