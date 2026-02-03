from unittest.mock import patch

from odoo.tests import tagged

DEFAULT_TEST_CONTEXT = {
    "skip_shopify_sync": True,
    "tracking_disable": True,
    "no_reset_password": True,
    "mail_create_nosubscribe": True,
    "mail_create_nolog": True,
    "mail_notrack": True,
}

STANDARD_TAGS = ["post_install", "-at_install"]
UNIT_TAGS = STANDARD_TAGS + ["unit_test", "transaction_utilities"]

__all__ = [
    "tagged",
    "patch",
    "DEFAULT_TEST_CONTEXT",
    "STANDARD_TAGS",
    "UNIT_TAGS",
]
