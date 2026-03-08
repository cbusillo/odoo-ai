from test_support.tests.fixtures.unit_case import AdminContextUnitTestCase

from ..common_imports import common


@common.tagged(*common.UNIT_TAGS)
class UnitTestCase(AdminContextUnitTestCase):
    default_test_context = common.DEFAULT_TEST_CONTEXT
    model_aliases = {
        "Partner": "res.partner",
        "DeviceModel": "service.device.model",
        "Device": "service.device",
        "TransportOrder": "service.transport.order",
        "TransportOrderDevice": "service.transport.order.device",
        "DiagnosticOrder": "service.diagnostic.order",
        "DiagnosticOrderDevice": "service.diagnostic.order.device",
        "RepairBatch": "service.repair.batch",
        "RepairBatchDevice": "service.repair.batch.device",
    }

    @property
    def Partner(self) -> "odoo.model.res_partner":
        return self.env["res.partner"]

    @property
    def DeviceModel(self) -> "odoo.model.service_device_model":
        return self.env["service.device.model"]

    @property
    def Device(self) -> "odoo.model.service_device":
        return self.env["service.device"]

    @property
    def TransportOrder(self) -> "odoo.model.service_transport_order":
        return self.env["service.transport.order"]

    @property
    def TransportOrderDevice(self) -> "odoo.model.service_transport_order_device":
        return self.env["service.transport.order.device"]

    @property
    def DiagnosticOrder(self) -> "odoo.model.service_diagnostic_order":
        return self.env["service.diagnostic.order"]

    @property
    def DiagnosticOrderDevice(self) -> "odoo.model.service_diagnostic_order_device":
        return self.env["service.diagnostic.order.device"]

    @property
    def RepairBatch(self) -> "odoo.model.service_repair_batch":
        return self.env["service.repair.batch"]

    @property
    def RepairBatchDevice(self) -> "odoo.model.service_repair_batch_device":
        return self.env["service.repair.batch.device"]
