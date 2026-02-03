"""Migration to fix autopost_bills NULL values and empty names in res.partner.

This migration addresses:
1. Odoo 18 issue where partners created via SQL don't have autopost_bills set
2. Empty partner names from Shopify imports that violate test constraints
"""

import logging

from odoo.sql_db import Cursor

_logger = logging.getLogger(__name__)


def migrate(cr: Cursor, version: str) -> None:
    """Fix partner data issues for test compatibility."""
    _logger.info("Starting migration to fix partner data issues...")

    # Fix 1: Set default autopost_bills value for partners missing it
    cr.execute("SELECT COUNT(*) FROM res_partner WHERE autopost_bills IS NULL")
    null_count_before = cr.fetchone()[0]

    if null_count_before > 0:
        _logger.info(f"Found {null_count_before} partners with NULL autopost_bills")

        cr.execute("""
            UPDATE res_partner 
            SET autopost_bills = 'ask' 
            WHERE autopost_bills IS NULL
        """)

        _logger.info(f"Updated {cr.rowcount} partner records with autopost_bills")

    # Fix 2: Handle empty partner names
    # First, fix the contact partner with phone but no name
    cr.execute("""
        UPDATE res_partner 
        SET name = phone 
        WHERE name = '' 
        AND type = 'contact' 
        AND phone IS NOT NULL
    """)
    contact_fixed = cr.rowcount
    if contact_fixed > 0:
        _logger.info(f"Fixed {contact_fixed} contact partners by using phone as name")

    # For any remaining contacts with empty names, use a placeholder
    cr.execute("""
        UPDATE res_partner 
        SET name = 'Customer ' || id::text 
        WHERE name = '' 
        AND type = 'contact'
    """)
    contact_placeholder = cr.rowcount
    if contact_placeholder > 0:
        _logger.info(f"Fixed {contact_placeholder} contact partners with placeholder names")

    # For delivery/invoice partners with empty names, set to NULL (allowed by constraint)
    cr.execute("""
        UPDATE res_partner 
        SET name = NULL 
        WHERE name = '' 
        AND type IN ('delivery', 'invoice')
    """)
    address_fixed = cr.rowcount
    if address_fixed > 0:
        _logger.info(f"Fixed {address_fixed} delivery/invoice partners by setting name to NULL")

    # Verify results
    cr.execute("SELECT COUNT(*) FROM res_partner WHERE autopost_bills IS NULL")
    null_count_after = cr.fetchone()[0]

    cr.execute("SELECT COUNT(*) FROM res_partner WHERE name = ''")
    empty_names_after = cr.fetchone()[0]

    if null_count_after == 0 and empty_names_after == 0:
        _logger.info("✓ Migration successful: All partner data issues fixed")
    else:
        if null_count_after > 0:
            _logger.error(f"✗ {null_count_after} partners still have NULL autopost_bills")
        if empty_names_after > 0:
            _logger.error(f"✗ {empty_names_after} partners still have empty names")
