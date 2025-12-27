{
    "name": "Disable Odoo Online",
    "version": "18.0.1.0",
    "summary": "Disable Odoo online features and publisher warranty checks",
    "description": """
Disables Odoo's online features and publisher warranty checks for offline or private deployments.
    """,
    "category": "Tools",
    "author": "Chris Busillo (Shiny Computers)",
    "maintainers": ["cbusillo"],
    "license": "LGPL-3",
    "depends": [
        "base",
        "mail_enterprise",
    ],
    "data": [
        "security/ir.model.access.csv",
    ],
    "installable": True,
    "application": False,
}
