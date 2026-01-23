from odoo.tests import TransactionCase

from ..common_imports import DEFAULT_TEST_CONTEXT, UNIT_TAGS, tagged


@tagged(*UNIT_TAGS)
class UnitTestCase(TransactionCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.env = cls.env(user=cls.env.ref("base.user_admin"))
        cls.env = cls.env(
            context=dict(
                cls.env.context,
                **DEFAULT_TEST_CONTEXT,
            )
        )
        cls.Partner = cls.env["res.partner"]
        cls.DeviceModel = cls.env["service.device.model"]
        cls.Device = cls.env["service.device"]
        cls.TransportOrder = cls.env["service.transport.order"]
        cls.TransportOrderDevice = cls.env["service.transport.order.device"]
        cls.DiagnosticOrder = cls.env["service.diagnostic.order"]
        cls.DiagnosticOrderDevice = cls.env["service.diagnostic.order.device"]
        cls.RepairBatch = cls.env["service.repair.batch"]
        cls.RepairBatchDevice = cls.env["service.repair.batch.device"]
