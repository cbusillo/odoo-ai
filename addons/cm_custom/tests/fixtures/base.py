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
        cls.DeviceModel = cls.env["device.model"]
        cls.Device = cls.env["device"]
        cls.TransportOrder = cls.env["transport.order"]
        cls.TransportOrderDevice = cls.env["transport.order.device"]
        cls.DiagnosticOrder = cls.env["diagnostic.order"]
        cls.DiagnosticOrderDevice = cls.env["diagnostic.order.device"]
        cls.RepairBatch = cls.env["repair.batch"]
        cls.RepairBatchDevice = cls.env["repair.batch.device"]

