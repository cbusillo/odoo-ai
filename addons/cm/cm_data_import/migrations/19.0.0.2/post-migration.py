from odoo.addons.cm_data_import.migrations.employee_external_identity import migrate_employee_identity_external_ids
from odoo.sql_db import Cursor


def migrate(cr: Cursor, version: str) -> None:
    migrate_employee_identity_external_ids(cr)
