import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, Mock, patch

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from .base_types import STANDARD_TAGS, OdooValue
from .test_helpers import generate_shopify_id, generate_unique_sku

_BASE_TEST_CONTEXT = {
    "tracking_disable": True,
    "no_reset_password": True,
    "mail_create_nosubscribe": True,
    "mail_create_nolog": True,
    "mail_notrack": True,
}


@dataclass(frozen=True)
class CommonImports:
    module_name: str
    MODULE_TAG: str
    DEFAULT_TEST_CONTEXT: dict[str, bool]
    STANDARD_TAGS: list[str]
    UNIT_TAGS: list[str]
    INTEGRATION_TAGS: list[str]
    TOUR_TAGS: list[str]
    JS_TAGS: list[str]
    tagged: Any
    TransactionCase: Any
    patch: Any
    MagicMock: Any
    Mock: Any
    ValidationError: Any
    UserError: Any
    date: Any
    datetime: Any
    timedelta: Any
    Decimal: Any
    logging: Any
    time: Any
    OdooValue: Any
    generate_shopify_id: Any
    generate_unique_sku: Any


def build_default_test_context(*, include_skip_shopify_sync: bool = False) -> dict[str, bool]:
    default_context = dict(_BASE_TEST_CONTEXT)
    if include_skip_shopify_sync:
        default_context["skip_shopify_sync"] = True
    return default_context


def build_unit_tags(module_name: str) -> list[str]:
    return STANDARD_TAGS + ["unit_test", module_name]


def infer_addon_name(package_name: str) -> str:
    package_segments = [segment for segment in package_name.split(".") if segment]
    if "tests" in package_segments:
        tests_index = package_segments.index("tests")
        if tests_index > 0:
            return package_segments[tests_index - 1]
    if len(package_segments) >= 2 and package_segments[0] == "addons":
        return package_segments[1]
    raise ValueError(f"Unable to infer addon name from package '{package_name}'")


def _build_phase_tags(module_name: str, phase_tag: str) -> list[str]:
    return STANDARD_TAGS + [phase_tag, module_name]


def build_common_imports(package_name: str, *, include_skip_shopify_sync: bool = False) -> CommonImports:
    module_name = infer_addon_name(package_name)
    return CommonImports(
        module_name=module_name,
        MODULE_TAG=module_name,
        DEFAULT_TEST_CONTEXT=build_default_test_context(include_skip_shopify_sync=include_skip_shopify_sync),
        STANDARD_TAGS=list(STANDARD_TAGS),
        UNIT_TAGS=_build_phase_tags(module_name, "unit_test"),
        INTEGRATION_TAGS=_build_phase_tags(module_name, "integration_test"),
        TOUR_TAGS=_build_phase_tags(module_name, "tour_test"),
        JS_TAGS=_build_phase_tags(module_name, "js_test"),
        tagged=tagged,
        TransactionCase=TransactionCase,
        patch=patch,
        MagicMock=MagicMock,
        Mock=Mock,
        ValidationError=ValidationError,
        UserError=UserError,
        date=date,
        datetime=datetime,
        timedelta=timedelta,
        Decimal=Decimal,
        logging=logging,
        time=time,
        OdooValue=OdooValue,
        generate_shopify_id=generate_shopify_id,
        generate_unique_sku=generate_unique_sku,
    )


def build_addon_test_api(package_name: str, *, include_skip_shopify_sync: bool = False) -> SimpleNamespace:
    common = build_common_imports(package_name, include_skip_shopify_sync=include_skip_shopify_sync)
    return SimpleNamespace(
        module_name=common.module_name,
        module_tag=common.MODULE_TAG,
        default_test_context=common.DEFAULT_TEST_CONTEXT,
        standard_tags=common.STANDARD_TAGS,
        unit_tags=common.UNIT_TAGS,
        integration_tags=common.INTEGRATION_TAGS,
        tour_tags=common.TOUR_TAGS,
        js_tags=common.JS_TAGS,
        tagged=common.tagged,
        transaction_case=common.TransactionCase,
        patch=common.patch,
        magic_mock=common.MagicMock,
        mock=common.Mock,
        validation_error=common.ValidationError,
        user_error=common.UserError,
        date=common.date,
        datetime=common.datetime,
        timedelta=common.timedelta,
        decimal=common.Decimal,
        logging=common.logging,
        time=common.time,
        odoo_value=common.OdooValue,
        generate_shopify_id=common.generate_shopify_id,
        generate_unique_sku=common.generate_unique_sku,
    )


__all__ = [
    "Any",
    "CommonImports",
    "MagicMock",
    "Mock",
    "OdooValue",
    "SimpleNamespace",
    "TransactionCase",
    "UserError",
    "ValidationError",
    "build_addon_test_api",
    "build_common_imports",
    "patch",
    "tagged",
    "date",
    "datetime",
    "timedelta",
    "Decimal",
    "logging",
    "time",
    "STANDARD_TAGS",
    "build_default_test_context",
    "build_unit_tags",
    "generate_shopify_id",
    "generate_unique_sku",
    "infer_addon_name",
]
