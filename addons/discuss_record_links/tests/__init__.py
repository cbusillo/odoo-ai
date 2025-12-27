# Expose JS unit tests in subpackage so Odoo test loader finds them
import sys

try:
    from .js import js_unit_tests as _js_unit_tests
except ImportError:
    _js_unit_tests = None  # pragma: no cover - best-effort import

if _js_unit_tests is not None:
    # Re-expose under a test_* name for Odoo discovery
    sys.modules[__name__].test_js_units = _js_unit_tests

# Import tour tests so they register with the test loader
try:
    from . import tour as _tour_tests
except ImportError:  # pragma: no cover - defensive guard for partial installs
    _tour_tests = None
else:
    module = getattr(_tour_tests, "test_smoke_login_tour", None)
    if module is not None:
        sys.modules[__name__].test_smoke_login_tour = module
