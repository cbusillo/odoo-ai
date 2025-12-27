{
    "name": "HR Employee Name Extended",
    "version": "18.0.4.0.0",
    "category": "Human Resources",
    "summary": "Separate first/last names with flexible formatting",
    "description": """
Manage employee names with separate first, last, and nickname fields.
Supports different name formats for international use.
    """,
    "author": "Chris Busillo (Shiny Computers)",
    "maintainers": ["cbusillo"],
    "depends": [
        "hr",
        "base_setup",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/hr_employee_views.xml",
        "views/res_config_settings_views.xml",
        "views/server_actions.xml",
        "views/menu.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
