{
    "name": "Discuss: Smart Record Links",
    "version": "18.0.1.0",
    "category": "Productivity/Discuss",
    "summary": "Type [ to search and insert links to products and more in Discuss/Chatter",
    "depends": [
        "base",
        "mail",
        "stock",
        "web",
        "web_editor",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/record_link_config_data.xml",
        "views/record_link_config_views.xml",
        "views/res_config_settings_view.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "discuss_record_links/static/src/js/*.js",
        ],
        "web.assets_unit_tests_setup": [
            "discuss_record_links/static/src/js/*.js",
        ],
        "web.assets_unit_tests": [
            "discuss_record_links/static/tests/*.test.js",
        ],
        "web.assets_tests": [
            "discuss_record_links/static/tests/tours/*.js",
        ],
    },
    "application": False,
    "license": "LGPL-3",
    "installable": True,
}
