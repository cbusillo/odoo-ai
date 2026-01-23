from datetime import datetime

from odoo import models

from ..services import repairshopr_sync_models as repairshopr_models
from ..services.repairshopr_sync_client import RepairshoprSyncClient
from .repairshopr_importer import EXTERNAL_SYSTEM_CODE, IMPORT_CONTEXT, RESOURCE_CONTACT, RESOURCE_CUSTOMER


class RepairshoprImporter(models.Model):
    _inherit = "repairshopr.importer"

    def _import_customers(
        self,
        repairshopr_client: RepairshoprSyncClient,
        start_datetime: datetime | None,
        system: "odoo.model.external_system",
        sync_started_at: datetime,
    ) -> None:
        partner_model = self.env["res.partner"].sudo().with_context(IMPORT_CONTEXT)
        commit_interval = self._get_commit_interval()
        processed_count = 0
        customers = repairshopr_client.get_model(repairshopr_models.Customer, updated_at=start_datetime)
        for customer in customers:
            external_id_value = str(customer.id)
            if not self._should_process_external_row(
                system,
                external_id_value,
                RESOURCE_CUSTOMER,
                customer.updated_at,
            ):
                continue
            partner = partner_model.search_by_external_id(
                EXTERNAL_SYSTEM_CODE,
                external_id_value,
                RESOURCE_CUSTOMER,
            )
            values = self._build_partner_values_from_customer(customer)
            if partner:
                partner.write(values)
            else:
                partner = partner_model.create(values)
                partner.set_external_id(EXTERNAL_SYSTEM_CODE, external_id_value, RESOURCE_CUSTOMER)
            self._mark_external_id_synced(
                system,
                external_id_value,
                RESOURCE_CUSTOMER,
                customer.updated_at or sync_started_at,
            )
            self._ensure_customer_phone_contacts(partner_model, partner, customer)
            self._import_contacts(partner_model, partner, customer, system, sync_started_at)
            processed_count += 1
            if self._maybe_commit(processed_count, commit_interval, label="customer"):
                partner_model = self.env["res.partner"].sudo().with_context(IMPORT_CONTEXT)

    def _import_contacts(
        self,
        partner_model: "odoo.model.res_partner",
        parent_partner: "odoo.model.res_partner",
        customer: repairshopr_models.Customer,
        system: "odoo.model.external_system",
        sync_started_at: datetime,
    ) -> None:
        if not customer.contacts:
            return
        for contact in customer.contacts:
            external_id_value = str(contact.id)
            contact_partner = partner_model.search_by_external_id(
                EXTERNAL_SYSTEM_CODE,
                external_id_value,
                RESOURCE_CONTACT,
            )
            values = self._build_partner_values_from_contact(contact, parent_partner)
            if contact_partner:
                contact_partner.write(values)
            else:
                contact_partner = partner_model.create(values)
                contact_partner.set_external_id(EXTERNAL_SYSTEM_CODE, external_id_value, RESOURCE_CONTACT)
            self._mark_external_id_synced(
                system,
                external_id_value,
                RESOURCE_CONTACT,
                customer.updated_at or sync_started_at,
            )
            self._ensure_contact_phone_contacts(partner_model, parent_partner, contact_partner, contact)

    def _build_partner_values_from_customer(self, customer: repairshopr_models.Customer) -> "odoo.values.res_partner":
        name = self._build_customer_name(customer)
        state_id, country_id = self._resolve_state_and_country(customer.state)
        email_value = customer.email if not customer.no_email else None
        phone_value = self._select_primary_phone(customer.phone, customer.mobile)
        values = {
            "name": name,
            "company_type": "company" if customer.business_name else "person",
            "is_company": bool(customer.business_name),
            "email": email_value,
            "phone": phone_value,
            "street": customer.address,
            "street2": customer.address_2,
            "city": customer.city,
            "zip": customer.zip,
            "comment": customer.notes or None,
            "customer_rank": 1,
            "active": not bool(customer.disabled),
        }
        if state_id:
            values["state_id"] = state_id
        if country_id:
            values["country_id"] = country_id
        return values

    def _build_partner_values_from_contact(
        self,
        contact: repairshopr_models.Contact,
        parent_partner: "odoo.model.res_partner",
    ) -> "odoo.values.res_partner":
        name = self._build_contact_name(contact)
        state_id, country_id = self._resolve_state_and_country(contact.state)
        contact_phone, contact_mobile = self._select_contact_phone_values(contact)
        phone_value = self._select_primary_phone(contact_phone, contact_mobile)
        values = {
            "name": name,
            "company_type": "person",
            "is_company": False,
            "email": contact.email,
            "phone": phone_value,
            "street": contact.address1,
            "street2": contact.address2,
            "city": contact.city,
            "zip": contact.zip,
            "comment": contact.notes or None,
            "parent_id": parent_partner.id if parent_partner else False,
            "type": "contact",
            "active": True,
        }
        if state_id:
            values["state_id"] = state_id
        if country_id:
            values["country_id"] = country_id
        return values

    @staticmethod
    def _select_primary_phone(phone_value: str | None, mobile_value: str | None) -> str | None:
        return phone_value or mobile_value

    def _select_contact_phone_values(self, contact: repairshopr_models.Contact) -> tuple[str | None, str | None]:
        phone_value = contact.processed_phone or contact.phone
        phone_value = self._apply_extension(phone_value, contact.extension)
        mobile_value = contact.processed_mobile or contact.mobile
        return phone_value, mobile_value

    @staticmethod
    def _apply_extension(phone_value: str | None, extension: str | None) -> str | None:
        if not phone_value:
            return None
        if not extension:
            return phone_value
        return f"{phone_value} x{extension}"

    def _ensure_customer_phone_contacts(
        self,
        partner_model: "odoo.model.res_partner",
        parent_partner: "odoo.model.res_partner",
        customer: repairshopr_models.Customer,
    ) -> None:
        primary_phone = self._select_primary_phone(customer.phone, customer.mobile)
        entries = self._build_additional_phone_entries(
            primary_phone=primary_phone,
            phone_value=customer.phone,
            mobile_value=customer.mobile,
        )
        base_name = parent_partner.name or self._build_customer_name(customer)
        self._ensure_phone_contacts(partner_model, parent_partner, base_name, entries)

    def _ensure_contact_phone_contacts(
        self,
        partner_model: "odoo.model.res_partner",
        parent_partner: "odoo.model.res_partner",
        contact_partner: "odoo.model.res_partner",
        contact: repairshopr_models.Contact,
    ) -> None:
        contact_phone, contact_mobile = self._select_contact_phone_values(contact)
        primary_phone = self._select_primary_phone(contact_phone, contact_mobile)
        entries = self._build_additional_phone_entries(
            primary_phone=primary_phone,
            phone_value=contact_phone,
            mobile_value=contact_mobile,
        )
        base_name = contact_partner.name or self._build_contact_name(contact)
        parent_for_phones = parent_partner or contact_partner
        self._ensure_phone_contacts(partner_model, parent_for_phones, base_name, entries)

    @staticmethod
    def _build_additional_phone_entries(
        *,
        primary_phone: str | None,
        phone_value: str | None,
        mobile_value: str | None,
    ) -> list[tuple[str, str]]:
        entries: list[tuple[str, str]] = []
        if phone_value and phone_value != primary_phone:
            entries.append(("Office", phone_value))
        if mobile_value and mobile_value != primary_phone and mobile_value != phone_value:
            entries.append(("Mobile", mobile_value))
        return entries

    def _ensure_phone_contacts(
        self,
        partner_model: "odoo.model.res_partner",
        parent_partner: "odoo.model.res_partner",
        base_name: str,
        entries: list[tuple[str, str]],
    ) -> None:
        if not parent_partner or not entries:
            return
        for label, phone_value in entries:
            if not phone_value:
                continue
            contact_name = self._build_phone_contact_name(base_name, label)
            existing_contact = partner_model.search(
                [
                    ("parent_id", "=", parent_partner.id),
                    ("phone", "=", phone_value),
                    ("type", "=", "contact"),
                ],
                limit=1,
            )
            values = {
                "name": contact_name,
                "company_type": "person",
                "is_company": False,
                "phone": phone_value,
                "parent_id": parent_partner.id,
                "type": "contact",
                "active": True,
            }
            if existing_contact:
                existing_contact.write(values)
            else:
                partner_model.create(values)

    @staticmethod
    def _build_phone_contact_name(base_name: str, label: str) -> str:
        base_name = base_name or "RepairShopr Contact"
        return f"{base_name} - {label}"

    @staticmethod
    def _build_customer_name(customer: repairshopr_models.Customer) -> str:
        if customer.business_name:
            return customer.business_name
        if customer.fullname:
            return customer.fullname
        name_parts = [customer.firstname, customer.lastname]
        joined = " ".join(part for part in name_parts if part)
        return joined or f"RepairShopr Customer {customer.id}"

    @staticmethod
    def _build_contact_name(contact: repairshopr_models.Contact) -> str:
        if contact.name:
            return contact.name
        if contact.email:
            return contact.email
        return f"RepairShopr Contact {contact.id}"

    def _resolve_state_and_country(self, state_value: str | None) -> tuple[int | None, int | None]:
        if not state_value:
            return None, None
        state_model = self.env["res.country.state"].sudo()
        state = state_model.search([("code", "=", state_value)], limit=1)
        if not state:
            state = state_model.search([("name", "ilike", state_value)], limit=1)
        if state:
            return state.id, state.country_id.id
        country_model = self.env["res.country"].sudo()
        country = country_model.search([("code", "=", "US")], limit=1)
        if country:
            state = state_model.search(
                [
                    ("country_id", "=", country.id),
                    ("code", "=", state_value),
                ],
                limit=1,
            )
            if state:
                return state.id, country.id
        return None, None

    def _get_or_create_partner_by_customer_id(
        self,
        customer_id: int | None,
        fallback_name: str | None,
    ) -> "odoo.model.res_partner":
        if not customer_id:
            return self.env["res.partner"].browse()
        partner_model = self.env["res.partner"].sudo().with_context(IMPORT_CONTEXT)
        partner = partner_model.search_by_external_id(
            EXTERNAL_SYSTEM_CODE,
            str(customer_id),
            RESOURCE_CUSTOMER,
        )
        if partner:
            return partner
        values = {
            "name": fallback_name or f"RepairShopr Customer {customer_id}",
            "customer_rank": 1,
            "company_type": "company",
            "is_company": True,
        }
        partner = partner_model.create(values)
        partner.set_external_id(EXTERNAL_SYSTEM_CODE, str(customer_id), RESOURCE_CUSTOMER)
        return partner
