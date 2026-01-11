# Import all unit test modules
# Import JavaScript unit tests
# noinspection PyUnusedImports
from ..js import js_unit_tests
from . import (
    test_autopost_bills_migration,
    test_basic,
    test_infrastructure_check,
    test_model_motor,
    test_model_motor_product_template,
    test_model_motor_workflow,
    test_model_product_template,
    test_model_transaction_mixin,
    test_multigraph_python,
    test_multigraph_quick_integration,
    test_multigraph_view,
    test_product_factory,
    test_service_product_deleter,
    test_service_shopify_helpers,
    test_service_shopify_sync,
    test_simple_unit,
    test_tour_coverage,
)
