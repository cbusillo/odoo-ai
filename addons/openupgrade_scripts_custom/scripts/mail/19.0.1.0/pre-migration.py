from odoo import SUPERUSER_ID, api
from odoo.api import Environment
from odoo.sql_db import Cursor
from openupgradelib import openupgrade


def _ensure_mail_link_preview_unique_source_url(env: Environment) -> None:
    message_id_column = "message_id"
    mail_link_preview_table = "mail_link_preview"
    message_link_preview_table = "mail_message_link_preview"
    env.cr.execute("SELECT to_regclass('public.mail_link_preview')")
    if env.cr.fetchone()[0] is None:
        return

    env.cr.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = 'public' "
        "  AND table_name = 'mail_link_preview' "
        "  AND column_name = 'message_id'",
    )
    mail_link_preview_has_message_id = env.cr.fetchone() is not None

    env.cr.execute("SELECT to_regclass('public.mail_message_link_preview')")
    message_link_preview_exists = env.cr.fetchone()[0] is not None

    if mail_link_preview_has_message_id and not message_link_preview_exists:
        # This hook runs before the mail module update.
        #
        # In Odoo 18, `mail_link_preview` can store one row per message for the
        # same URL. In Odoo 19, link previews are associated to messages through
        # `mail_message_link_preview`. Create and backfill the association table
        # early so deduplication does not lose per-message link previews.
        env.cr.execute(
            "CREATE TABLE IF NOT EXISTS mail_message_link_preview ("
            "  id SERIAL PRIMARY KEY,"
            "  message_id INTEGER NOT NULL,"
            "  link_preview_id INTEGER NOT NULL,"
            "  sequence INTEGER NOT NULL DEFAULT 0"
            ")",
        )
        insert_message_link_preview_sql = (
            f"INSERT INTO {message_link_preview_table} (message_id, link_preview_id, sequence) "
            f"SELECT DISTINCT {message_id_column}, id, 0 "
            f"FROM {mail_link_preview_table} "
            f"WHERE {message_id_column} IS NOT NULL"
        )
        env.cr.execute(insert_message_link_preview_sql)
        message_link_preview_exists = True

    # Find duplicate source_url groups and keep the lowest id.
    # noinspection SqlShouldBeInGroupBy
    env.cr.execute(
        "SELECT source_url, MIN(id) FROM mail_link_preview WHERE source_url IS NOT NULL GROUP BY source_url HAVING COUNT(*) > 1",
    )
    duplicate_groups = env.cr.fetchall()
    if not duplicate_groups:
        env.cr.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS mail_link_preview_unique_source_url ON mail_link_preview (source_url)",
        )
        return

    for source_url, keep_id in duplicate_groups:
        if mail_link_preview_has_message_id:
            select_mail_link_preview_sql = (
                f"SELECT id, {message_id_column} FROM {mail_link_preview_table} WHERE source_url = %s ORDER BY id"
            )
            env.cr.execute(select_mail_link_preview_sql, (source_url,))
        else:
            env.cr.execute(
                "SELECT id, NULL::integer AS message_id FROM mail_link_preview WHERE source_url = %s ORDER BY id",
                (source_url,),
            )
        rows = env.cr.fetchall()
        duplicate_ids = [record_id for record_id, _message_id in rows if record_id != keep_id]
        message_ids = [message_id for _record_id, message_id in rows if message_id is not None]
        if not duplicate_ids:
            continue

        if message_link_preview_exists:
            # Preserve existing per-message association if present.
            update_message_link_preview_sql = (
                f"UPDATE {message_link_preview_table} SET link_preview_id = %s WHERE link_preview_id = ANY(%s)"
            )
            env.cr.execute(update_message_link_preview_sql, (keep_id, duplicate_ids))
            if mail_link_preview_has_message_id and message_ids:
                # Backfill association from legacy mail_link_preview.message_id.
                backfill_message_link_preview_sql = (
                    f"INSERT INTO {message_link_preview_table} (message_id, link_preview_id, sequence) "
                    f"SELECT DISTINCT {mail_link_preview_table}.{message_id_column}, %s, 0 "
                    f"FROM {mail_link_preview_table} "
                    f"WHERE {mail_link_preview_table}.source_url = %s "
                    f"  AND {mail_link_preview_table}.{message_id_column} IS NOT NULL "
                    "  AND NOT EXISTS ("
                    f"    SELECT 1 FROM {message_link_preview_table} "
                    f"    WHERE {message_link_preview_table}.{message_id_column} = {mail_link_preview_table}.{message_id_column} "
                    f"      AND {message_link_preview_table}.link_preview_id = %s"
                    "  )"
                )
                env.cr.execute(backfill_message_link_preview_sql, (keep_id, source_url, keep_id))
            # Defensive: remove any duplicates created by the update/backfill.
            remove_duplicate_message_link_preview_sql = (
                f"DELETE FROM {message_link_preview_table} kept "
                f"USING {message_link_preview_table} dropped "
                "WHERE kept.id < dropped.id "
                f"  AND kept.{message_id_column} = dropped.{message_id_column} "
                "  AND kept.link_preview_id = dropped.link_preview_id"
            )
            env.cr.execute(remove_duplicate_message_link_preview_sql)

        env.cr.execute("DELETE FROM mail_link_preview WHERE id = ANY(%s)", (duplicate_ids,))

    env.cr.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS mail_link_preview_unique_source_url ON mail_link_preview (source_url)",
    )

    if message_link_preview_exists:
        create_message_link_preview_index_sql = (
            "CREATE UNIQUE INDEX IF NOT EXISTS mail_message_link_preview_unique_message_link_preview "
            f"ON {message_link_preview_table} ({message_id_column}, link_preview_id)"
        )
        env.cr.execute(create_message_link_preview_index_sql)


def _ensure_env(cursor_or_env: Cursor | Environment) -> Environment:
    if isinstance(cursor_or_env, api.Environment):
        return cursor_or_env
    return api.Environment(cursor_or_env, SUPERUSER_ID, {})


@openupgrade.migrate()
def migrate(cr: Cursor, version: str) -> None:
    """Pre-migration hook for mail (19.0.1.0)."""
    _ = version
    env = _ensure_env(cr)
    _ensure_mail_link_preview_unique_source_url(env)
