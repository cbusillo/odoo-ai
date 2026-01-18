import logging

from odoo import models

from ..services.fishbowl_client import FishbowlClient
from . import fishbowl_rows
from .fishbowl_import_constants import EXTERNAL_SYSTEM_CODE, IMPORT_CONTEXT, RESOURCE_UNIT

_logger = logging.getLogger(__name__)


# External Fishbowl schema; SQL resolver has no catalog.
# noinspection SqlResolve
class FishbowlImporterUnits(models.Model):
    _inherit = "fishbowl.importer"

    def _import_units_of_measure(self, client: FishbowlClient) -> None:
        unit_rows = self._fetch_rows(
            client,
            fishbowl_rows.UNIT_ROWS_ADAPTER,
            "SELECT id, name, code, uomType, defaultRecord, integral, activeFlag FROM uom ORDER BY id",
        )
        conversion_rows = self._fetch_rows(
            client,
            fishbowl_rows.UNIT_CONVERSION_ROWS_ADAPTER,
            "SELECT fromUomId, toUomId, factor, multiply FROM uomconversion ORDER BY id",
        )
        reference_by_type, _unit_ids_by_type = self._build_reference_units(unit_rows)

        ratios_by_id = self._compute_unit_ratios(unit_rows, conversion_rows)
        unit_model = self.env["uom.uom"].sudo().with_context(IMPORT_CONTEXT)
        reference_unit_map: dict[int, int] = {}
        for row in unit_rows:
            fishbowl_unit_id = row.id
            unit_type_id = row.uomType or 0
            reference_unit_id = reference_by_type.get(unit_type_id)
            if not reference_unit_id or reference_unit_id != fishbowl_unit_id:
                continue
            name = str(row.name or "").strip() or f"Unit {fishbowl_unit_id}"
            values: "odoo.values.uom_uom" = {
                "name": name,
                "relative_factor": 1.0,
                "relative_uom_id": False,
                "active": self._to_bool(row.activeFlag),
            }
            unit = unit_model.get_or_create_by_external_id(
                EXTERNAL_SYSTEM_CODE,
                str(fishbowl_unit_id),
                values,
                RESOURCE_UNIT,
            )
            reference_unit_map[fishbowl_unit_id] = unit.id

        for row in unit_rows:
            fishbowl_unit_id = row.id
            unit_type_id = row.uomType or 0
            reference_unit_id = reference_by_type.get(unit_type_id)
            if not reference_unit_id:
                _logger.warning("Missing reference UoM for Fishbowl unit %s", fishbowl_unit_id)
                continue
            reference_odoo_id = reference_unit_map.get(reference_unit_id)
            if not reference_odoo_id:
                _logger.warning("Missing reference mapping for Fishbowl unit %s", fishbowl_unit_id)
                continue
            name = str(row.name or "").strip() or f"Unit {fishbowl_unit_id}"
            ratio = ratios_by_id.get(fishbowl_unit_id)
            if ratio is None:
                ratio = 1.0
                _logger.warning("Missing conversion ratio for Fishbowl unit %s; defaulting to 1.0", fishbowl_unit_id)
            values: "odoo.values.uom_uom" = {
                "name": name,
                "relative_factor": float(ratio),
                "relative_uom_id": reference_odoo_id,
                "active": self._to_bool(row.activeFlag),
            }
            if fishbowl_unit_id == reference_unit_id:
                values["relative_factor"] = 1.0
                values["relative_uom_id"] = False
            unit_model.get_or_create_by_external_id(
                EXTERNAL_SYSTEM_CODE,
                str(fishbowl_unit_id),
                values,
                RESOURCE_UNIT,
            )

    def _compute_unit_ratios(
        self,
        unit_rows: list[fishbowl_rows.UnitRow],
        conversion_rows: list[fishbowl_rows.UnitConversionRow],
    ) -> dict[int, float]:
        reference_by_type, unit_ids_by_type = self._build_reference_units(unit_rows)

        adjacency: dict[int, list[tuple[int, float]]] = {}
        for row in conversion_rows:
            from_id = row.fromUomId
            to_id = row.toUomId
            factor = float(row.factor or 1)
            multiply = float(row.multiply or 1)
            if factor == 0:
                continue
            ratio = multiply / factor
            adjacency.setdefault(from_id, []).append((to_id, ratio))
            adjacency.setdefault(to_id, []).append((from_id, 1 / ratio))

        ratios: dict[int, float] = {}
        for reference_id in reference_by_type.values():
            ratios[reference_id] = 1.0
            queue: list[int] = [reference_id]
            while queue:
                current_id = queue.pop(0)
                current_ratio = ratios[current_id]
                for neighbor_id, neighbor_ratio in adjacency.get(current_id, []):
                    if neighbor_id in ratios:
                        continue
                    ratios[neighbor_id] = current_ratio * neighbor_ratio
                    queue.append(neighbor_id)

        return ratios

    def _build_reference_units(
        self,
        unit_rows: list[fishbowl_rows.UnitRow],
    ) -> tuple[dict[int, int], dict[int, list[int]]]:
        reference_by_type: dict[int, int] = {}
        unit_ids_by_type: dict[int, list[int]] = {}
        for row in unit_rows:
            unit_type_id = row.uomType or 0
            unit_id = row.id
            if unit_type_id:
                unit_ids_by_type.setdefault(unit_type_id, []).append(unit_id)
            if self._to_bool(row.defaultRecord) and unit_type_id:
                reference_by_type[unit_type_id] = unit_id

        for unit_type_id, unit_ids in unit_ids_by_type.items():
            if unit_type_id not in reference_by_type and unit_ids:
                reference_by_type[unit_type_id] = unit_ids[0]
        return reference_by_type, unit_ids_by_type
