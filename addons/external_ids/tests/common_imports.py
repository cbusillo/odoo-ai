from typing import Any
from odoo.tests import tagged
from odoo.exceptions import ValidationError

__all__ = ["Any", "tagged", "ValidationError", "DEFAULT_TEST_CONTEXT", "STANDARD_TAGS", "UNIT_TAGS"]

DEFAULT_TEST_CONTEXT = {
    "tracking_disable": True,
    "no_reset_password": True,
    "mail_create_nosubscribe": True,
    "mail_create_nolog": True,
    "mail_notrack": True,
}

STANDARD_TAGS = ["post_install", "-at_install"]
UNIT_TAGS = STANDARD_TAGS + ["unit_test", "external_ids"]
