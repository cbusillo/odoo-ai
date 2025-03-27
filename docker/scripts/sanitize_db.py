#!/usr/bin/env python3
import odoo
from odoo import api, SUPERUSER_ID
import sys

def sanitize_database() -> None:
    db_registry = odoo.modules.registry.Registry(odoo.tools.config['db_name'])
    with db_registry.cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})
        
        # Neutralize email sending
        env['ir.mail_server'].search([]).write({'active': False})
        # noinspection PyTypeChecker
        env['ir.config_parameter'].sudo().set_param('mail.catchall.domain', False)
        # noinspection PyTypeChecker
        env['ir.config_parameter'].sudo().set_param('mail.catchall.alias', False)
        # noinspection PyTypeChecker
        env['ir.config_parameter'].sudo().set_param('mail.bounce.alias', False)

        # Deactivate scheduled actions
        active_crons = env['ir.cron'].search([])
        print(f"Deactivating {len(active_crons)} cron jobs...")
        active_crons.write({'active': False})
        cr.commit()

        active_crons = env['ir.cron'].search([('active', '=', True)])
        print(f"{len(active_crons)} cron jobs are still active.")
        if active_crons:
            print("Error: The following cron jobs are still active:")
            for cron in active_crons:
                print(f"- {cron.name} (id: {cron.id})")
            sys.exit(1)

if __name__ == '__main__':
    print("Sanitizing database...")
    sanitize_database()
    print("Database sanitized.")