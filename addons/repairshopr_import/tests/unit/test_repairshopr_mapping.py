from types import SimpleNamespace

from ...models.repairshopr_importer import EXTERNAL_SYSTEM_CODE, RESOURCE_ESTIMATE, RESOURCE_PRODUCT
from ..common_imports import UNIT_TAGS, tagged
from ..fixtures.base import UnitTestCase


@tagged(*UNIT_TAGS)
class TestRepairshoprMapping(UnitTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.importer = self.RepairshoprImporter

    def test_build_partner_values_from_customer_company(self) -> None:
        customer_record = SimpleNamespace(
            id=101,
            business_name="Shiny Computers",
            fullname=None,
            firstname=None,
            lastname=None,
            email="owner@example.com",
            no_email=False,
            phone="555-1111",
            mobile=None,
            address="123 Main",
            address_2="Suite 1",
            city="Springfield",
            zip="12345",
            notes="Notes",
            disabled=False,
            state=None,
        )

        values_payload = self.importer._build_partner_values_from_customer(customer_record)

        self.assertEqual(values_payload["name"], "Shiny Computers")
        self.assertEqual(values_payload["company_type"], "company")
        self.assertTrue(values_payload["is_company"])
        self.assertEqual(values_payload["email"], "owner@example.com")
        self.assertEqual(values_payload["phone"], "555-1111")
        self.assertEqual(values_payload["street"], "123 Main")

    def test_build_partner_values_from_contact_uses_extension(self) -> None:
        parent_partner = self.Partner.create({"name": "Parent Partner"})
        contact_record = SimpleNamespace(
            id=202,
            name="Sam Service",
            email="sam@example.com",
            address1="456 Elm",
            address2=None,
            city="Metropolis",
            zip="67890",
            notes=None,
            processed_phone=None,
            phone="555-2222",
            processed_mobile=None,
            mobile=None,
            extension="44",
            state=None,
        )

        values_payload = self.importer._build_partner_values_from_contact(contact_record, parent_partner)

        self.assertEqual(values_payload["parent_id"], parent_partner.id)
        self.assertEqual(values_payload["phone"], "555-2222 x44")

    def test_build_product_values(self) -> None:
        product_record = SimpleNamespace(
            id=303,
            name=None,
            description="Widget",
            price_retail=25.0,
            price_cost=12.5,
            long_description="Long description",
            disabled=False,
            upc_code="ABC-123",
        )

        values_payload = self.importer._build_product_values(product_record)

        self.assertEqual(values_payload["name"], "Widget")
        self.assertEqual(values_payload["list_price"], 25.0)
        self.assertEqual(values_payload["standard_price"], 12.5)
        self.assertEqual(values_payload["description"], "Widget")
        self.assertEqual(values_payload["description_sale"], "Long description")
        self.assertTrue(values_payload["active"])
        self.assertEqual(values_payload["barcode"], "ABC123")

    def test_merge_values_for_existing_product_only_fills_missing(self) -> None:
        product_record = self.ProductTemplate.create(
            {
                "name": "Existing",
                "list_price": 20.0,
                "standard_price": 10.0,
                "description": "Existing description",
                "description_sale": "",
            }
        )
        values_payload = {
            "list_price": 30.0,
            "standard_price": 15.0,
            "description": "Incoming description",
            "description_sale": "Incoming sale description",
            "barcode": "SKU-123",
        }

        merged_values = self.importer._merge_values_for_existing_product(product_record, values_payload)

        self.assertNotIn("list_price", merged_values)
        self.assertNotIn("standard_price", merged_values)
        self.assertNotIn("description", merged_values)
        self.assertEqual(merged_values.get("description_sale"), "Incoming sale description")
        self.assertEqual(merged_values.get("barcode"), "SKU-123")

    def test_sanitize_update_values_skips_barcode_conflict(self) -> None:
        product_one = self.ProductTemplate.create({"name": "Product One", "barcode": "111"})
        product_two = self.ProductTemplate.create({"name": "Product Two"})

        values_payload = {"barcode": "111"}
        sanitized_values = self.importer._sanitize_update_values(product_two, values_payload)

        self.assertNotIn("barcode", sanitized_values)
        self.assertEqual(product_one.barcode, "111")

    def test_extract_standard_price(self) -> None:
        values_payload = {"name": "Test", "standard_price": 9.5}

        remaining_values, standard_price_value = self.importer._extract_standard_price(values_payload)

        self.assertNotIn("standard_price", remaining_values)
        self.assertEqual(standard_price_value, 9.5)

    def test_compose_ticket_description(self) -> None:
        properties = SimpleNamespace(id=1, rs_client="ignore", color="Red", size="Large")
        comments = [
            SimpleNamespace(
                hidden=False,
                created_at="2024-01-01",
                tech="Alex",
                subject="Inspection",
                body="All good",
            ),
            SimpleNamespace(hidden=True, created_at="2024-01-02", tech="Hidden", subject="", body=""),
        ]
        ticket_record = SimpleNamespace(
            problem_type="Battery",
            status="Open",
            priority="High",
            properties=properties,
            comments=comments,
        )

        description = self.importer._compose_ticket_description(ticket_record)

        self.assertIn("Problem Type: Battery", description)
        self.assertIn("Status: Open", description)
        self.assertIn("Priority: High", description)
        self.assertIn("Color: Red", description)
        self.assertIn("Size: Large", description)
        self.assertIn("Comments:", description)
        self.assertIn("Inspection", description)
        self.assertIn("All good", description)

    def test_fetch_line_items_handles_missing_payload(self) -> None:
        class ClientStub:
            @staticmethod
            def fetch_from_api(_endpoint: str, *, params: dict[str, str]) -> tuple[list[dict[str, object]] | None]:
                return (None,)

        line_items = self.importer._fetch_line_items(ClientStub(), estimate_id=10)

        self.assertEqual(line_items, [])

    def test_build_product_values_with_partial_payload(self) -> None:
        product_record = SimpleNamespace(
            id=404,
            name=None,
            description=None,
            price_retail=None,
            price_cost=None,
            long_description=None,
            disabled=False,
            upc_code=None,
            product_category=None,
            category_path=None,
        )

        values_payload = self.importer._build_product_values(product_record)

        self.assertEqual(values_payload["name"], "RepairShopr Product 404")
        self.assertEqual(values_payload["list_price"], 0.0)
        self.assertEqual(values_payload["standard_price"], 0.0)
        self.assertEqual(values_payload["description"], "")
        self.assertEqual(values_payload["description_sale"], "")
        self.assertTrue(values_payload["active"])
        self.assertNotIn("barcode", values_payload)

    def test_import_products_is_idempotent(self) -> None:
        class ClientStub:
            def __init__(self, products: list[SimpleNamespace]) -> None:
                self._products = products

            def get_model(self, _model: object, *, updated_at: object = None) -> list[SimpleNamespace]:
                return self._products

        product_record = SimpleNamespace(
            id=505,
            name="Widget",
            description="Widget",
            price_retail=10.0,
            price_cost=5.0,
            long_description=None,
            disabled=False,
            upc_code=None,
            product_category=None,
            category_path=None,
        )
        client = ClientStub([product_record])

        self.importer._import_products(client, None)
        first_product = self.ProductTemplate.search_by_external_id(
            EXTERNAL_SYSTEM_CODE,
            "505",
            RESOURCE_PRODUCT,
        )
        self.importer._import_products(client, None)
        second_product = self.ProductTemplate.search_by_external_id(
            EXTERNAL_SYSTEM_CODE,
            "505",
            RESOURCE_PRODUCT,
        )

        self.assertTrue(first_product)
        self.assertEqual(first_product.id, second_product.id)
        self.assertEqual(self.ProductTemplate.search_count([("name", "=", "Widget")]), 1)

    def test_import_estimates_is_idempotent(self) -> None:
        class ClientStub:
            def __init__(self, estimates: list[SimpleNamespace]) -> None:
                self._estimates = estimates

            def get_model(self, _model: object, *, updated_at: object = None) -> list[SimpleNamespace]:
                return self._estimates

            @staticmethod
            def fetch_from_api(
                _endpoint: str,
                *,
                params: dict[str, str],
            ) -> tuple[list[dict[str, object]]]:
                return ([],)

        estimate_record = SimpleNamespace(
            id=606,
            customer_id=707,
            customer_business_then_name="Test Customer",
            number="EST-606",
            date=None,
            created_at=None,
            employee=None,
        )
        client = ClientStub([estimate_record])

        self.importer._import_estimates(client, None)
        first_order = self.env["sale.order"].search_by_external_id(
            EXTERNAL_SYSTEM_CODE,
            "606",
            RESOURCE_ESTIMATE,
        )
        self.importer._import_estimates(client, None)
        second_order = self.env["sale.order"].search_by_external_id(
            EXTERNAL_SYSTEM_CODE,
            "606",
            RESOURCE_ESTIMATE,
        )

        self.assertTrue(first_order)
        self.assertEqual(first_order.id, second_order.id)
