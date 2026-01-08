{
    "name": "Web Assets Patch",
    "version": "19.0.0.1",
    "summary": "Ensure frontend SCSS variables load before Bootstrap helpers",
    "category": "Technical",
    "author": "Shiny Computers",
    "depends": ["web"],
    "assets": {
        "web._assets_helpers": [
            (
                "before",
                "web/static/lib/bootstrap/scss/_functions.scss",
                "web_assets_patch/static/src/scss/bootstrap_pre_variables.scss",
            ),
        ],
    },
    "auto_install": True,
    "installable": True,
    "license": "LGPL-3",
}
