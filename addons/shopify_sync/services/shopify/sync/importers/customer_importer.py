import logging
import re

from odoo.api import Environment
from odoo.addons.phone_validation.tools.phone_validation import phone_format
from odoo.exceptions import UserError

from ...gql import (
    Client,
    AddressFields,
    CustomerFields,
)
from ..base import ShopifyBaseImporter, ShopifyPage
from ...helpers import (
    find_partner_by_shopify_address_id,
    find_record_by_external_id,
    parse_shopify_id_from_gid,
    normalize_email,
    normalize_phone,
    normalize_str,
    shopify_address_resource_for_role,
    upsert_external_id,
    write_if_changed,
)
from typing import Literal

_logger = logging.getLogger(__name__)


AddressRole = Literal["shipping", "billing"]
AddressType = Literal["delivery", "invoice"]


class CustomerImporter(ShopifyBaseImporter[CustomerFields]):
    def __init__(self, env: Environment, sync_record: "odoo.model.shopify_sync") -> None:
        super().__init__(env, sync_record)

    def _fetch_page(self, client: Client, query: str | None, cursor: str | None) -> ShopifyPage[CustomerFields]:
        return client.get_customers(query=query, cursor=cursor, limit=self.page_size)

    def _import_one(self, shopify_customer: CustomerFields) -> bool:
        return self.import_customer(shopify_customer)

    def _get_or_create_category(self, name: str) -> "odoo.model.res_partner_category":
        category = self.env["res.partner.category"].search([("name", "=", name)], limit=1)
        if not category:
            category = self.env["res.partner.category"].create({"name": name})
        return category

    def _get_tax_exempt_fiscal_position(self) -> "odoo.model.account_fiscal_position":
        fiscal_position = self.env["account.fiscal.position"].search([("name", "ilike", "tax exempt")], limit=1)
        if not fiscal_position:
            fiscal_position = self.env["account.fiscal.position"].create({"name": "Tax Exempt", "auto_apply": False})
        return fiscal_position

    def import_customers_since_last_import(self) -> int:
        return self.run_since_last_import("customer")

    def _format_phone_number(self, phone: str) -> str:
        if not phone or not phone.strip():
            return ""
        stripped = phone.strip()
        country = self.env.company.country_id or self.env["res.country"].search([("code", "=", "US")], limit=1)
        if not country:
            return stripped
        phone_code = int(country.phone_code or 0)
        formatted = phone_format(phone, country.code, phone_code, force_format="E164", raise_exception=False)
        if formatted and formatted.startswith("+"):
            return formatted

        normalized = normalize_phone(stripped)
        if not normalized:
            return stripped

        if phone_code:
            code_value = str(phone_code)
            if len(normalized) == 10:
                return f"+{code_value}{normalized}"
            if normalized.startswith(code_value):
                return f"+{normalized}"
            if len(normalized) == len(code_value) + 10:
                return f"+{normalized}"

        if normalized.startswith("1") and len(normalized) == 11:
            return f"+{normalized}"

        return stripped

    @staticmethod
    def _geolocalize_partner(partner: "odoo.model.res_partner") -> None:
        if not partner or not partner.exists():
            return

        if not any((partner.street, partner.city, partner.zip, partner.country_id)):
            return

        try:
            geo_localize = getattr(partner, "geo_localize", None)
            if not callable(geo_localize):
                return
            geo_localize()
        except UserError as error:
            _logger.warning(f"Failed to geolocalize partner {partner.name} (ID: {partner.id}): {str(error)}", exc_info=True)

    def _sync_phone_blacklist(self, partner: "odoo.model.res_partner", should_blacklist: bool) -> bool:
        if "phone_sanitized" not in partner._fields:
            return False

        if hasattr(partner, "_phone_get_number_fields"):
            phone_field_names = partner._phone_get_number_fields()
        else:
            phone_field_names = ["phone"]

        phone_numbers = [
            partner[field_name]
            for field_name in phone_field_names
            if field_name in partner._fields and partner[field_name]
        ]
        if not phone_numbers:
            return False

        if "phone.blacklist" not in self.env:
            return False

        phone_sanitized = partner.phone_sanitized or ""
        if not phone_sanitized and hasattr(partner, "_phone_format"):
            phone_sanitized = partner._phone_format(number=phone_numbers[0]) or ""
        if not phone_sanitized:
            return False

        phone_blacklist = self.env["phone.blacklist"].sudo()
        existing_blacklist = phone_blacklist.search(
            [("number", "=", phone_sanitized), ("active", "=", True)],
            limit=1,
        )

        if should_blacklist:
            if existing_blacklist:
                return False
            phone_blacklist._add([phone_sanitized])
            return True

        if not existing_blacklist:
            return False
        phone_blacklist._remove([phone_sanitized])
        return True

    @staticmethod
    def _sanitize_external_id_value(value: str | None) -> str:
        return (value or "").strip()

    def _set_external_id_if_needed(
        self,
        partner: "odoo.model.res_partner",
        *,
        system_code: str,
        resource: str,
        external_id_value: str | None,
    ) -> bool:
        sanitized = self._sanitize_external_id_value(external_id_value)
        existing_external_id = partner.get_external_system_id(system_code, resource) or ""
        if existing_external_id == sanitized:
            return False
        upsert_external_id(
            partner,
            system_code=system_code,
            resource=resource,
            external_id_value=sanitized or None,
        )
        return True

    def _set_external_id_moving_if_needed(
        self,
        partner: "odoo.model.res_partner",
        *,
        system_code: str,
        resource: str,
        external_id_value: str | None,
    ) -> bool:
        sanitized = self._sanitize_external_id_value(external_id_value)
        existing_external_id = partner.get_external_system_id(system_code, resource) or ""
        if existing_external_id == sanitized:
            return False

        system = self.env["external.system"].search([("code", "=", system_code)], limit=1)
        if not system:
            upsert_external_id(
                partner,
                system_code=system_code,
                resource=resource,
                external_id_value=sanitized or None,
            )
            return True

        external_id_model = self.env["external.id"].sudo().with_context(active_test=False)
        record_mapping = external_id_model.search(
            [
                ("res_model", "=", partner._name),
                ("res_id", "=", partner.id),
                ("system_id", "=", system.id),
                ("resource", "=", resource),
            ],
            limit=1,
        )

        if sanitized:
            existing_mapping = external_id_model.search(
                [
                    ("system_id", "=", system.id),
                    ("resource", "=", resource),
                    ("external_id", "=", sanitized),
                ],
                limit=1,
            )
            if existing_mapping and existing_mapping.id != record_mapping.id:
                if record_mapping:
                    record_mapping.unlink()
                existing_mapping.write({"res_model": partner._name, "res_id": partner.id, "active": True})
                return True

            if record_mapping:
                record_mapping.write({"external_id": sanitized, "active": True})
                return True

            external_id_model.create(
                {
                    "res_model": partner._name,
                    "res_id": partner.id,
                    "system_id": system.id,
                    "resource": resource,
                    "external_id": sanitized,
                    "active": True,
                }
            )
            return True

        if record_mapping and record_mapping.active:
            record_mapping.write({"active": False})
            return True
        return False

    @staticmethod
    def _partner_identity_mismatch(
        partner: "odoo.model.res_partner",
        *,
        name: str,
        email: str,
        phone: str,
    ) -> bool:
        if name and partner.name and normalize_str(name) != normalize_str(partner.name):
            return True
        if email and partner.email and normalize_email(email) != normalize_email(partner.email):
            return True
        if phone and partner.phone and normalize_phone(phone) != normalize_phone(partner.phone):
            return True
        return False

    def _ensure_ebay_identity_contact(
        self,
        partner: "odoo.model.res_partner",
        *,
        name: str,
        email: str,
        phone: str,
    ) -> None:
        if not partner or not partner.exists():
            return
        if email and partner.child_ids.filtered(lambda record: normalize_email(record.email) == normalize_email(email)):
            return
        if phone and partner.child_ids.filtered(lambda record: normalize_phone(record.phone) == normalize_phone(phone)):
            return
        if name and partner.child_ids.filtered(lambda record: normalize_str(record.name) == normalize_str(name)):
            return
        contact_values: "odoo.values.res_partner" = {
            "parent_id": partner.id,
            "type": "contact",
            "name": name or partner.name,
        }
        if email:
            contact_values["email"] = email
        if phone:
            contact_values["phone"] = phone
        self.env["res.partner"].create(contact_values)

    def import_customer(self, shopify_customer: CustomerFields) -> bool:
        shopify_customer_id = parse_shopify_id_from_gid(shopify_customer.id)
        tags = [t.strip().lower() for t in shopify_customer.tags]
        is_ebay = "ebay" in tags

        last_name_raw = (shopify_customer.last_name or "").strip()
        ebay_username = ""
        if is_ebay:
            ebay_match = re.search(r"\(([^)]+)\)$", last_name_raw)
            if ebay_match:
                ebay_username = ebay_match.group(1).strip()
                last_name_raw = re.sub(r"\s*\([^)]+\)\s*$", "", last_name_raw)

        if shopify_customer.default_email_address and shopify_customer.default_email_address.email_address:
            shopify_email = normalize_email(shopify_customer.default_email_address.email_address)
        else:
            shopify_email = ""

        if shopify_customer.default_phone_number and shopify_customer.default_phone_number.phone_number:
            shopify_phone = shopify_customer.default_phone_number.phone_number
        elif shopify_customer.default_address and shopify_customer.default_address.phone:
            shopify_phone = shopify_customer.default_address.phone
        else:
            shopify_phone = None
        shopify_phone = shopify_phone.strip() if shopify_phone else ""

        partner_model = self.env["res.partner"]
        partner = find_record_by_external_id(
            self.env,
            model_name="res.partner",
            system_code="shopify",
            resource="customer",
            external_id_value=shopify_customer_id,
        )
        partner_found_by_ebay = False
        if not partner and ebay_username:
            partner = find_record_by_external_id(
                self.env,
                model_name="res.partner",
                system_code="ebay",
                resource="profile",
                external_id_value=ebay_username,
            )
            partner_found_by_ebay = bool(partner)
        if not partner and shopify_email:
            partner = partner_model.search([("email", "ilike", shopify_email)], limit=1)
        if not partner and shopify_phone:
            formatted_phone = self._format_phone_number(shopify_phone)
            if formatted_phone:
                if "phone_mobile_search" in partner_model._fields:
                    partner = partner_model.search([("phone_mobile_search", "=", formatted_phone)], limit=1)
                elif "mobile" in partner_model._fields:
                    mobile_field = "mobile"
                    partner = partner_model.search(
                        ["|", ("phone", "=", formatted_phone), (mobile_field, "=", formatted_phone)],
                        limit=1,
                    )
                else:
                    partner = partner_model.search([("phone", "=", formatted_phone)], limit=1)

        email = shopify_email or (partner.email if partner else "")
        phone = self._format_phone_number(shopify_phone) or (partner.phone if partner else "")
        last_name = last_name_raw

        first_name = (shopify_customer.first_name or "").strip()
        name_parts = [first_name, last_name]
        name = (
            re.sub(r"\s{2,}", " ", " ".join(p for p in name_parts if p)).strip()
            or email
            or phone
            or f"Customer {shopify_customer_id}"
        )
        # Truncate name to 512 characters (Odoo char field limit)
        if name and len(name) > 512:
            name = name[:512]

        tax_exempt_flag = bool(shopify_customer.tax_exempt) if shopify_customer.tax_exempt is not None else False
        fiscal_position = self._get_tax_exempt_fiscal_position() if tax_exempt_flag else False

        opt_in_states = {"SUBSCRIBED", "PENDING"}
        email_state = shopify_customer.default_email_address.marketing_state if shopify_customer.default_email_address else None
        sms_state = shopify_customer.default_phone_number.marketing_state if shopify_customer.default_phone_number else None
        email_blacklisted_flag = email_state not in opt_in_states if email_state else False
        sms_blacklisted_flag = sms_state not in opt_in_states if sms_state else False

        partner_vals: "odoo.values.res_partner" = {
            "name": name,
            "property_account_position_id": fiscal_position.id if fiscal_position else False,
        }
        if email:
            partner_vals["email"] = email
        if phone:
            partner_vals["phone"] = phone
        if not partner:
            partner = self.env["res.partner"].create(partner_vals)
            changed = True
        else:
            if partner_found_by_ebay and self._partner_identity_mismatch(
                partner,
                name=name,
                email=email,
                phone=phone,
            ):
                self._ensure_ebay_identity_contact(partner, name=name, email=email, phone=phone)
                partner_vals = {
                    "property_account_position_id": fiscal_position.id if fiscal_position else False,
                }
                if name and not partner.name:
                    partner_vals["name"] = name
                if email and not partner.email:
                    partner_vals["email"] = email
                if phone and not partner.phone:
                    partner_vals["phone"] = phone
            changed = write_if_changed(partner, partner_vals)

        changed |= self._set_external_id_if_needed(
            partner,
            system_code="shopify",
            resource="customer",
            external_id_value=shopify_customer_id,
        )
        changed |= self._set_external_id_if_needed(
            partner,
            system_code="ebay",
            resource="profile",
            external_id_value=ebay_username or None,
        )

        self._geolocalize_partner(partner)

        # Always ensure Shopify category is assigned
        shopify_category = self._get_or_create_category("Shopify")
        if shopify_category.id not in partner.category_id.ids:
            partner.write({"category_id": [(4, shopify_category.id)]})
            changed = True

        addresses_changed = False
        addresses_to_process: list[tuple[AddressFields, AddressRole]] = []
        if shopify_customer.default_address:
            addresses_to_process.append((shopify_customer.default_address, "billing"))
        if shopify_customer.addresses_v_2 and shopify_customer.addresses_v_2.nodes:
            for addr in shopify_customer.addresses_v_2.nodes:
                addresses_to_process.append((addr, "shipping"))
        processed_ids: set[str] = set()
        for address, role in addresses_to_process:
            address_id = address.id
            if address_id in processed_ids:
                continue
            processed_ids.add(address_id)
            addresses_changed |= self.process_address(address, partner, role=role)
        if addresses_changed:
            changed = True

        if (
            not tax_exempt_flag
            and partner.property_account_position_id
            and "tax exempt" in partner.property_account_position_id.name.casefold()
        ):
            partner.property_account_position_id = False

        # Update phone blacklist status based on marketing opt-out
        if self._sync_phone_blacklist(partner, sms_blacklisted_flag):
            changed = True

        # Manage email blacklist via mail.blacklist model
        if partner.email_normalized:
            blacklist_sudo = self.env["mail.blacklist"].sudo()
            existing_blacklist = blacklist_sudo.search([("email", "=", partner.email_normalized)], limit=1)

            if email_blacklisted_flag and not existing_blacklist:
                blacklist_sudo.create({"email": partner.email_normalized})
                changed = True
            elif not email_blacklisted_flag and existing_blacklist:
                existing_blacklist.unlink()
                changed = True

        return changed

    def process_address(self, address: AddressFields, partner: "odoo.model.res_partner", role: AddressRole) -> bool:
        shopify_address_id = parse_shopify_id_from_gid(address.id)

        country = (
            self.env["res.country"].search([("code", "=", address.country_code_v_2.value)], limit=1)
            if address.country_code_v_2
            else False
        )

        state = False
        if country and (address.province_code or address.province):
            domain: list[tuple] = [("country_id", "=", country.id)]
            if address.province_code and address.province:
                domain = [
                    "|",
                    ("code", "=", address.province_code.strip()),
                    ("name", "ilike", address.province.strip()),
                ] + domain
            elif address.province_code:
                domain.append(("code", "=", address.province_code.strip()))
            else:
                domain.append(("name", "ilike", address.province.strip()))
            state = self.env["res.country.state"].search(domain, limit=1)

        formatted_phone = self._format_phone_number(address.phone) if address.phone else ""

        def get_phone_numbers(target_partner: "odoo.model.res_partner") -> set[str]:
            if hasattr(target_partner, "_phone_get_number_fields"):
                phone_field_names = target_partner._phone_get_number_fields()
            else:
                phone_field_names = ["phone"]
            return {
                normalize_phone(target_partner[field_name])
                for field_name in phone_field_names
                if field_name in target_partner._fields and target_partner[field_name]
            }

        existing_numbers = get_phone_numbers(partner)
        phone_mismatch = bool(formatted_phone and existing_numbers and normalize_phone(formatted_phone) not in existing_numbers)
        existing_address = find_partner_by_shopify_address_id(self.env, shopify_address_id, role=role)

        partner_has_address = any(
            (
                partner.street,
                partner.street2,
                partner.city,
                partner.zip,
                partner.state_id,
                partner.country_id,
            )
        )
        is_different_address = partner_has_address and any(
            (
                normalize_str(address.address_1) != normalize_str(partner.street),
                normalize_str(address.address_2) != normalize_str(partner.street2),
                normalize_str(address.city) != normalize_str(partner.city),
                normalize_str(address.zip) != normalize_str(partner.zip),
                country and country.id != partner.country_id.id,
                state and state.id != partner.state_id.id,
                phone_mismatch,
                normalize_str(address.company) != normalize_str(partner.company_name),
            )
        )

        if not existing_address and is_different_address:

            def phone_matches(child_address: "odoo.model.res_partner") -> bool:
                if not formatted_phone:
                    return True  # No phone to match, consider it a match based on other fields
                existing_phones = get_phone_numbers(child_address)
                if not existing_phones:
                    return True  # Existing address has no phone, still consider it a match
                return normalize_phone(formatted_phone) in existing_phones

            possible_duplicates = partner.child_ids.filtered(
                lambda a: normalize_str(a.street) == normalize_str(address.address_1)
                and normalize_str(a.street2) == normalize_str(address.address_2)
                and normalize_str(a.city) == normalize_str(address.city)
                and normalize_str(a.zip) == normalize_str(address.zip)
                and (not country or a.country_id.id == country.id)
                and (not state or a.state_id.id == state.id)
                and phone_matches(a)
                and normalize_str(a.company_name) == normalize_str(address.company)
            )
            for possible_duplicate in possible_duplicates:
                address_resource = shopify_address_resource_for_role(role)
                existing_external_id = possible_duplicate.get_external_system_id("shopify", address_resource)
                if existing_external_id and existing_external_id != shopify_address_id:
                    continue
                if not existing_external_id:
                    external_id_changed = self._set_external_id_moving_if_needed(
                        possible_duplicate,
                        system_code="shopify",
                        resource=address_resource,
                        external_id_value=shopify_address_id,
                    )
                    return external_id_changed  # Found duplicate, only updated Shopify external ID
                existing_address = possible_duplicate
                break

        # New address_type logic and early return for main address update
        # For billing addresses, always update the main partner record (unless existing_address is a different record)
        if role == "billing" and not existing_address:
            main_address_vals: "odoo.values.res_partner" = {
                "street": (address.address_1 or "").strip(),
                "street2": (address.address_2 or "").strip(),
                "city": (address.city or "").strip(),
                "zip": (address.zip or "").strip(),
                "state_id": state.id if state else False,
                "country_id": country.id if country else False,
            }
            if formatted_phone:
                main_address_vals["phone"] = formatted_phone
            changed = write_if_changed(partner, main_address_vals)
            changed |= self._set_external_id_moving_if_needed(
                partner,
                system_code="shopify",
                resource=shopify_address_resource_for_role(role),
                external_id_value=shopify_address_id,
            )
            self._geolocalize_partner(partner)
            return changed

        # If the address is the same as current main address, just update the external ID
        if not is_different_address:
            return self._set_external_id_moving_if_needed(
                partner,
                system_code="shopify",
                resource=shopify_address_resource_for_role(role),
                external_id_value=shopify_address_id,
            )

        address_type: AddressType = "invoice" if role == "billing" else "delivery"
        address_resource = shopify_address_resource_for_role(role)

        address_vals: "odoo.values.res_partner" = {
            "parent_id": partner.id,
            "type": address_type,
            "name": None if (address.name or "").strip() == (partner.name or "").strip() else (address.name or "").strip(),
            "street": (address.address_1 or "").strip(),
            "street2": (address.address_2 or "").strip(),
            "city": (address.city or "").strip(),
            "zip": (address.zip or "").strip(),
            "state_id": state.id if state else False,
            "country_id": country.id if country else False,
        }
        if address.company:
            address_vals["company_name"] = address.company.strip()

        if formatted_phone:
            address_vals["phone"] = formatted_phone

        if existing_address:
            if existing_address.type != address_type:
                copy_defaults = {
                    "type": address_type,
                    "parent_id": partner.id,
                    "name": address_vals.get("name"),
                }
                company_name_to_set = address_vals.get("company_name")
                if company_name_to_set:
                    copy_defaults["company_name"] = company_name_to_set
                copied_address = existing_address.copy(default=copy_defaults)
                write_if_changed(copied_address, address_vals)
                # Odoo automatically sets company_name to False for child contacts
                # We need to explicitly set it again if it was provided
                if company_name_to_set and not copied_address.company_name:
                    copied_address.write({"company_name": company_name_to_set})
                self._set_external_id_moving_if_needed(
                    copied_address,
                    system_code="shopify",
                    resource=address_resource,
                    external_id_value=shopify_address_id,
                )
                self._geolocalize_partner(copied_address)
                return True
            changed = write_if_changed(existing_address, address_vals)
            changed |= self._set_external_id_moving_if_needed(
                existing_address,
                system_code="shopify",
                resource=address_resource,
                external_id_value=shopify_address_id,
            )
            return changed
        elif is_different_address:
            address_vals["category_id"] = [(6, 0, partner.category_id.ids)]
            company_name_to_set = address_vals.get("company_name")
            created_address = self.env["res.partner"].create(address_vals)
            # Odoo automatically sets company_name to False for child contacts
            # We need to explicitly set it again if it was provided
            if company_name_to_set and not created_address.company_name:
                created_address.write({"company_name": company_name_to_set})
            self._set_external_id_moving_if_needed(
                created_address,
                system_code="shopify",
                resource=address_resource,
                external_id_value=shopify_address_id,
            )
            self._geolocalize_partner(created_address)
            return True
        return False
