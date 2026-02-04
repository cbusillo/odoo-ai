import uuid

from ..common_imports import tagged, logging, time, patch, INTEGRATION_TAGS

from ...services.shopify.gql import (
    CustomerFields,
    AddressFields,
)
from ...services.shopify.helpers import parse_shopify_id_from_gid
from ...services.shopify.sync.importers.customer_importer import CustomerImporter

from ..fixtures.shopify_responses import (
    create_shopify_customer_response,
    create_shopify_address_response,
)
from ..fixtures.base import IntegrationTestCase
from ..fixtures.factories import ShopifySyncFactory, PartnerFactory

_logger = logging.getLogger(__name__)


@tagged(*INTEGRATION_TAGS)
class TestCustomerImporter(IntegrationTestCase):
    def setUp(self) -> None:
        super().setUp()
        self._setup_shopify_mocks()  # Set up Shopify API mocks
        self.sync_record = ShopifySyncFactory.create(self.env, mode="import_changed_customers")
        self.importer = CustomerImporter(self.env, self.sync_record)

        self.tax_exempt_fiscal_position = self.env["account.fiscal.position"].create({"name": "Tax Exempt", "auto_apply": False})

    def _find_partner_by_customer_id(self, customer_id: str) -> "odoo.model.res_partner":
        return self.env["res.partner"].search_by_external_id("shopify", customer_id, resource="customer")

    def test_import_customer_basic(self) -> None:
        unique_email = f"john.doe.{uuid.uuid4().hex[:8]}@example.com"
        customer_data = create_shopify_customer_response(
            gid="gid://shopify/Customer/111",
            email=unique_email,
            phone="+1-212-555-0123",
        )

        shopify_customer = CustomerFields(**customer_data)
        result = self.importer._import_one(shopify_customer)

        self.assertTrue(result)

        partner = self._find_partner_by_customer_id("111")
        self.assertTrue(partner)
        self.assertEqual(partner.name, "John Doe")
        self.assertEqual(partner.email, unique_email)
        self.assertTrue(partner.phone)
        self.assertIn(self.shopify_category.id, partner.category_id.ids)

    def test_import_customer_with_ebay_tag(self) -> None:
        customer_data = create_shopify_customer_response(
            gid="gid://shopify/Customer/222",
            first_name="Jane",
            last_name="Smith (ebay_user123)",
            email="jane.smith@example.com",
            tags=["eBay", "wholesale"],
        )

        shopify_customer = CustomerFields(**customer_data)
        result = self.importer._import_one(shopify_customer)

        self.assertTrue(result)

        partner = self._find_partner_by_customer_id("222")
        self.assertTrue(partner)
        self.assertEqual(partner.name, "Jane Smith")
        self.assertEqual(partner.get_external_system_id("ebay", "profile"), "ebay_user123")

    def test_import_customer_tax_exempt(self) -> None:
        customer_data = create_shopify_customer_response(
            gid="gid://shopify/Customer/333", first_name="Tax", last_name="Exempt", tax_exempt=True
        )

        shopify_customer = CustomerFields(**customer_data)
        result = self.importer._import_one(shopify_customer)

        self.assertTrue(result)

        partner = self._find_partner_by_customer_id("333")
        self.assertTrue(partner)
        self.assertEqual(partner.property_account_position_id.id, self.tax_exempt_fiscal_position.id)

    def test_import_customer_update_existing_by_email(self) -> None:
        existing_partner = PartnerFactory.create(
            self.env,
            name="Old Name",
            email="existing@example.com",
        )

        customer_data = create_shopify_customer_response(
            gid="gid://shopify/Customer/444", first_name="Updated", last_name="Name", email="EXISTING@EXAMPLE.COM"
        )

        shopify_customer = CustomerFields(**customer_data)
        result = self.importer._import_one(shopify_customer)

        self.assertTrue(result)

        existing_partner.invalidate_recordset()
        self.assertEqual(existing_partner.get_external_system_id("shopify", "customer"), "444")
        self.assertEqual(existing_partner.name, "Updated Name")

    def test_import_customer_update_existing_by_phone(self) -> None:
        existing_partner = PartnerFactory.create(
            self.env,
            name="Old Name",
            phone="+12125550123",
        )

        customer_data = create_shopify_customer_response(
            gid="gid://shopify/Customer/555", first_name="Phone", last_name="Match", phone="212-555-0123"
        )

        shopify_customer = CustomerFields(**customer_data)
        result = self.importer._import_one(shopify_customer)

        self.assertTrue(result)

        existing_partner.invalidate_recordset()
        self.assertEqual(existing_partner.get_external_system_id("shopify", "customer"), "555")
        self.assertEqual(existing_partner.name, "Phone Match")

    def test_import_customer_marketing_opt_out(self) -> None:
        customer_data = create_shopify_customer_response(
            gid="gid://shopify/Customer/666",
            first_name="Marketing",
            last_name="OptOut",
            email="optout@example.com",
            phone="+1-415-867-5310",
        )

        customer_data["defaultEmailAddress"]["marketingState"] = "UNSUBSCRIBED"
        customer_data["defaultPhoneNumber"]["marketingState"] = "UNSUBSCRIBED"

        shopify_customer = CustomerFields(**customer_data)
        result = self.importer._import_one(shopify_customer)

        self.assertTrue(result)

        partner = self._find_partner_by_customer_id("666")
        self.assertTrue(partner)
        self.assertTrue(partner.is_blacklisted)
        if "phone_sanitized_blacklisted" in partner._fields:
            self.assertTrue(partner.phone_sanitized_blacklisted)
        elif "phone_blacklisted" in partner._fields:
            self.assertTrue(partner.phone_blacklisted)

    def test_import_customer_with_addresses(self) -> None:
        billing_address = create_shopify_address_response(
            gid="gid://shopify/CustomerAddress/1001",
            name="John Billing",
            address1="123 Billing St",
        )

        shipping_address = create_shopify_address_response(
            gid="gid://shopify/CustomerAddress/1002",
            name="John Shipping",
            address1="456 Shipping Ave",
            city="Los Angeles",
            province_code="CA",
            zip_code="90001",
        )

        customer_data = create_shopify_customer_response(
            gid="gid://shopify/Customer/777",
            last_name="Multi-Address",
            default_address=billing_address,
            addresses=[billing_address, shipping_address],
        )

        shopify_customer = CustomerFields(**customer_data)
        result = self.importer._import_one(shopify_customer)

        self.assertTrue(result)

        partner = self._find_partner_by_customer_id("777")
        self.assertTrue(partner)

        self.assertEqual(partner.street, "123 Billing St")
        self.assertEqual(partner.city, "New York")

        child_addresses = partner.child_ids
        self.assertEqual(len(child_addresses), 1)

        shipping_child = child_addresses.filtered(lambda a: a.type == "delivery")
        self.assertTrue(shipping_child)
        self.assertEqual(shipping_child.street, "456 Shipping Ave")
        self.assertEqual(shipping_child.city, "Los Angeles")

    def test_import_customer_no_email_no_phone(self) -> None:
        customer_data = create_shopify_customer_response(
            gid="gid://shopify/Customer/888",
            first_name="No",
            last_name="Contact",
            email=None,
            phone=None,
        )

        shopify_customer = CustomerFields(**customer_data)
        result = self.importer._import_one(shopify_customer)

        self.assertTrue(result)

        partner = self._find_partner_by_customer_id("888")
        self.assertTrue(partner)
        self.assertEqual(partner.name, "No Contact")
        self.assertFalse(partner.email)
        self.assertFalse(partner.phone)

    def test_format_phone_number(self) -> None:
        test_cases = [
            ("212-555-0123", "+12125550123"),
            ("(212) 555-0123", "+12125550123"),
            ("+1-212-555-0123", "+12125550123"),
            ("12125550123", "+12125550123"),
            ("+1 (212) 555-0123 ext. 890", "+12125550123"),
            ("01144 20 7946 0958 x123", "+442079460958"),
            ("1212555012345", "1212555012345"),
            ("02079460958", "02079460958"),
            ("", ""),
            ("   ", ""),
            (None, ""),
        ]

        for input_phone, expected in test_cases:
            result = self.importer._format_phone_number(input_phone or "")
            self.assertEqual(result, expected, f"Failed for input: {input_phone}")

    def test_get_or_create_category(self) -> None:
        new_category = self.importer._get_or_create_category("Test Category")
        self.assertTrue(new_category)
        self.assertEqual(new_category.name, "Test Category")

        existing_category = self.importer._get_or_create_category("Test Category")
        self.assertEqual(existing_category.id, new_category.id)

    def test_get_tax_exempt_fiscal_position(self) -> None:
        fiscal_position = self.importer._get_tax_exempt_fiscal_position()
        self.assertEqual(fiscal_position.id, self.tax_exempt_fiscal_position.id)

        self.tax_exempt_fiscal_position.unlink()
        new_fiscal_position = self.importer._get_tax_exempt_fiscal_position()
        self.assertTrue(new_fiscal_position)
        self.assertEqual(new_fiscal_position.name, "Tax Exempt")
        self.assertFalse(new_fiscal_position.auto_apply)

    def test_import_customer_empty_name_uses_email(self) -> None:
        customer_data = create_shopify_customer_response(
            gid="gid://shopify/Customer/999",
            first_name="",
            last_name="",
            email="customer@example.com",
        )

        shopify_customer = CustomerFields(**customer_data)
        result = self.importer._import_one(shopify_customer)

        self.assertTrue(result)

        partner = self._find_partner_by_customer_id("999")
        self.assertTrue(partner)
        self.assertEqual(partner.name, "customer@example.com")

    def test_process_address_creates_child(self) -> None:
        partner = PartnerFactory.create(
            self.env,
            name="Main Partner",
            shopify_customer_id="1111",
            street="123 Main St",
            city="New York",
            state_id=self.ny_state.id,
            country_id=self.usa_country.id,
        )

        address_data = create_shopify_address_response(
            gid="gid://shopify/CustomerAddress/2001",
            name="Shipping Address",
            address1="789 Ship Lane",
            city="Brooklyn",
            company="Test Company",
        )

        address = AddressFields(**address_data)
        result = self.importer.process_address(address, partner, role="shipping")

        self.assertTrue(result)

        child_address = partner.child_ids.filtered(
            lambda child: child.get_external_system_id("shopify", "address_delivery") == "2001"
        )
        self.assertTrue(child_address)
        self.assertEqual(child_address.type, "delivery")
        self.assertEqual(child_address.street, "789 Ship Lane")
        self.assertEqual(child_address.city, "Brooklyn")
        self.assertEqual(child_address.company_name, "Test Company")

    def test_process_address_updates_main(self) -> None:
        partner = PartnerFactory.create(
            self.env,
            name="Main Partner",
            shopify_customer_id="2222",
            street="123 Test Street",
            city="Initial City",
            state_id=self.ny_state.id,
            country_id=self.usa_country.id,
        )

        address_data = create_shopify_address_response(
            gid="gid://shopify/CustomerAddress/3001",
            address1="456 New St",
            city="Chicago",
            province_code="IL",
        )

        address = AddressFields(**address_data)
        result = self.importer.process_address(address, partner, role="billing")

        self.assertTrue(result)

        partner.invalidate_recordset()
        self.assertEqual(partner.street, "456 New St")
        self.assertEqual(partner.city, "Chicago")
        self.assertEqual(partner.get_external_system_id("shopify", "address_invoice"), "3001")

    def test_process_address_duplicate_detection(self) -> None:
        partner = PartnerFactory.create(
            self.env,
            name="Main Partner",
            shopify_customer_id="3333",
            street="123 Main St",
            city="New York",
            state_id=self.ny_state.id,
            country_id=self.usa_country.id,
        )

        ma_state = self.env["res.country.state"].search([("code", "=", "MA"), ("country_id", "=", self.usa_country.id)], limit=1)
        if not ma_state:
            ma_state = self.env["res.country.state"].create(
                {"name": "Massachusetts", "code": "MA", "country_id": self.usa_country.id}
            )

        existing_child = PartnerFactory.create(
            self.env,
            parent_id=partner.id,
            type="delivery",
            street="999 Existing St",
            city="Boston",
            zip="02101",
            state_id=ma_state.id,
            country_id=self.usa_country.id,
        )

        address_data = create_shopify_address_response(
            gid="gid://shopify/CustomerAddress/4001",
            address1="999 Existing St",
            city="Boston",
            province_code="MA",
            zip_code="02101",
            phone=None,
        )

        address = AddressFields(**address_data)

        self.importer.process_address(address, partner, role="shipping")

        existing_child.invalidate_recordset()

        self.assertEqual(
            existing_child.get_external_system_id("shopify", "address_delivery"),
            "4001",
            "Existing address should be linked to Shopify ID",
        )

        all_children = partner.child_ids
        self.assertEqual(len(all_children), 1, "No new child address should be created")
        self.assertEqual(all_children[0].id, existing_child.id, "The same child should be updated")

    def test_import_customer_removes_tax_exempt_if_false(self) -> None:
        partner = PartnerFactory.create(
            self.env,
            name="Previously Tax Exempt",
            shopify_customer_id="4444",
            property_account_position_id=self.tax_exempt_fiscal_position.id,
        )

        customer_data = create_shopify_customer_response(
            gid="gid://shopify/Customer/4444",
            first_name="No Longer",
            last_name="Tax Exempt",
        )

        shopify_customer = CustomerFields(**customer_data)
        result = self.importer._import_one(shopify_customer)

        self.assertTrue(result)

        partner.invalidate_recordset()
        self.assertFalse(partner.property_account_position_id)

    def test_import_customer_removes_phone_blacklist_if_subscribed(self) -> None:
        partner = PartnerFactory.create(
            self.env,
            name="Previously Blacklisted",
            shopify_customer_id="5555",
            phone="+1-415-867-5311",
        )
        if "phone_blacklisted" in partner._fields:
            partner._phone_set_blacklisted()
            partner.invalidate_recordset()
            if "phone_sanitized_blacklisted" in partner._fields:
                self.assertTrue(partner.phone_sanitized_blacklisted)
            else:
                self.assertTrue(partner.phone_blacklisted)

        customer_data = create_shopify_customer_response(
            gid="gid://shopify/Customer/5555",
            first_name="Now",
            last_name="Subscribed",
            phone="+1-415-867-5311",
        )

        customer_data["defaultPhoneNumber"]["marketingState"] = "SUBSCRIBED"

        shopify_customer = CustomerFields(**customer_data)
        result = self.importer._import_one(shopify_customer)

        self.assertTrue(result)

        partner.invalidate_recordset()
        if "phone_sanitized_blacklisted" in partner._fields:
            self.assertFalse(partner.phone_sanitized_blacklisted)
        elif "phone_blacklisted" in partner._fields:
            self.assertFalse(partner.phone_blacklisted)

    def test_import_customer_removes_email_blacklist_if_subscribed(self) -> None:
        partner = PartnerFactory.create(
            self.env,
            name="Previously Email Blacklisted",
            shopify_customer_id="5556",
            email="previously.blacklisted@example.com",
        )

        self.env["mail.blacklist"].sudo().create({"email": partner.email_normalized})
        partner.invalidate_recordset()
        self.assertTrue(partner.is_blacklisted)

        customer_data = create_shopify_customer_response(
            gid="gid://shopify/Customer/5556",
            first_name="Now",
            last_name="Email Subscribed",
            email="previously.blacklisted@example.com",
        )

        customer_data["defaultEmailAddress"]["marketingState"] = "SUBSCRIBED"

        shopify_customer = CustomerFields(**customer_data)
        result = self.importer._import_one(shopify_customer)

        self.assertTrue(result)

        partner.invalidate_recordset()
        self.assertFalse(partner.is_blacklisted)

    def test_import_customer_direct(self) -> None:
        customer_data = create_shopify_customer_response(
            gid="gid://shopify/Customer/8888",
            first_name="Direct",
            last_name="Test",
            email=f"direct.test.{uuid.uuid4().hex[:8]}@example.com",
        )

        customer = CustomerFields(**customer_data)
        result = self.importer._import_one(customer)

        self.assertTrue(result)

        partner = self._find_partner_by_customer_id("8888")
        self.assertTrue(partner, "Customer 8888 should be created")
        self.assertEqual(partner.name, "Direct Test")

    def test_import_customers_batch(self) -> None:
        unique_id = uuid.uuid4().hex[:8]

        base_id = int(time.time() * 1000) % 1000000  # Unique base ID

        customers_data = []
        for i in range(1, 4):
            customer_data = create_shopify_customer_response(
                gid=f"gid://shopify/Customer/{base_id + i}",
                first_name="Batch",
                last_name=f"Customer{i}",
                email=f"batch.customer{i}.{unique_id}@example.com",
            )
            customers_data.append(customer_data)

        for i, customer_data in enumerate(customers_data):
            customer = CustomerFields(**customer_data)
            result = self.importer._import_one(customer)
            self.assertTrue(result, f"Import should succeed for customer {i + 1}")

            customer_id = parse_shopify_id_from_gid(customer_data["id"])
            partner = self._find_partner_by_customer_id(customer_id)

            self.assertTrue(partner, f"Customer {customer_id} should be found")
            self.assertEqual(partner.email, f"batch.customer{i + 1}.{unique_id}@example.com")
            self.assertEqual(partner.name, f"Batch Customer{i + 1}")

    def test_process_address_with_different_role_creates_copy(self) -> None:
        partner = PartnerFactory.create(
            self.env,
            name="Main Partner",
            shopify_customer_id="6666",
        )

        PartnerFactory.create(
            self.env,
            parent_id=partner.id,
            type="invoice",
            shopify_address_id="5001",
            street="123 Invoice St",
            city="Dallas",
        )

        address_data = create_shopify_address_response(
            gid="gid://shopify/CustomerAddress/5001",
            address1="123 Invoice St",
            city="Dallas",
        )

        address = AddressFields(**address_data)
        result = self.importer.process_address(address, partner, role="shipping")

        self.assertTrue(result)

        delivery_address = partner.child_ids.filtered(lambda a: a.type == "delivery")
        self.assertTrue(delivery_address)
        self.assertEqual(delivery_address.get_external_system_id("shopify", "address_delivery"), "5001")
        self.assertEqual(delivery_address.street, "123 Invoice St")

    def test_import_customer_with_phone_from_address(self) -> None:
        address_with_phone = create_shopify_address_response(
            phone="+1-212-555-0177",
        )

        customer_data = create_shopify_customer_response(
            gid="gid://shopify/Customer/7777",
            first_name="Phone",
            last_name="FromAddress",
            phone=None,
            default_address=address_with_phone,
        )

        customer_data["defaultPhoneNumber"] = None

        shopify_customer = CustomerFields(**customer_data)
        result = self.importer._import_one(shopify_customer)

        self.assertTrue(result)

        partner = self._find_partner_by_customer_id("7777")
        self.assertTrue(partner)
        self.assertTrue(partner.phone)
        self.assertIn("2125550177", partner.phone.replace("-", "").replace("+1", ""))

    def test_import_customer_normalizes_email(self) -> None:
        customer_data = create_shopify_customer_response(
            gid="gid://shopify/Customer/8888",
            first_name="Email",
            last_name="Test",
            email="  MIXED.Case@EXAMPLE.COM  ",
        )

        shopify_customer = CustomerFields(**customer_data)
        result = self.importer._import_one(shopify_customer)

        self.assertTrue(result)

        partner = self._find_partner_by_customer_id("8888")
        self.assertTrue(partner)
        self.assertEqual(partner.email, "mixed.case@example.com")

    def test_import_customer_with_none_values(self) -> None:
        customer_data = create_shopify_customer_response(
            gid="gid://shopify/Customer/9999",
            first_name=None,
            last_name=None,
            email=None,
            phone=None,
            addresses=[],
        )

        shopify_customer = CustomerFields(**customer_data)
        result = self.importer._import_one(shopify_customer)

        self.assertTrue(result)

        partner = self._find_partner_by_customer_id("9999")
        self.assertTrue(partner)

    def test_import_customer_with_extremely_long_names(self) -> None:
        long_name = "A" * 500  # Very long name
        customer_data = create_shopify_customer_response(
            first_name=long_name,
            last_name=long_name,
            email="very.long.email.address.that.exceeds.normal.length@example-domain-with-very-long-name.com",
            phone="+1234567890123456789012345",  # Very long phone
            tags=[f"tag{i}" for i in range(100)],  # Many tags
        )

        shopify_customer = CustomerFields(**customer_data)
        result = self.importer._import_one(shopify_customer)

        self.assertTrue(result)

        partner = self._find_partner_by_customer_id("123456789")
        self.assertTrue(partner)
        self.assertLessEqual(len(partner.name), 512)  # Typical Odoo char field limit

    def test_import_customer_with_special_characters_in_all_fields(self) -> None:
        customer_data = create_shopify_customer_response(
            first_name="Robert'); DROP TABLE res_partner;--",
            last_name="<script>alert('XSS')</script>",
            email="test@example.com",
            phone="+1 (212) 555-0123 ext. 890",
            note="Customer note with \n newlines \t tabs and \r carriage returns",
        )

        shopify_customer = CustomerFields(**customer_data)
        result = self.importer._import_one(shopify_customer)

        self.assertTrue(result)

        partner = self._find_partner_by_customer_id("123456789")
        self.assertTrue(partner)
        self.assertIn("Robert", partner.name)
        self.assertIn("script", partner.name)  # Should be escaped, not executed

    def test_import_customer_with_invalid_email_formats(self) -> None:
        invalid_emails = [
            "not-an-email",
            "@example.com",
            "user@",
            "user @example.com",
            "user@example",
            "",
            "user@.com",
        ]

        for email in invalid_emails:
            customer_identifier = abs(hash(email))
            customer_data = create_shopify_customer_response(
                gid=f"gid://shopify/Customer/{customer_identifier}",
                email=email,
            )

            shopify_customer = CustomerFields(**customer_data)
            result = self.importer._import_one(shopify_customer)
            self.assertTrue(result)

    def test_import_customer_with_duplicate_addresses(self) -> None:
        address1 = create_shopify_address_response(
            province="NY",
            zip="10001",
        )
        address2 = create_shopify_address_response(
            gid="gid://shopify/CustomerAddress/456",
            province="NY",
            zip="10001",
        )
        address3 = create_shopify_address_response(
            gid="gid://shopify/CustomerAddress/789",
            province="NY",
            zip="10001",
        )

        billing_address = create_shopify_address_response(
            gid="gid://shopify/CustomerAddress/999",
            address1="456 Oak St",
            province="CA",
            zip="90210",
        )

        customer_data = create_shopify_customer_response(
            default_address=billing_address,
            addresses=[address1, address2, address3],  # 3 identical shipping addresses
        )

        shopify_customer = CustomerFields(**customer_data)
        result = self.importer._import_one(shopify_customer)

        self.assertTrue(result)

        partner = self._find_partner_by_customer_id("123456789")
        self.assertTrue(partner)
        child_addresses = partner.child_ids.filtered(lambda c: c.type == "delivery")
        self.assertEqual(len(child_addresses), 3)

        addresses = list(child_addresses)
        self.assertEqual(addresses[0].street, addresses[1].street)
        self.assertEqual(addresses[0].street, addresses[2].street)
        self.assertEqual(addresses[0].city, addresses[1].city)
        self.assertEqual(addresses[0].city, addresses[2].city)

    def test_import_customer_with_circular_references(self) -> None:
        PartnerFactory.create(
            self.env,
            name="Existing Partner",
            email="circular@example.com",
            shopify_customer_id="999",
        )

        customer_data = create_shopify_customer_response(
            gid="gid://shopify/Customer/999",  # Same ID as existing
            email="circular@example.com",
            default_address=create_shopify_address_response(
                gid="gid://shopify/CustomerAddress/999",
            ),
        )

        shopify_customer = CustomerFields(**customer_data)
        result = self.importer._import_one(shopify_customer)

        self.assertTrue(result)  # Update is successful
        partners = self._find_partner_by_customer_id("999")
        self.assertEqual(len(partners), 1)  # No duplicate created

    def test_import_customer_api_rate_limit(self) -> None:
        from ...services.shopify.helpers import ShopifyApiError

        with patch.object(self.importer, "_fetch_page") as mock_fetch:
            mock_fetch.side_effect = ShopifyApiError("Rate limit exceeded")

            with self.assertRaises(ShopifyApiError) as cm:
                self.importer.import_customers_since_last_import()

            self.assertIn("Rate limit", str(cm.exception))

    def test_import_customer_with_international_phone_formats(self) -> None:
        phone_formats = [
            "+44 20 7946 0958",  # UK
            "+81 3-1234-5678",  # Japan
            "+49 (0)30 12345678",  # Germany
            "+33 1 23 45 67 89",  # France
            "+86 138 0000 0000",  # China
            "+91-9876543210",  # India
            "001-212-555-0123",  # International prefix
        ]

        for i, phone in enumerate(phone_formats):
            customer_data = create_shopify_customer_response(
                gid=f"gid://shopify/Customer/{i + 1000}",
                phone=phone,
            )

            shopify_customer = CustomerFields(**customer_data)
            result = self.importer._import_one(shopify_customer)

            self.assertTrue(result)
            partner = self._find_partner_by_customer_id(str(i + 1000))
            self.assertTrue(partner)
            if hasattr(partner, "_phone_get_number_fields"):
                phone_field_names = partner._phone_get_number_fields()
            else:
                phone_field_names = ["phone"]
            phone_values = [
                partner[field_name]
                for field_name in phone_field_names
                if field_name in partner._fields and partner[field_name]
            ]
            self.assertTrue(phone_values)

    def test_import_customer_with_default_address_in_list(self) -> None:
        default_address = create_shopify_address_response(
            gid="gid://shopify/CustomerAddress/111",
        )

        shipping_address = create_shopify_address_response(
            gid="gid://shopify/CustomerAddress/111",  # Same as default
        )

        alt_address = create_shopify_address_response(
            gid="gid://shopify/CustomerAddress/222",
            address1="456 Secondary St",
            city="Boston",
        )

        customer_data = create_shopify_customer_response(
            default_address=default_address,
            addresses=[shipping_address, alt_address],
        )

        shopify_customer = CustomerFields(**customer_data)
        result = self.importer._import_one(shopify_customer)

        self.assertTrue(result)

        partner = self._find_partner_by_customer_id("123456789")
        self.assertTrue(partner)
        self.assertEqual(partner.street, "123 Main St")
        delivery_addresses = partner.child_ids.filtered(lambda c: c.type == "delivery")
        self.assertEqual(len(delivery_addresses), 1)
        self.assertEqual(delivery_addresses[0].street, "456 Secondary St")
