{
    "name": "Environment Overrides",
    "version": "19.0.0.1",
    "category": "Technical",
    "summary": "Apply environment-specific overrides during restore workflows",
    "description": "Centralized environment overrides for restore and upgrade workflows.",
    "author": "Shiny Computers",
    "maintainers": ["cbusillo"],
    "depends": [
        "base",
        "mail",
        "product",
        "web",
    ],
    "data": [],
    "assets": {
        "web.assets_backend": [
            "environment_overrides/static/src/js/notification_permission_patch.js",
        ],
        "web.assets_unit_tests": [
            "environment_overrides/static/tests/*.test.js",
        ],
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
