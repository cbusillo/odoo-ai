{
    "name": "External IDs Management",
    "version": "19.0.1.0.2",
    "category": "Technical",
    "summary": "Generic substrate for external-system record identity and links.",
    "description": """
        Manage external systems and assign/manage multiple external IDs per record.
    """,
    "author": "Chris Busillo (Shiny Computers)",
    "maintainers": ["cbusillo"],
    "development_status": "Beta",
    "license": "LGPL-3",
    "depends": ["base", "web"],
    "data": [
        "data/external_systems.xml",
        "security/ir.model.access.csv",
        "views/menu_views.xml",
        "views/external_system_views.xml",
        "views/external_id_views.xml",
        "views/external_system_url_views.xml",
    ],
    "installable": True,
    "application": False,
}
