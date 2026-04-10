EMPLOYEE_EXTERNAL_SYSTEM_APPLICABLE_MODEL_XMLIDS = ("hr.model_hr_employee",)

EMPLOYEE_EXTERNAL_SYSTEM_DEFAULTS = {
    "discord": {
        "name": "Discord",
        "id_format": r"^\d{17,20}$",
        "url": "https://discord.com",
        "sequence": 30,
    },
    "repairshopr": {
        "name": "RepairShopr",
        "id_format": r"^\d+$",
        "url": "https://YOURSUBDOMAIN.repairshopr.com",
        "sequence": 40,
    },
    "timeclock": {
        "name": "TimeClock",
        "id_format": r"^\d+$",
        "url": "https://timeclock.example.com",
        "sequence": 50,
    },
}
