{
    "name": "Product Connect",
    "version": "19.0.8.2",
    "category": "Industries",
    "author": "Chris Busillo (Shiny Computers)",
    "maintainers": ["cbusillo"],
    "depends": [
        "base",
        "product",
        "web",
        "web_tour",
        "website_sale",
        "base_automation",
        "stock",
        "mail",
        "project",
        "repair",
        "contacts",
        "account",
        "sale_management",
        "purchase",
        "phone_validation",
        "delivery",
        "delivery_ups_rest",
        "delivery_usps_rest",
        "base_geolocalize",
        "external_ids",
        "hr_employee_name_extended",
        "discuss_record_links",
        "disable_odoo_online",
        "authentik_sso",
    ],
    "summary": "Connect to product sources and manage motor parts inventory with Shopify integration",
    "description": """
Comprehensive motor parts management system with Shopify integration.
Handles inventory, repairs, and multi-channel sales for marine equipment.
    """,
    "data": [
        # Security first
        "security/ir.model.access.csv",
        # Seed/reference data (order matters where noted)
        "data/motor_test_section_data.xml",  # motor data order is important (relations)
        "data/motor_test_selection_data.xml",
        "data/motor_test_template_data.xml",
        "data/motor_part_template_data.xml",
        "data/motor_stat_data.xml",
        "data/product_condition_data.xml",
        "data/res_config_data.xml",
        "data/mail_templates.xml",
        "data/delivery_products.xml",  # delivery data order is important (relations)
        "data/delivery_carriers.xml",
        "data/delivery_carrier_mappings.xml",
        # Reports
        "report/motor_product_reports.xml",
        "report/motor_reports.xml",
        "report/product_reports.xml",
        # Views
        "views/delivery_carrier_views.xml",
        "views/motor_views.xml",  # motor_views needs to be loaded first (menu parent)
        "views/motor_part_template_views.xml",
        "views/motor_product_template_views.xml",
        "views/motor_product_views.xml",
        "views/motor_test_template_views.xml",
        "views/motor_test_selection_views.xml",
        "views/motor_test_section_views.xml",
        "views/printnode_interface_views.xml",
        "views/product_color_views.xml",
        "views/product_condition_views.xml",
        "views/product_import_views.xml",
        "views/product_inventory_wizard_views.xml",
        "views/product_product_views.xml",
        "views/product_template_views.xml",
        "views/product_processing_views.xml",
        "views/product_image_views.xml",
        "views/product_type_views.xml",
        "views/product_manufacturer_views.xml",
        "views/repair_order_views.xml",
        "views/res_partner_views.xml",
        "views/res_users_views.xml",
        "views/sale_order_views.xml",
        "views/shipping_analytics_views.xml",
        "views/shopify_sync_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "product_connect/static/src/scss/*",
            "product_connect/static/src/js/utils/*",
            "product_connect/static/src/js/forms/*",
            "product_connect/static/src/js/lists/*",
            "product_connect/static/src/js/widgets/*",
            "product_connect/static/src/xml/*",
        ],
        "web.assets_backend_lazy": [
            "product_connect/static/src/js/external/qr-scanner.umd.min.js",
            # Load all custom view code/templates/styles recursively
            "product_connect/static/src/views/**/*.js",
            "product_connect/static/src/views/**/*.xml",
            "product_connect/static/src/views/**/*.scss",
        ],
        "product_connect.test_helpers": [
            "product_connect/static/tests/helpers/*.js",
        ],
        "web.assets_unit_tests_setup": [
            ("include", "product_connect.test_helpers"),
            # Ensure all custom view code is available in the unit test harness
            "product_connect/static/src/views/**/*.js",
            "product_connect/static/src/views/**/*.xml",
        ],
        # JavaScript unit tests (Hoot/QUnit) - helpers must be included first
        "web.assets_unit_tests": [
            ("include", "product_connect.test_helpers"),
            "product_connect/static/tests/*.test.js",
        ],
        # Browser tours only - DO NOT include unit tests here
        "web.assets_tests": [
            "product_connect/static/tests/tours/**/*.js",
        ],
    },
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}
