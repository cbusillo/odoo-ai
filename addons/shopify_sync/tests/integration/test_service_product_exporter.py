from odoo import fields

from ..common_imports import MagicMock, tagged, timedelta, INTEGRATION_TAGS

from ...services.shopify.sync.exporters.product_exporter import ProductExporter
from ...services.shopify import helpers as _helpers_module
from ...services.shopify.gql import (
    ProductSetProductSetProductResourcePublicationsV2NodesPublication,
    ProductSetProductSetProductResourcePublicationsV2Nodes,
)
from ..fixtures.base import IntegrationTestCase


class DummySync:
    def __init__(self) -> None:
        self.id = 1
        self.hard_throttle_count = 0
        self.total_count = 0
        self.updated_count = 0

    def ensure_not_canceled(self) -> None:
        return


class DummyPublication(ProductSetProductSetProductResourcePublicationsV2NodesPublication):
    def __init__(self, gid: str) -> None:
        super().__init__(id=gid, publication=type("P", (), {"id": gid})())


class DummyPublicationNode(ProductSetProductSetProductResourcePublicationsV2Nodes):
    def __init__(self, gid: str) -> None:
        publication = DummyPublication(gid)
        super().__init__(publication=publication)


@tagged(*INTEGRATION_TAGS)
class TestProductExporter(IntegrationTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.exporter = ProductExporter(self.env, DummySync())

        from ..fixtures.factories import ProductFactory

        self.test_products = []
        for i in range(3):
            product_template = ProductFactory.create(
                self.env,
                list_price=100.0 + (i * 10),
            )
            self.test_products.append(product_template.product_variant_id)

    def test_metafield_from_id_value_key(self) -> None:
        result = ProductExporter.metafield_from_id_value_key("5", "k", "v", "text")
        self.assertEqual(result.namespace, "custom")
        self.assertEqual(result.key, "k")
        self.assertEqual(result.value, "v")
        self.assertEqual(result.type, "text")
        self.assertEqual(str(result.id), "gid://shopify/Metafield/5")

    def test_is_published_on_channel(self) -> None:
        gid = "gid://shopify/Publication/" + str(next(iter(_helpers_module.PUBLICATION_CHANNELS.values())))
        publication = DummyPublication(gid)
        self.assertTrue(ProductExporter.is_published_on_channel(publication))
        publication.id = "gid://shopify/Publication/999"
        self.assertFalse(ProductExporter.is_published_on_channel(publication))

    def test_is_published_on_all_channels(self) -> None:
        values = list(_helpers_module.PUBLICATION_CHANNELS.values())
        channels = [DummyPublicationNode(f"gid://shopify/Publication/{v}") for v in values]
        self.assertTrue(self.exporter.is_published_on_all_channels(channels))
        channels.append(DummyPublicationNode("gid://shopify/Publication/999"))
        self.assertFalse(self.exporter.is_published_on_all_channels(channels))

    def test_publish_product(self) -> None:
        self.env["ir.config_parameter"].sudo().set_param("shopify.test_store", "")
        self.exporter.service._client = MagicMock()
        self.exporter._publish_product("gid")
        self.exporter.service.client.update_publications.assert_called_once()

    def test_publish_product_skipped_on_test_store(self) -> None:
        self.env["ir.config_parameter"].sudo().set_param("shopify.test_store", "1")
        self.exporter.service._client = MagicMock()
        self.exporter._publish_product("gid")
        self.exporter.service.client.update_publications.assert_not_called()

    def test_find_products_to_export(self) -> None:
        prod1 = self.test_products[0]  # This is a product.product
        prod1.is_ready_for_sale = True
        prod1.is_published = True
        setattr(prod1, "shopify_next_export", True)

        prod2 = self.test_products[1]  # This is a product.product
        prod2.write(
            {
                "is_ready_for_sale": True,
                "is_published": True,
                "sale_ok": False,
            }
        )

        prod3 = self.test_products[2]  # This is a product.product
        prod3.is_ready_for_sale = True
        prod3.is_published = True
        setattr(prod3, "shopify_last_exported_at", fields.Datetime.now() + timedelta(days=1))

        result = self.exporter._find_products_to_export()
        self.assertIn(prod1, result)
        self.assertNotIn(prod2, result)
        self.assertNotIn(prod3, result)
