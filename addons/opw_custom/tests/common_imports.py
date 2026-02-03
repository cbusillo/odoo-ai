import logging
import random
import secrets
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Callable, Iterator, Optional
from unittest.mock import MagicMock, Mock, PropertyMock, patch

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import HttpCase, TransactionCase, tagged

from .base_types import (
    INTEGRATION_TAGS,
    STANDARD_TAGS,
    JS_TAGS,
    TEST_SHOPIFY_ID_MAX,
    TEST_SHOPIFY_ID_MIN,
    TEST_SKU_PREFIX,
    TOUR_TAGS,
    UNIT_TAGS,
    AssertionDict,
    DEFAULT_TEST_CONTEXT,
    MockType,
    OdooValue,
)

__all__ = [
    "date",
    "datetime",
    "timedelta",
    "Decimal",
    "logging",
    "random",
    "secrets",
    "time",
    "Any",
    "Callable",
    "Iterator",
    "Optional",
    "MagicMock",
    "Mock",
    "PropertyMock",
    "patch",
    "tagged",
    "TransactionCase",
    "HttpCase",
    "ValidationError",
    "UserError",
    "AccessError",
    "OdooValue",
    "MockType",
    "AssertionDict",
    "DEFAULT_TEST_CONTEXT",
    "STANDARD_TAGS",
    "UNIT_TAGS",
    "JS_TAGS",
    "INTEGRATION_TAGS",
    "TOUR_TAGS",
    "TEST_SKU_PREFIX",
    "TEST_SHOPIFY_ID_MIN",
    "TEST_SHOPIFY_ID_MAX",
]
