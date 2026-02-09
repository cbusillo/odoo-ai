from datetime import datetime, timedelta

from odoo import fields
from odoo.exceptions import ValidationError

from ..common_imports import UNIT_TAGS, tagged
from ..fixtures.base import UnitTestCase


@tagged(*UNIT_TAGS)
class TestCmCustom(UnitTestCase):
    def _create_partner(self, name: str) -> "odoo.model.res_partner":
        return self.Partner.create({"name": name})

    def _create_device(
        self,
        owner: "odoo.model.res_partner",
        serial_number: str,
        payer: "odoo.model.res_partner | None" = None,
    ) -> "odoo.model.service_device":
        device_model = self.DeviceModel.create({"number": f"MODEL-{serial_number}"})
        return self.Device.create(
            {
                "serial_number": serial_number,
                "model": device_model.id,
                "owner": owner.id,
                "payer": (payer or owner).id,
            }
        )

    def _create_non_admin_user(self, suffix: str) -> "odoo.model.res_users":
        return self.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": f"Test User {suffix}",
                "login": f"test_user_{suffix}@example.com",
                "email": f"test_user_{suffix}@example.com",
                "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )

    def _create_transport_order(
        self,
        client: "odoo.model.res_partner",
        contact: "odoo.model.res_partner",
        *,
        state: str = "draft",
        arrival_date: datetime | None = None,
        departure_date: datetime | None = None,
    ) -> "odoo.model.service_transport_order":
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
        quality_control_order = self.env["service.quality.control.order"].create(
            {
                "name": "Quality Control",
                "state": "started",
            }
        )
        quality_control_order_device_started = self.env[
            "service.quality.control.order.device"
        ].create(
            {
                "quality_control_order": quality_control_order.id,
                "device": device_started.id,
                "state": "started",
            }
        )
        quality_control_order_device_finished = self.env[
            "service.quality.control.order.device"
        ].create(
            {
                "quality_control_order": quality_control_order.id,
                "device": device_finished.id,
                "state": "passed",
            }
        )
        repair_batch = self.RepairBatch.create({"name": "Batch"})
        repair_batch_device_started = self.RepairBatchDevice.create(
            {
                "batch_id": repair_batch.id,
                "device_id": device_started.id,
                "state": "started",
            }
        )
        repair_batch_device_finished = self.RepairBatchDevice.create(
            {
                "batch_id": repair_batch.id,
                "device_id": device_finished.id,
                "state": "finished",
            }
        )

        self.assertIn(quality_control_order_device_started, client_partner.qc_orders)
        self.assertNotIn(quality_control_order_device_finished, client_partner.qc_orders)
        self.assertIn(repair_batch_device_started, client_partner.repair_batch_devices)
        self.assertIn(repair_batch_device_finished, client_partner.repair_batch_devices)

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

    def test_device_create_requires_payer_outside_import_context(self) -> None:
        owner_partner = self._create_partner("Missing Payer Owner")
        device_model = self.DeviceModel.create({"number": "MODEL-MISSING-PAYER"})

        with self.assertRaises(ValidationError):
            self.Device.create(
                {
                    "serial_number": "MISSING-PAYER",
                    "model": device_model.id,
                    "owner": owner_partner.id,
                }
            )

    def test_device_create_allows_blank_payer_in_import_context(self) -> None:
        owner_partner = self._create_partner("Import Owner")
        device_model = self.DeviceModel.create({"number": "MODEL-IMPORT"})

        device = self.Device.with_context(cm_skip_required_fields=True).create(
            {
                "serial_number": "IMPORT-WITHOUT-PAYER",
                "model": device_model.id,
                "owner": owner_partner.id,
            }
        )

        self.assertFalse(device.payer)
        self.assertTrue(device.is_historical_import)

    def test_device_write_cannot_clear_payer_outside_import_context(self) -> None:
        owner_partner = self._create_partner("Write Owner")
        device = self._create_device(owner_partner, "WRITE-PAYER")

        with self.assertRaises(ValidationError):
            device.write({"payer": False})

    def test_device_write_allows_clear_payer_in_import_context(self) -> None:
        owner_partner = self._create_partner("Import Write Owner")
        device = self._create_device(owner_partner, "WRITE-PAYER-IMPORT")

        device.with_context(cm_skip_required_fields=True).write({"payer": False})

        self.assertFalse(device.payer)
        self.assertTrue(device.is_historical_import)

    def test_device_write_non_admin_cannot_mark_historical(self) -> None:
        owner_partner = self._create_partner("Historical Flag Owner")
        device = self._create_device(owner_partner, "HISTORICAL-FLAG")
        non_admin_user = self._create_non_admin_user("historical_flag")

        with self.assertRaises(ValidationError):
            device.with_user(non_admin_user).write({"is_historical_import": True})

    def test_device_duplicate_preserves_historical_blank_payer(self) -> None:
        owner_partner = self._create_partner("Historical Duplicate Owner")
        device_model = self.DeviceModel.create({"number": "MODEL-HISTORICAL-DUP"})
        original_device = self.Device.with_context(cm_skip_required_fields=True).create(
            {
                "serial_number": "HISTORICAL-DUPLICATE",
                "model": device_model.id,
                "owner": owner_partner.id,
            }
        )

        duplicated_device = original_device.copy({"serial_number": "HISTORICAL-DUPLICATE-COPY"})

        self.assertFalse(duplicated_device.payer)
        self.assertTrue(duplicated_device.is_historical_import)

    def test_device_create_non_admin_cannot_set_historical_flag(self) -> None:
        owner_partner = self._create_partner("Create Guard Owner")
        non_admin_user = self._create_non_admin_user("create_guard")
        device_model = self.DeviceModel.create({"number": "MODEL-CREATE-GUARD"})

        with self.assertRaises(ValidationError):
            self.Device.with_user(non_admin_user).create(
                {
                    "serial_number": "CREATE-GUARD",
                    "model": device_model.id,
                    "owner": owner_partner.id,
                    "payer": False,
                    "is_historical_import": True,
                }
            )

    def test_device_duplicate_historical_with_payer_copies_without_historical_flag(self) -> None:
        owner_partner = self._create_partner("Historical With Payer Owner")
        payer_partner = self._create_partner("Historical With Payer Payer")
        device_model = self.DeviceModel.create({"number": "MODEL-HISTORICAL-WITH-PAYER"})
        original_device = self.Device.with_context(cm_skip_required_fields=True).create(
            {
                "serial_number": "HISTORICAL-WITH-PAYER",
                "model": device_model.id,
                "owner": owner_partner.id,
            }
        )
        original_device.write({"payer": payer_partner.id})

        duplicated_device = original_device.copy({"serial_number": "HISTORICAL-WITH-PAYER-COPY"})

        self.assertEqual(duplicated_device.payer.id, payer_partner.id)
        self.assertFalse(duplicated_device.is_historical_import)

    def test_device_duplicate_historical_blank_payer_with_payer_override_clears_historical_flag(self) -> None:
        owner_partner = self._create_partner("Historical Override Owner")
        payer_partner = self._create_partner("Historical Override Payer")
        device_model = self.DeviceModel.create({"number": "MODEL-HISTORICAL-OVERRIDE"})
        original_device = self.Device.with_context(cm_skip_required_fields=True).create(
            {
                "serial_number": "HISTORICAL-OVERRIDE",
                "model": device_model.id,
                "owner": owner_partner.id,
            }
        )

        duplicated_device = original_device.copy(
            {
                "serial_number": "HISTORICAL-OVERRIDE-COPY",
                "payer": payer_partner.id,
            }
        )

        self.assertEqual(duplicated_device.payer.id, payer_partner.id)
        self.assertFalse(duplicated_device.is_historical_import)
