import json
from unittest.mock import patch

from ...models.repairshopr_importer import (
    REPAIRSHOPR_PHASE_ESTIMATES,
    REPAIRSHOPR_PHASE_INVOICES,
    REPAIRSHOPR_PHASE_TICKETS,
    REPAIRSHOPR_PHASE_TRANSPORT_BACKFILL,
    REPAIRSHOPR_RESUME_STATE_PARAM,
    REPAIRSHOPR_RESUME_STATE_VERSION,
)
from ..common_imports import common
from ..fixtures.base import UnitTestCase


class _ClientStub:
    def clear_cache(self) -> None:
        return None


@common.tagged(*common.UNIT_TAGS)
class TestRepairshoprResumeState(UnitTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.importer = self.RepairshoprImporter
        self.parameter_model = self.env["ir.config_parameter"].sudo()

    def test_get_resume_state_clears_invalid_phase(self) -> None:
        self.parameter_model.set_param(
            REPAIRSHOPR_RESUME_STATE_PARAM,
            json.dumps(
                {
                    "version": REPAIRSHOPR_RESUME_STATE_VERSION,
                    "phase": "bogus",
                    "ticket_after_id": 99,
                }
            ),
        )

        resume_state = self.importer._get_resume_state()

        self.assertEqual(resume_state["phase"], "customers")
        self.assertFalse(self.parameter_model.get_param(REPAIRSHOPR_RESUME_STATE_PARAM))

    def test_advance_resume_state_clears_phase_cursor(self) -> None:
        self.importer._set_resume_state(
            {
                "version": REPAIRSHOPR_RESUME_STATE_VERSION,
                "phase": REPAIRSHOPR_PHASE_TICKETS,
                "ticket_after_id": 321,
                "estimate_after_id": 654,
                "invoice_after_id": 987,
            }
        )

        state = self.importer._advance_resume_state(REPAIRSHOPR_PHASE_TICKETS)

        self.assertEqual(state["phase"], REPAIRSHOPR_PHASE_ESTIMATES)
        self.assertIsNone(state["ticket_after_id"])
        self.assertEqual(state["estimate_after_id"], 654)
        self.assertEqual(state["invoice_after_id"], 987)

    def test_run_import_resumes_from_saved_phase(self) -> None:
        self.importer._set_resume_state(
            {
                "version": REPAIRSHOPR_RESUME_STATE_VERSION,
                "phase": REPAIRSHOPR_PHASE_ESTIMATES,
                "ticket_after_id": 321,
                "estimate_after_id": 654,
                "invoice_after_id": 987,
            }
        )
        importer_class = type(self.importer)

        with (
            patch.object(importer_class, "_build_client", autospec=True, return_value=_ClientStub()),
            patch.object(importer_class, "_import_customers", autospec=True) as import_customers,
            patch.object(importer_class, "_import_products", autospec=True) as import_products,
            patch.object(importer_class, "_import_tickets", autospec=True) as import_tickets,
            patch.object(importer_class, "_import_estimates", autospec=True) as import_estimates,
            patch.object(importer_class, "_import_invoices", autospec=True) as import_invoices,
            patch.object(importer_class, "_backfill_transport_order_devices", autospec=True) as transport_backfill,
        ):
            self.importer._run_import(update_last_sync=False)

        import_customers.assert_not_called()
        import_products.assert_not_called()
        import_tickets.assert_not_called()
        import_estimates.assert_called_once()
        import_invoices.assert_called_once()
        transport_backfill.assert_called_once()

        self.assertEqual(import_estimates.call_args.kwargs["resume_after_id"], 654)
        self.assertEqual(import_invoices.call_args.kwargs["resume_after_id"], 987)
        self.assertFalse(self.parameter_model.get_param(REPAIRSHOPR_RESUME_STATE_PARAM))
