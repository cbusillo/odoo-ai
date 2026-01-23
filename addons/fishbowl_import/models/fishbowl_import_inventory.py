import logging

from odoo import models
from odoo.tools.float_utils import float_is_zero

from ..services.fishbowl_client import FishbowlClient, chunked
from . import fishbowl_rows
from .fishbowl_import_constants import IMPORT_CONTEXT

_logger = logging.getLogger(__name__)


# External Fishbowl schema; SQL resolver has no catalog.
# noinspection SqlResolve
class FishbowlImporterInventory(models.Model):
    _inherit = "fishbowl.importer"

    def _import_on_hand(self, client: FishbowlClient, product_maps: dict[str, dict[int, int]]) -> None:
        stock_location = self._get_location("internal")
        stock_location_id = stock_location.id
        quant_model = self.env["stock.quant"].sudo().with_context(IMPORT_CONTEXT, active_test=False)
        product_model = self.env["product.product"].sudo().with_context(IMPORT_CONTEXT, active_test=False)
        commit_interval = self._get_commit_interval()
        update_count = 0
        inventory_rows = fishbowl_rows.INVENTORY_ROWS_ADAPTER.validate_python(
            client.fetch_all("SELECT partId, SUM(qtyOnHand) AS qtyOnHand FROM qtyinventorytotals GROUP BY partId")
        )
        if not inventory_rows:
            _logger.warning("Fishbowl on-hand returned no rows; skipping on-hand sync.")
            return
        fishbowl_part_ids: set[int] = set()
        def refresh_stock_models() -> None:
            nonlocal stock_location, quant_model
            self._commit_and_clear()
            stock_location = self.env["stock.location"].browse(stock_location_id)
            quant_model = self.env["stock.quant"].sudo().with_context(IMPORT_CONTEXT, active_test=False)

        def refresh_inventory_models() -> None:
            nonlocal product_model
            refresh_stock_models()
            product_model = self.env["product.product"].sudo().with_context(IMPORT_CONTEXT, active_test=False)

        for row in inventory_rows:
            if row.partId is None:
                continue
            fishbowl_part_ids.add(row.partId)
            product_id = product_maps["part"].get(row.partId)
            if not product_id:
                continue
            product = product_model.browse(product_id)
            if not self._is_stockable_product(product):
                continue
            target_quantity = float(row.qtyOnHand or 0)
            current_quantity = product.with_context(active_test=False, location=stock_location.id).qty_available
            delta_quantity = target_quantity - current_quantity
            if float_is_zero(delta_quantity, precision_rounding=product.uom_id.rounding):
                continue
            quant_model._update_available_quantity(product, stock_location, delta_quantity)
            update_count += 1
            if commit_interval > 0 and update_count % commit_interval == 0:
                refresh_inventory_models()

        # Clear any lingering on-hand quantities for parts no longer reported by Fishbowl.
        missing_part_ids = set(product_maps["part"]) - fishbowl_part_ids
        if missing_part_ids:
            missing_product_ids = [product_maps["part"][part_id] for part_id in missing_part_ids if part_id in product_maps["part"]]
            cleared_count = 0
            for batch in chunked(missing_product_ids, 500):
                group_rows = quant_model._read_group(
                    [
                        ("product_id", "in", batch),
                        ("location_id", "=", stock_location.id),
                        ("quantity", "!=", 0),
                    ],
                    ["product_id"],
                    ["quantity:sum"],
                )
                if not group_rows:
                    continue
                for product, group_quantity in group_rows:
                    if not product or not self._is_stockable_product(product):
                        continue
                    if float_is_zero(group_quantity, precision_rounding=product.uom_id.rounding):
                        continue
                    quant_model._update_available_quantity(product, stock_location, -float(group_quantity))
                    cleared_count += 1
                    update_count += 1
                    if commit_interval > 0 and update_count % commit_interval == 0:
                        refresh_stock_models()
            if cleared_count:
                _logger.info("Fishbowl import: cleared on-hand for %s stale products", cleared_count)
        self._commit_and_clear()
