import logging

from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor
from psycopg2 import sql

_logger = logging.getLogger(__name__)


_COLUMNS_BY_TABLE_ALLOWLIST = {
    "attachment": set(),
    "image_1920_file_size": {"product_image"},
    "image_1920_file_size_kb": set(),
    "image_1920_height": {"product_image"},
    "image_1920_resolution": set(),
    "image_1920_width": {"product_image"},
    "initial_index": {"product_image"},
}

_METADATA_COLUMN_NAMES = [
    "image_1920_file_size",
    "image_1920_file_size_kb",
    "image_1920_height",
    "image_1920_resolution",
    "image_1920_width",
    "initial_index",
]


# Ruff false positive: Cursor annotation is present but flagged during inspection.
def _fetch_tables_with_column(cursor: Cursor, column_name: str) -> list[str]:  # noqa: ANN001
    cursor.execute(
        """
        SELECT table_name
          FROM information_schema.columns
         WHERE table_schema = 'public'
           AND column_name = %s
        """,
        [column_name],
    )
    return [row[0] for row in cursor.fetchall()]


def _drop_columns(cursor: Cursor, table_name: str, column_names: list[str]) -> None:
    if not column_names:
        return
    clauses = sql.SQL(", ").join(
        sql.SQL("DROP COLUMN IF EXISTS {}")
        .format(sql.Identifier(column))
        for column in column_names
    )
    statement = sql.SQL("ALTER TABLE ") + sql.Identifier(table_name) + sql.SQL(" ") + clauses
    cursor.execute(statement)


def _collect_metadata_tables(cursor: Cursor) -> set[str]:
    tables: set[str] = set()
    for column_name in _METADATA_COLUMN_NAMES:
        tables.update(_fetch_tables_with_column(cursor, column_name))
    return tables


def _cleanup_legacy_columns(cursor: Cursor) -> None:
    metadata_tables = _collect_metadata_tables(cursor)
    columns_by_table: dict[str, list[str]] = {}
    for column_name, allowed_tables in _COLUMNS_BY_TABLE_ALLOWLIST.items():
        table_names = _fetch_tables_with_column(cursor, column_name)
        for table_name in table_names:
            if column_name == "attachment" and table_name not in metadata_tables:
                continue
            if table_name in allowed_tables:
                continue
            columns_by_table.setdefault(table_name, []).append(column_name)

    for table_name, column_names in columns_by_table.items():
        _logger.info("Dropping legacy image metadata columns from %s: %s", table_name, ", ".join(column_names))
        _drop_columns(cursor, table_name, column_names)


def _recompute_product_image_metadata(env: api.Environment) -> None:
    image_model = env["product.image"].with_context(active_test=False)
    image_ids = image_model.search([]).ids
    batch_size = 200
    for offset in range(0, len(image_ids), batch_size):
        batch_ids = image_ids[offset : offset + batch_size]
        batch_records = image_model.browse(batch_ids)
        compute_image_metadata = getattr(batch_records, "_compute_image_metadata", None)
        if compute_image_metadata:
            compute_image_metadata()


def migrate(cr: Cursor, version: str) -> None:
    _ = version
    env = api.Environment(cr, SUPERUSER_ID, {})
    _cleanup_legacy_columns(env.cr)
    _recompute_product_image_metadata(env)
