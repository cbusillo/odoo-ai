{
    "name": "CM Diagnostic",
    "version": "19.0.0.1",
    "category": "Industries",
    "summary": "Diagnostic workflow for Cell Mechanic",
    "description": "Diagnostic orders and tests for device intake.",
    "author": "Shiny Computers",
    "maintainers": ["cbusillo"],
    "license": "LGPL-3",
    "depends": [
        "base",
        "mail",
        "cm_device",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/device_views.xml",
        "views/diagnostic_order_views.xml",
        "views/cm_diagnostic_actions.xml",
    ],
    "installable": True,
    "application": False,
}
