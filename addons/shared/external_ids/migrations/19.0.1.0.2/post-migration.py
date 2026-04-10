from odoo.addons.external_ids.migrations.external_ui_cleanup import unlink_obsolete_external_id_views
from odoo.sql_db import Cursor


def migrate(cr: Cursor, version: str) -> None:
    unlink_obsolete_external_id_views(cr)
