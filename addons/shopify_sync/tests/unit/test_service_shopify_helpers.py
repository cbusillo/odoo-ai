from collections.abc import Callable

from ...services.shopify import helpers
from ...services.shopify.gql.base_model import BaseModel
from ..common_imports import UNIT_TAGS, MagicMock, UserError, datetime, patch, tagged
from ..fixtures.base import UnitTestCase
from ..fixtures.factories import PartnerFactory, ProductFactory


@tagged(*UNIT_TAGS)
class TestShopifyHelpers(UnitTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.env = self.env(context=dict(self.env.context, skip_shopify_sync=True))
        self.test_partner = PartnerFactory.create(
            self.env,
            name="Test Partner",
        )
        self.test_product = ProductFactory.create(self.env)

    def test_normalise_values(self) -> None:
        cases: list[tuple[str, Callable[[str], str], str]] = [
            (" TeSt  ", helpers.normalize_str, "test"),
            ("+1 (800) 555-1234", helpers.normalize_phone, "18005551234"),
            (" Example@Email.Com ", helpers.normalize_email, "example@email.com"),
        ]
        for raw, func, expected in cases:
            with self.subTest(raw=raw, func=func.__name__):
                self.assertEqual(func(raw), expected)

    def test_image_order_key(self) -> None:
        class MockImage:
            def __init__(self, sequence: int | None, create_date: datetime | None) -> None:
                self.sequence = sequence
                self.create_date = create_date

        dt = datetime(2024, 1, 1)
        self.assertEqual(helpers.image_order_key(MockImage(2, dt)), (2, dt))

    def test_last_import_config_key(self) -> None:
        self.assertEqual(helpers.last_import_config_key("product"), "shopify.last_product_import_time")

    def test_sync_mode_properties(self) -> None:
        mode = helpers.SyncMode.IMPORT_ALL_PRODUCTS
        self.assertEqual(mode.display_name, "Import All Products")
        self.assertEqual(mode.resource_type, "product")
        self.assertIn((mode.value, mode.display_name), helpers.SyncMode.choices())

    def test_odoo_data_error_str(self) -> None:
        class MockRec:
            name = "prod"
            id = 42
            default_code = "SKU"

        err = helpers.OdooDataError("msg", MockRec())
        self.assertEqual(str(err), "msg [Odoo Name prod] [Odoo ID 42] [Odoo SKU SKU]")

    def test_odoo_data_error_no_record(self) -> None:
        err = helpers.OdooDataError("x")
        self.assertEqual(err.sku, "")
        self.assertEqual(err.name, "")
        self.assertEqual(str(err), "x")

    def test_odoo_data_error_name_only(self) -> None:
        class Rec:
            name = "n"
            id = None
            default_code = None

        err = helpers.OdooDataError("msg", Rec())
        self.assertEqual(str(err), "msg [Odoo Name n]")

    def test_shopify_api_error_str(self) -> None:
        class Var(BaseModel):
            sku: str | None = None

        class Vars(BaseModel):
            nodes: list[Var]

        class Prod(BaseModel):
            id: str
            title: str
            variants: Vars

        prod = Prod(id="gid/123", title="name", variants=Vars(nodes=[Var(sku="S1")]))
        msg = str(helpers.ShopifyApiError("err", shopify_record=prod))
        self.assertIn("[Shopify ID gid/123]", msg)
        self.assertIn("[Shopify SKU S1]", msg)

    def test_shopify_api_error_only_odoo_record(self) -> None:
        class MockOdoo:
            def __init__(self) -> None:
                self.default_code = "D1"
                self.id = 99
                self.name = "dummy"

        txt = str(helpers.ShopifyApiError("msg", odoo_record=MockOdoo()))
        self.assertIn("[Odoo Name dummy]", txt)
        self.assertNotIn("Shopify ID", txt)

    def test_parse_shopify_datetime_to_utc(self) -> None:
        self.assertEqual(
            helpers.parse_shopify_datetime_to_utc("2024-05-20T12:34:56Z"),
            datetime(2024, 5, 20, 12, 34, 56),
        )

    def test_format_datetime_for_shopify(self) -> None:
        from datetime import UTC

        dt = datetime(2024, 5, 20, 12, 34, 56, tzinfo=UTC)
        self.assertEqual(helpers.format_datetime_for_shopify(dt), "2024-05-20T12:34:56Z")

    def test_parse_format_sku_bin(self) -> None:
        self.assertEqual(helpers.parse_shopify_sku_field_to_sku_and_bin("SKU1 - Bin"), ("SKU1", "Bin"))
        self.assertEqual(helpers.format_sku_bin_for_shopify("SKU1", "Bin"), "SKU1 - Bin")
        self.assertEqual(helpers.parse_shopify_sku_field_to_sku_and_bin("SKU1"), ("SKU1", ""))

    def test_parse_sku_bin_errors(self) -> None:
        for bad in ["", "   "]:
            with self.subTest(bad=bad):
                with self.assertRaises(helpers.ShopifyMissingSkuFieldError):
                    helpers.parse_shopify_sku_field_to_sku_and_bin(bad)

    def test_format_sku_bin_missing_sku(self) -> None:
        with self.assertRaises(helpers.OdooMissingSkuError):
            helpers.format_sku_bin_for_shopify("", "Bin")

    def test_write_if_changed_branches(self) -> None:
        partner = self.env["res.partner"].create({"name": "old", "autopost_bills": "ask"})

        with patch.object(self.env["res.partner"].__class__, "write", wraps=partner.write) as mock_write:
            self.assertFalse(helpers.write_if_changed(partner, {"name": "old"}))
            mock_write.assert_not_called()

        with patch.object(self.env["res.partner"].__class__, "write", wraps=partner.write) as mock_write:
            self.assertTrue(helpers.write_if_changed(partner, {"name": "new"}))
            mock_write.assert_called_once_with({"name": "new"})
            self.assertEqual(partner.name, "new")

    def test_write_if_changed_float(self) -> None:
        product = ProductFactory.create(self.env, list_price=1.23)

        with patch.object(self.env["product.template"].__class__, "write", wraps=product.write) as mock_write:
            self.assertFalse(helpers.write_if_changed(product, {"list_price": 1.23}))
            mock_write.assert_not_called()

        with patch.object(self.env["product.template"].__class__, "write", wraps=product.write) as mock_write:
            self.assertTrue(helpers.write_if_changed(product, {"list_price": 1.25}))
            mock_write.assert_called_once_with({"list_price": 1.25})
            self.assertEqual(product.list_price, 1.25)

        with self.assertRaises(UserError):
            helpers.write_if_changed(product, {"list_price": ["bad"]})

    def test_determine_latest_odoo_product_modification_time(self) -> None:
        class Tmpl:
            def __init__(self, write_date: datetime) -> None:
                self.write_date = write_date

        class Prod:
            def __init__(self, w1: datetime, w2: datetime, w3: datetime) -> None:
                self.write_date = w1
                self.product_tmpl_id = Tmpl(w2)
                self.shopify_last_exported_at = w3

        t1, t2, t3 = datetime(2024, 1, 1), datetime(2024, 1, 2), datetime(2024, 1, 3)
        self.assertEqual(helpers.determine_latest_odoo_product_modification_time(Prod(t1, t2, t3)), t3)

    def test_parse_datetime_and_gid_and_sku_errors(self) -> None:
        naive_dt = datetime(2024, 5, 20, 12, 34, 56)
        self.assertEqual(helpers.parse_shopify_datetime_to_utc(naive_dt), naive_dt)
        self.assertEqual(helpers.parse_shopify_id_from_gid("5"), "5")
        self.assertEqual(helpers.format_shopify_gid_from_id("product", 5), "gid://shopify/product/5")
        with self.assertRaises(helpers.ShopifyMissingSkuFieldError):
            helpers.parse_shopify_sku_field_to_sku_and_bin(" ")
        with self.assertRaises(helpers.OdooMissingSkuError):
            helpers.format_sku_bin_for_shopify("", "bin")

    def test_write_if_changed_multi_record_raises_error(self) -> None:
        partners = self.env["res.partner"].create(
            [
                {"name": "Partner 1", "autopost_bills": "ask"},
                {"name": "Partner 2", "autopost_bills": "ask"},
            ]
        )

        mock_record = MagicMock()
        mock_record._fields = {"partner_ids": MagicMock()}
        mock_record.__getitem__ = lambda _, key: partners if key == "partner_ids" else None

        with self.assertRaises(UserError) as cm:
            helpers.write_if_changed(mock_record, {"partner_ids": partners})

        self.assertIn("multi‑record recordset", str(cm.exception))

        class Var(BaseModel):
            sku: str | None = None

        class Vars(BaseModel):
            nodes: list[Var]

        class Prod(BaseModel):
            id: str
            title: str
            variants: Vars

        prod = Prod(id="gid/1", title="n", variants=Vars(nodes=[Var()]))
        err = helpers.ShopifyApiError("msg", shopify_record=prod)
        err.__cause__ = ValueError("boom")
        self.assertIn("Shopify error: boom", str(err))

    def test_parse_shopify_id_from_gid(self) -> None:
        self.assertEqual(helpers.parse_shopify_id_from_gid("gid://shopify/product/123"), "123")

    def test_parse_shopify_id_from_gid_int(self) -> None:
        self.assertEqual(helpers.parse_shopify_id_from_gid("5"), "5")

    def test_parse_datetime_and_format_with_naive(self) -> None:
        dt_str = "2024-05-20T07:34:56-05:00"
        parsed = helpers.parse_shopify_datetime_to_utc(dt_str)
        self.assertEqual(parsed, datetime(2024, 5, 20, 12, 34, 56))
        naive = datetime(2024, 5, 20, 12, 34, 56)
        self.assertEqual(helpers.format_datetime_for_shopify(naive), "2024-05-20T12:34:56Z")

    def test_image_order_key_defaults(self) -> None:
        class MockImage:
            def __init__(self) -> None:
                self.sequence = None
                self.create_date = None

        self.assertEqual(helpers.image_order_key(MockImage()), (0, helpers.DEFAULT_DATETIME))

    def test_normalise_none(self) -> None:
        funcs: list[Callable[[str | None], str]] = [helpers.normalize_str, helpers.normalize_phone, helpers.normalize_email]
        for func in funcs:
            with self.subTest(func=func.__name__):
                self.assertEqual(func(None), "")

    def test_parse_shopify_sku_field_simple(self) -> None:
        self.assertEqual(helpers.parse_shopify_sku_field_to_sku_and_bin("SKU1 Bin"), ("SKU1", "Bin"))

    def test_determine_latest_modification_none(self) -> None:
        # Test that the function returns DEFAULT_DATETIME when no dates are set
        # Since we can't set write_date to NULL in tests (it's always set on creation),
        # we'll test with a mock object instead
        from unittest.mock import MagicMock

        mock_product = MagicMock()
        mock_product.write_date = None
        mock_product.product_tmpl_id.write_date = None
        mock_product.shopify_last_exported_at = None

        result = helpers.determine_latest_odoo_product_modification_time(mock_product)
        self.assertEqual(result, helpers.DEFAULT_DATETIME)

    def test_write_if_changed_no_changes(self) -> None:
        sale_order = self.env["sale.order"].create(
            {
                "partner_id": self.test_partner.id,
                "state": "draft",
            }
        )

        with patch.object(self.env["sale.order"].__class__, "write", wraps=sale_order.write) as mock_write:
            changed = helpers.write_if_changed(
                sale_order,
                {
                    "partner_id": self.test_partner.id,
                    "state": "draft",
                },
            )
            self.assertFalse(changed)
            mock_write.assert_not_called()

    def test_write_if_changed_with_changes(self) -> None:
        sale_order = self.env["sale.order"].create(
            {
                "partner_id": self.test_partner.id,
                "state": "draft",
            }
        )

        new_partner = PartnerFactory.create(
            self.env,
            name="New Partner",
        )

        with patch.object(self.env["sale.order"].__class__, "write", wraps=sale_order.write) as mock_write:
            changed = helpers.write_if_changed(
                sale_order,
                {
                    "partner_id": new_partner.id,
                    "state": "draft",
                },
            )
            self.assertTrue(changed)
            mock_write.assert_called_once()
            self.assertEqual(sale_order.partner_id.id, new_partner.id)

    def test_write_if_changed_with_float_field(self) -> None:
        product = ProductFactory.create(
            self.env,
            list_price=100.0,
            standard_price=50.0,
        )

        with patch.object(self.env["product.template"].__class__, "write", wraps=product.write) as mock_write:
            changed = helpers.write_if_changed(
                product,
                {
                    "list_price": 100.0,
                    "standard_price": 50.0,
                },
            )
            self.assertFalse(changed)
            mock_write.assert_not_called()

        with patch.object(self.env["product.template"].__class__, "write", wraps=product.write) as mock_write:
            changed = helpers.write_if_changed(
                product,
                {
                    "list_price": 150.0,
                    "standard_price": 50.0,
                },
            )
            self.assertTrue(changed)
            mock_write.assert_called_once_with({"list_price": 150.0})
            self.assertEqual(product.list_price, 150.0)

    def test_shopify_api_error_sku_missing(self) -> None:
        class Prod(BaseModel):
            id: str

        prod = Prod(id="gid/1")
        err = helpers.ShopifyApiError("msg", shopify_record=prod)
        self.assertEqual(err.sku, "")

    def test_shopify_api_error_name_missing_then_present(self) -> None:
        class Prod(BaseModel):
            id: str = "gid/1"
            title: str = "foo"
            variants: list = []

        err = helpers.ShopifyApiError("msg", shopify_record=Prod())
        with patch.object(helpers.OdooDataError, "__str__", lambda _exc: "err"):
            txt = str(err)
            self.assertIn("[foo]", txt)

    def test_shopify_product_id_no_record(self) -> None:
        err = helpers.ShopifyApiError("msg")
        self.assertEqual(err.shopify_product_id, "")

    def test_shopify_api_error_no_shopify_id(self) -> None:
        class Prod(BaseModel):
            id: str | None = None
            title: str = "n"
            variants: list = []

        err = helpers.ShopifyApiError("msg", shopify_record=Prod())
        with patch.object(helpers.OdooDataError, "__str__", lambda _exc: "msg"):
            txt = str(err)
            self.assertNotIn("Shopify ID", txt)

    def test_parse_sku_no_value_error(self) -> None:
        with self.assertRaises(helpers.ShopifyMissingSkuFieldError):
            helpers.parse_shopify_sku_field_to_sku_and_bin(" - Bin")
