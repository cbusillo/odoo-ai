from odoo.tests import tagged

__all__ = ["STANDARD_TAGS", "UNIT_TAGS", "tagged"]

STANDARD_TAGS = ["post_install", "-at_install"]
UNIT_TAGS = STANDARD_TAGS + ["unit_test", "discuss_record_links"]
