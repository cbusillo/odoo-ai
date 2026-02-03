from datetime import datetime
from typing import Any, Union
from unittest.mock import MagicMock, Mock

OdooValue = Union[str, int, float, bool, None, list, tuple, datetime, bytes]


MockType = Union[MagicMock, Mock]

AssertionDict = dict[str, Any]

DEFAULT_TEST_CONTEXT = {
    "skip_shopify_sync": True,
    "tracking_disable": True,
    "no_reset_password": True,
    "mail_create_nosubscribe": True,
    "mail_create_nolog": True,
    "mail_notrack": True,
}

STANDARD_TAGS = ["post_install", "-at_install"]
UNIT_TAGS = STANDARD_TAGS + ["unit_test"]
INTEGRATION_TAGS = STANDARD_TAGS + ["integration_test"]
TOUR_TAGS = STANDARD_TAGS + ["tour_test"]
JS_TAGS = STANDARD_TAGS + ["js_test"]
PERFORMANCE_TAGS = STANDARD_TAGS + ["performance_test"]

TEST_SKU_PREFIX = "TEST"
TEST_SHOPIFY_ID_MIN = 1000000000
TEST_SHOPIFY_ID_MAX = 9999999999
