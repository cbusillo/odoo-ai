{
    "name": "Authentik SSO",
    "version": "19.0.0.1",
    "category": "Authentication",
    "summary": "Authentik OAuth2/OpenID Connect integration",
    "description": "Authentik SSO configuration and user mapping.",
    "author": "Shiny Computers",
    "maintainers": ["cbusillo"],
    "depends": [
        "base",
        "auth_oauth",
        "auth_signup",
    ],
    "data": [
        "data/authentik_template_user.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
