{
    "name": "OPW Custom",
    "version": "19.0.8.2",
    "category": "Industries",
    "author": "Chris Busillo (Shiny Computers)",
    "maintainers": ["cbusillo"],
    "depends": [
        "base",
        "product",
        "web",
        "environment_banner",
        "web_tour",
        "website_sale",
        "base_automation",
        "stock",
        "mail",
        "project",
        "contacts",
        "account",
        "sale_management",
        "purchase",
        "phone_validation",
        "base_geolocalize",
        "notification_center",
        "transaction_utilities",
        "product_metadata",
        "product_widgets",
        "image_enhancements",
        "marine_motors",
        "shopify_sync",
        "hr_employee_name_extended",
        "discuss_record_links",
        "disable_odoo_online",
        "authentik_sso",
    ],
    "summary": "OPW-specific product workflows, processing analytics, and inventory tools",
    "description": """
OPW customizations for product processing, inventory, and reporting.
Builds on shared addons such as marine motors and Shopify sync.
    """,
    "data": [
        # Security first
        "security/ir.model.access.csv",
        "data/res_config_data.xml",
        # Reports
        "report/product_reports.xml",
        # Views
        "views/product_import_views.xml",
        "views/product_inventory_wizard_views.xml",
        "views/product_product_views.xml",
        "views/product_template_views.xml",
        "views/product_processing_views.xml",
        "views/product_image_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "opw_custom/static/src/scss/*",
            "opw_custom/static/src/js/lists/*",
            "opw_custom/static/src/js/widgets/*",
            "opw_custom/static/src/xml/*",
        ],
        "web.assets_backend_lazy": [
            "opw_custom/static/src/js/external/qr-scanner.umd.min.js",
            # Load all custom view code/templates/styles recursively
            "opw_custom/static/src/views/**/*.js",
            "opw_custom/static/src/views/**/*.xml",
            "opw_custom/static/src/views/**/*.scss",
        ],
        "opw_custom.test_helpers": [
            "opw_custom/static/tests/helpers/*.js",
        ],
        "web.assets_unit_tests_setup": [
            ("include", "opw_custom.test_helpers"),
            # Ensure all custom view code is available in the unit test harness
            "opw_custom/static/src/views/**/*.js",
            "opw_custom/static/src/views/**/*.xml",
        ],
        # JavaScript unit tests (Hoot/QUnit) - helpers must be included first
        "web.assets_unit_tests": [
            ("include", "opw_custom.test_helpers"),
            "opw_custom/static/tests/*.test.js",
        ],
        # Browser tours only - DO NOT include unit tests here
        "web.assets_tests": [
            "opw_custom/static/tests/tours/**/*.js",
        ],
    },
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}
