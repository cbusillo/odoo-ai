"""Environment override tests."""

from test_support.tests.discovery import expose_module_alias, expose_subdirectory_tests

_exposed_modules = expose_subdirectory_tests(__name__, __path__)
expose_module_alias(
    __name__,
    "js.js_unit_tests",
    "test_js_units",
    warn_on_missing=False,
)
