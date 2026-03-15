from odoo import models
from test_support.tests.fixtures.unit_case import AdminContextUnitTestCase

from ..common_imports import common


@common.tagged(*common.UNIT_TAGS)
class UnitTestCase(AdminContextUnitTestCase):
    default_test_context = common.DEFAULT_TEST_CONTEXT
    model_aliases = {
        "Device": "service.device",
        "DeviceModel": "service.device.model",
        "IntakeOrder": "service.intake.order",
        "IntakeOrderDevice": "service.intake.order.device",
        "Partner": "res.partner",
        "RepairClaim": "service.repair.claim",
    }

    @property
    def Device(self) -> models.Model:
        return self.env["service.device"]

    @property
    def DeviceModel(self) -> models.Model:
        return self.env["service.device.model"]

    @property
    def IntakeOrder(self) -> models.Model:
        return self.env["service.intake.order"]

    @property
    def IntakeOrderDevice(self) -> models.Model:
        return self.env["service.intake.order.device"]

    @property
    def Partner(self) -> models.Model:
        return self.env["res.partner"]

    @property
    def RepairClaim(self) -> models.Model:
        return self.env["service.repair.claim"]
