from openupgradelib import openupgrade


def _reset_mail_message_link_preview(env) -> None:
    """Clear pre-existing relation rows before upstream 19.0.1.19 backfill.

    Some 18->19 datasets already have rows in `mail_message_link_preview`.
    The upstream 19.0.1.19 script blindly inserts all rows from
    `mail_link_preview`, which fails on the unique
    `(message_id, link_preview_id)` constraint when stale rows are present.
    """

    env.cr.execute("SELECT to_regclass('public.mail_message_link_preview')")
    table_name = env.cr.fetchone()[0]
    if table_name is None:
        return
    # noinspection SqlWithoutWhere
    env.cr.execute("DELETE FROM mail_message_link_preview")


@openupgrade.migrate()
def migrate(env, version) -> None:
    _ = version
    openupgrade.load_data(env, "mail", "19.0.1.19/noupdate_changes.xml")
    _reset_mail_message_link_preview(env)
    openupgrade.delete_records_safely_by_xml_id(
        env,
        [
            "mail.ir_cron_discuss_users_settings_unmute",
            "mail.module_category_canned_response",
        ],
    )
