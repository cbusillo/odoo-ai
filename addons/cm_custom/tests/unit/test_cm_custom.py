from datetime import timedelta

from odoo import fields

from ..common_imports import UNIT_TAGS, tagged
from ..fixtures.base import UnitTestCase


@tagged(*UNIT_TAGS)
class TestCmCustom(UnitTestCase):
    def _create_partner(self, name: str):
        return self.Partner.create({"name": name})

    def _create_device(self, owner, serial_number: str):
        device_model = self.DeviceModel.create({"number": f"MODEL-{serial_number}"})
        return self.Device.create(
            {
                "serial_number": serial_number,
                "model": device_model.id,
                "owner": owner.id,
            }
        )

    def _create_transport_order(
        self,
        client,
        contact,
        *,
        state: str = "draft",
        arrival_date: object = None,
        departure_date: object = None,
    ):
        return self.TransportOrder.create(
            {
                "client": client.id,
                "contact": contact.id,
                "employee": self.env.user.partner_id.id,
                "state": state,
                "arrival_date": arrival_date,
                "departure_date": departure_date,
            }
        )

    def test_average_time_on_location_per_device(self) -> None:
        client_partner = self._create_partner("Client")
        contact_partner = self._create_partner("Contact")
        reference_time = fields.Datetime.now()
        self._create_transport_order(
            client_partner,
            contact_partner,
            arrival_date=reference_time - timedelta(hours=1),
            departure_date=reference_time - timedelta(hours=5),
        )
        self._create_transport_order(
            client_partner,
            contact_partner,
            arrival_date=reference_time,
            departure_date=reference_time - timedelta(hours=3),
        )

        average_hours = client_partner.average_time_on_location_per_device

        self.assertAlmostEqual(average_hours, 3.5, places=2)

    def test_average_time_defaults_to_zero_without_durations(self) -> None:
        client_partner = self._create_partner("Client Without Orders")

        self.assertEqual(client_partner.average_time_on_location_per_device, 0.0)

    def test_devices_at_depot_respects_closed_orders(self) -> None:
        client_partner = self._create_partner("Device Client")
        contact_partner = self._create_partner("Device Contact")
        device_at_depot = self._create_device(client_partner, "DEPOT-1")
        device_closed = self._create_device(client_partner, "CLOSED-1")
        open_order = self._create_transport_order(
            client_partner,
            contact_partner,
            state="at_depot",
        )
        closed_order = self._create_transport_order(
            client_partner,
            contact_partner,
            state="intake_complete",
        )
        self.TransportOrderDevice.create(
            {
                "transport_order": open_order.id,
                "device": device_at_depot.id,
                "movement_type": "in",
            }
        )
        self.TransportOrderDevice.create(
            {
                "transport_order": closed_order.id,
                "device": device_closed.id,
                "movement_type": "out",
            }
        )

        devices_at_depot = client_partner.devices_at_depot

        self.assertIn(device_at_depot, devices_at_depot)
        self.assertNotIn(device_closed, devices_at_depot)

    def test_diagnostic_orders_computed_from_devices(self) -> None:
        client_partner = self._create_partner("Diagnostic Client")
        device = self._create_device(client_partner, "DIAG-1")
        diagnostic_order = self.DiagnosticOrder.create({"state": "started"})
        self.DiagnosticOrderDevice.create(
            {
                "diagnostic_order": diagnostic_order.id,
                "device": device.id,
                "state": "started",
            }
        )

        diagnostic_orders = client_partner.diagnostic_orders

        self.assertIn(diagnostic_order, diagnostic_orders)

    def test_qc_orders_and_repair_batch_devices(self) -> None:
        client_partner = self._create_partner("Repair Client")
        device_started = self._create_device(client_partner, "QC-START")
        device_finished = self._create_device(client_partner, "QC-FINISH")
        repair_batch = self.RepairBatch.create({"name": "Batch"})
        started_line = self.RepairBatchDevice.create(
            {
                "batch_id": repair_batch.id,
                "device_id": device_started.id,
                "state": "started",
            }
        )
        finished_line = self.RepairBatchDevice.create(
            {
                "batch_id": repair_batch.id,
                "device_id": device_finished.id,
                "state": "finished",
            }
        )

        self.assertIn(started_line, client_partner.qc_orders)
        self.assertNotIn(finished_line, client_partner.qc_orders)
        self.assertIn(started_line, client_partner.repair_batch_devices)
        self.assertIn(finished_line, client_partner.repair_batch_devices)

    def test_transport_order_device_onchange_sets_scan_date(self) -> None:
        client_partner = self._create_partner("Scan Client")
        contact_partner = self._create_partner("Scan Contact")
        device = self._create_device(client_partner, "SCAN-1")
        transport_order = self._create_transport_order(client_partner, contact_partner)
        record = self.TransportOrderDevice.new(
            {
                "transport_order": transport_order.id,
                "device": device.id,
                "movement_type": "in",
            }
        )

        record.verification_scan = "scan-value"
        record._onchange_verification_scan()

        self.assertTrue(record.scan_date)
