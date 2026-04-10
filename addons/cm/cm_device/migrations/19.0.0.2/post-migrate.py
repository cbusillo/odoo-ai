"""Backfill historical-import flag for legacy payer-less devices."""

import logging

from odoo import SUPERUSER_ID, api
from odoo.sql_db import Cursor

_logger = logging.getLogger(__name__)


def migrate(cr: Cursor, version: str) -> None:
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    device_model = env["service.device"].with_context(
        tracking_disable=True,
        mail_create_nolog=True,
        mail_notrack=True,
        mail_create_nosubscribe=True,
    )

    batch_size = 5000
    updated_count = 0
    last_device_id = 0

    while True:
        legacy_devices = device_model.search(
            [
                ("id", ">", last_device_id),
                ("payer", "=", False),
                ("is_historical_import", "=", False),
            ],
            order="id",
            limit=batch_size,
        )
        if not legacy_devices:
            break

        legacy_devices.write({"is_historical_import": True})
        updated_count += len(legacy_devices)
        last_device_id = legacy_devices[-1].id

    if updated_count:
        _logger.info("CM Device migration: marked %s payer-less legacy devices as historical imports", updated_count)
    else:
        _logger.info("CM Device migration: no payer-less legacy devices required backfill")
