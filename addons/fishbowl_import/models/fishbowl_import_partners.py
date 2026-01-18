import logging

from odoo import models

from ..services.fishbowl_client import FishbowlClient
from . import fishbowl_rows
from .fishbowl_import_constants import EXTERNAL_SYSTEM_CODE, IMPORT_CONTEXT, RESOURCE_ADDRESS, RESOURCE_CUSTOMER, RESOURCE_VENDOR

_logger = logging.getLogger(__name__)


# External Fishbowl schema; SQL resolver has no catalog.
# noinspection SqlResolve
class FishbowlImporterPartners(models.Model):
    _inherit = "fishbowl.importer"

    def _import_partners(self, client: FishbowlClient) -> dict[str, dict[int, int]]:
        customer_rows = self._fetch_rows(
            client,
            fishbowl_rows.CUSTOMER_ROWS_ADAPTER,
            "SELECT id, accountId, number, name, note, activeFlag FROM customer ORDER BY id",
        )
        vendor_rows = self._fetch_rows(
            client,
            fishbowl_rows.VENDOR_ROWS_ADAPTER,
            "SELECT id, accountId, name, accountNum, note, activeFlag FROM vendor ORDER BY id",
        )
        address_rows = self._fetch_rows(
            client,
            fishbowl_rows.ADDRESS_ROWS_ADAPTER,
            "SELECT id, accountId, name, addressName, address, city, stateId, countryId, zip, typeId FROM address ORDER BY id",
        )
        address_type_rows = self._fetch_rows(
            client,
            fishbowl_rows.ADDRESS_TYPE_ROWS_ADAPTER,
            "SELECT id, name FROM addresstype ORDER BY id",
        )
        country_rows = self._fetch_rows(
            client,
            fishbowl_rows.COUNTRY_ROWS_ADAPTER,
            "SELECT id, name, abbreviation FROM countryconst ORDER BY id",
        )
        state_rows = self._fetch_rows(
            client,
            fishbowl_rows.STATE_ROWS_ADAPTER,
            "SELECT id, countryConstID, name, code FROM stateconst ORDER BY id",
        )

        address_type_map = {row.id: str(row.name or "").strip() for row in address_type_rows}
        country_map = {row.id: row for row in country_rows}
        state_map = {row.id: row for row in state_rows}

        partner_model = self.env["res.partner"].sudo().with_context(IMPORT_CONTEXT)
        account_partner_map: dict[int, int] = {}
        customer_partner_map: dict[int, int] = {}
        vendor_partner_map: dict[int, int] = {}

        for row in customer_rows:
            fishbowl_id = row.id
            values: "odoo.values.res_partner" = {
                "name": str(row.name or "").strip() or f"Customer {fishbowl_id}",
                "ref": str(row.number or "").strip() or False,
                "comment": row.note or False,
                "active": self._to_bool(row.activeFlag),
                "customer_rank": 1,
            }
            partner = partner_model.get_or_create_by_external_id(
                EXTERNAL_SYSTEM_CODE,
                str(fishbowl_id),
                values,
                RESOURCE_CUSTOMER,
            )
            account_id = row.accountId
            if account_id is not None:
                account_partner_map[account_id] = partner.id
            customer_partner_map[fishbowl_id] = partner.id

        for row in vendor_rows:
            fishbowl_id = row.id
            values: "odoo.values.res_partner" = {
                "name": str(row.name or "").strip() or f"Vendor {fishbowl_id}",
                "ref": str(row.accountNum or "").strip() or False,
                "comment": row.note or False,
                "active": self._to_bool(row.activeFlag),
                "supplier_rank": 1,
            }
            partner = partner_model.get_or_create_by_external_id(
                EXTERNAL_SYSTEM_CODE,
                str(fishbowl_id),
                values,
                RESOURCE_VENDOR,
            )
            account_id = row.accountId
            if account_id is not None:
                account_partner_map.setdefault(account_id, partner.id)
            vendor_partner_map[fishbowl_id] = partner.id

        address_type_mapping = {
            "ship to": "delivery",
            "bill to": "invoice",
            "remit to": "invoice",
            "home": "other",
            "main office": "contact",
        }

        for row in address_rows:
            fishbowl_id = row.id
            account_id = row.accountId
            if account_id is None:
                continue
            parent_id = account_partner_map.get(account_id)
            if not parent_id:
                continue
            address_type_name = address_type_map.get(row.typeId or 0, "")
            partner_type = address_type_mapping.get(address_type_name.lower(), "other")
            country_id = self._resolve_country_id(row.countryId, country_map)
            state_id = self._resolve_state_id(row.stateId, state_map, country_map, country_id)
            values: "odoo.values.res_partner" = {
                "parent_id": parent_id,
                "type": partner_type,
                "name": str(row.addressName or row.name or "").strip() or False,
                "street": str(row.address or "").strip() or False,
                "city": str(row.city or "").strip() or False,
                "zip": str(row.zip or "").strip() or False,
                "country_id": country_id or False,
                "state_id": state_id or False,
            }
            partner_model.get_or_create_by_external_id(
                EXTERNAL_SYSTEM_CODE,
                str(fishbowl_id),
                values,
                RESOURCE_ADDRESS,
            )

        return {
            "account": account_partner_map,
            "customer": customer_partner_map,
            "vendor": vendor_partner_map,
        }

    def _resolve_country_id(
        self,
        country_id: int | None,
        country_map: dict[int, fishbowl_rows.CountryRow],
    ) -> int | None:
        if not country_id:
            return None
        country_record = country_map.get(country_id)
        if not country_record:
            return None
        code = str(country_record.abbreviation or "").strip()
        if not code:
            return None
        country = self.env["res.country"].sudo().search([("code", "=", code)], limit=1)
        return country.id if country else None

    def _resolve_state_id(
        self,
        state_id: int | None,
        state_map: dict[int, fishbowl_rows.StateRow],
        country_map: dict[int, fishbowl_rows.CountryRow],
        country_id: int | None,
    ) -> int | None:
        if not state_id:
            return None
        state_record = state_map.get(state_id)
        if not state_record:
            return None
        code = str(state_record.code or "").strip()
        if not code:
            return None
        domain = [("code", "=", code)]
        if country_id:
            domain.append(("country_id", "=", country_id))
        state = self.env["res.country.state"].sudo().search(domain, limit=1)
        if state:
            return state.id
        country_record = country_map.get(state_record.countryConstID or 0)
        if not country_record:
            return None
        country_code = str(country_record.abbreviation or "").strip()
        if not country_code:
            return None
        country = self.env["res.country"].sudo().search([("code", "=", country_code)], limit=1)
        if not country:
            return None
        state = (
            self.env["res.country.state"]
            .sudo()
            .search(
                [("code", "=", code), ("country_id", "=", country.id)],
                limit=1,
            )
        )
        return state.id if state else None
