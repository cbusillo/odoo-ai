import os

addons_path = os.getenv("ODOO_ADDONS_PATH") or "/odoo/addons,/enterprise,/workspace"
os.environ["ODOO_ADDONS_PATH"] = addons_path

import odoo
from odoo.modules.module import initialize_sys_path

odoo.tools.config["addons_path"] = addons_path
initialize_sys_path()

database_name = os.getenv("ODOO_DATABASE")
if database_name:
    odoo.tools.config["db_name"] = database_name
    odoo.tools.config["test_enable"] = True

from types import MethodType
from typing import Any

from _pytest.unittest import TestCaseFunction
from odoo.tests.common import BaseCase


def _outcome_ok(self: Any) -> Any:  # emulate unittest.TestResult.wasSuccessful
    return getattr(self, "_outcome", None) is None or self._outcome.success


TestCaseFunction.wasSuccessful = MethodType(_outcome_ok, TestCaseFunction)
TestCaseFunction.addSubTest = lambda *_, **__: None
BaseCase._tests_run_count = 1
