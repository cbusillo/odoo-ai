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
        "product",
        "auth_oauth",
        "auth_signup",
    ],
    "data": [
        "data/authentik_template_user.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
