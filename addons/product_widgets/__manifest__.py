{
    "name": "Product Widgets",
    "version": "19.0.1.0",
    "category": "Technical",
    "author": "Shiny Computers",
    "maintainers": ["cbusillo"],
    "depends": [
        "base",
        "product",
        "web",
        "html_editor",
    ],
    "summary": "Shared widgets for product workflows",
    "data": [],
    "assets": {
        "web.assets_backend": [
            "product_widgets/static/src/scss/*.scss",
            "product_widgets/static/src/js/utils/*.js",
            "product_widgets/static/src/js/widgets/*.js",
            "product_widgets/static/src/xml/*.xml",
        ],
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
