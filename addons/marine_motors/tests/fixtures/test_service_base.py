from .test_base import ProductConnectTransactionCase
from .base import _BaseDataMixin, _ShopifyMockMixin
from ..common_imports import tagged, STANDARD_TAGS


@tagged(*STANDARD_TAGS)
class ShopifyTestBase(_ShopifyMockMixin, _BaseDataMixin, ProductConnectTransactionCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.env = cls.env(context={"skip_shopify_sync": True})

    def setUp(self) -> None:
        super().setUp()
        self.shopify_service_patcher = None

    def tearDown(self) -> None:
        self._teardown_shopify_mocks()
        super().tearDown()
