# Copyright 2026 Shiny Computers
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _ensure_mail_link_preview_unique_source_url(env) -> None:
    """De-duplicate mail_link_preview.source_url and create the unique index.

    Odoo 18 can store multiple `mail_link_preview` rows per URL (one per
    message). Odoo 19 introduces a unique index on `(source_url)`.

    This hook runs before the mail module update to avoid upgrade warnings and
    ensure schema creation succeeds.
    """

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
        env.cr.execute(
            "INSERT INTO mail_message_link_preview (message_id, link_preview_id, sequence) "
            "SELECT DISTINCT message_id, id, 0 "
            "FROM mail_link_preview "
            "WHERE message_id IS NOT NULL",
        )
        message_link_preview_exists = True

    # Find duplicate source_url groups and keep the lowest id.
    env.cr.execute(
        "SELECT source_url, MIN(id) "
        "FROM mail_link_preview "
        "WHERE source_url IS NOT NULL "
        "GROUP BY source_url "
        "HAVING COUNT(*) > 1",
    )
    duplicate_groups = env.cr.fetchall()
    if not duplicate_groups:
        env.cr.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS mail_link_preview_unique_source_url "
            "ON mail_link_preview (source_url)",
        )
        return

    for source_url, keep_id in duplicate_groups:
        if mail_link_preview_has_message_id:
            env.cr.execute(
                "SELECT id, message_id FROM mail_link_preview WHERE source_url = %s ORDER BY id",
                (source_url,),
            )
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
            env.cr.execute(
                "UPDATE mail_message_link_preview SET link_preview_id = %s WHERE link_preview_id = ANY(%s)",
                (keep_id, duplicate_ids),
            )
            if mail_link_preview_has_message_id and message_ids:
                # Backfill association from legacy mail_link_preview.message_id.
                env.cr.execute(
                    "INSERT INTO mail_message_link_preview (message_id, link_preview_id, sequence) "
                    "SELECT DISTINCT mail_link_preview.message_id, %s, 0 "
                    "FROM mail_link_preview "
                    "WHERE mail_link_preview.source_url = %s "
                    "  AND mail_link_preview.message_id IS NOT NULL "
                    "  AND NOT EXISTS ("
                    "    SELECT 1 FROM mail_message_link_preview "
                    "    WHERE mail_message_link_preview.message_id = mail_link_preview.message_id "
                    "      AND mail_message_link_preview.link_preview_id = %s"
                    "  )",
                    (keep_id, source_url, keep_id),
                )
            # Defensive: remove any duplicates created by the update/backfill.
            env.cr.execute(
                "DELETE FROM mail_message_link_preview kept "
                "USING mail_message_link_preview dropped "
                "WHERE kept.id < dropped.id "
                "  AND kept.message_id = dropped.message_id "
                "  AND kept.link_preview_id = dropped.link_preview_id",
            )

        env.cr.execute("DELETE FROM mail_link_preview WHERE id = ANY(%s)", (duplicate_ids,))

    env.cr.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS mail_link_preview_unique_source_url "
        "ON mail_link_preview (source_url)",
    )

    if message_link_preview_exists:
        env.cr.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS mail_message_link_preview_unique_message_link_preview "
            "ON mail_message_link_preview (message_id, link_preview_id)",
        )


@openupgrade.migrate()
def migrate(env, version):
    """Pre-migration hook for mail (19.0.1.0)."""

    _ensure_mail_link_preview_unique_source_url(env)
