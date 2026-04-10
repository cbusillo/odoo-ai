{
    "name": "Environment Banner",
    "version": "19.0.0.1",
    "category": "Technical",
    "summary": "Show a non-production banner in the backend",
    "description": """
Display a backend banner for non-production environments.
    """,
    "author": "Shiny Computers",
    "maintainers": ["cbusillo"],
    "depends": [
        "web",
    ],
    "data": [],
    "assets": {
        "web.assets_backend": [
            "environment_banner/static/src/scss/*.scss",
            "environment_banner/static/src/js/*.js",
            "environment_banner/static/src/xml/*.xml",
        ],
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
