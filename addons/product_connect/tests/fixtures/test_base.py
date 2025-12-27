import secrets

from ..common_imports import TransactionCase, HttpCase, tagged, STANDARD_TAGS, UNIT_TAGS, TOUR_TAGS
from .factories import (
    ProductTagFactory,
    CrmTagFactory,
    PartnerFactory,
    ProductFactory,
    ProductImageFactory,
    ResUsersFactory,
)


@tagged(*STANDARD_TAGS)
class ProductConnectTransactionCase(TransactionCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()

        cls.env = cls.env(user=cls.env.ref("base.user_admin"))

        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))

        cls._setup_test_data()

    def setUp(self) -> None:
        super().setUp()
        self.env = self.env(user=self.env.ref("base.user_admin"))
        self.env = self.env(context=dict(self.env.context, skip_shopify_sync=True, tracking_disable=True))

    @classmethod
    def _setup_test_data(cls) -> None:
        cls.env = cls.env(context=dict(cls.env.context, skip_shopify_sync=True))

        cls._create_test_tags()

        cls._create_default_test_products()

    @classmethod
    def _create_test_tags(cls) -> None:
        cls.test_product_tag = ProductTagFactory.create(
            cls.env,
            name="Test Suite Data",
            sequence=999,
            color=10,
        )

        cls.test_order_tag = CrmTagFactory.create(
            cls.env,
            name="Test Suite Data",
            color=10,
        )

    @classmethod
    def _get_default_product_vals(cls) -> dict:
        return {
            "type": "consu",
            "list_price": 100.0,
            "sale_ok": True,
            "purchase_ok": True,
            "is_storable": True,
            "website_description": "Test product description",
            "product_tag_ids": [(4, cls.test_product_tag.id)],
        }

    @classmethod
    def _get_default_order_vals(cls) -> dict:
        return {
            "partner_id": cls.test_partner.id,
            "tag_ids": [(4, cls.test_order_tag.id)],
        }

    @classmethod
    def _get_default_partner_vals(cls) -> dict:
        return {
            "email": "test@example.com",
            "is_company": False,
        }

    @classmethod
    def _create_multigraph_test_products(cls) -> None:
        from datetime import date

        cls.test_products = cls.env["product.template"].create(
            [
                {
                    "name": f"Test Product {i}",
                    "default_code": f"{10000 + i}",
                    "list_price": 100 * i,
                    "standard_price": 60 * i,
                    "type": "consu",
                    "is_ready_for_sale": True,
                    "is_ready_for_sale_last_enabled_date": date(2025, 1, i),
                    "initial_quantity": 10 * i,
                    "initial_price_total": 1000 * i,
                    "initial_cost_total": 600 * i,
                }
                for i in range(1, 5)
            ]
        )

    @classmethod
    def _create_motor_dependencies(cls) -> dict:
        manufacturer = cls.env["product.manufacturer"].search([("name", "=", "Test Manufacturer")], limit=1)
        if not manufacturer:
            manufacturer = cls.env["product.manufacturer"].create({"name": "Test Manufacturer", "is_motor_manufacturer": True})

        stroke = cls.env["motor.stroke"].search([("code", "=", "4")], limit=1)
        if not stroke:
            stroke = cls.env["motor.stroke"].sudo().create({"name": "4 Stroke", "code": "4"})

        config = cls.env["motor.configuration"].search([("code", "=", "V6")], limit=1)
        if not config:
            config = cls.env["motor.configuration"].sudo().create({"name": "V6", "code": "V6"})

        return {
            "manufacturer": manufacturer,
            "stroke": stroke,
            "config": config,
        }

    @classmethod
    def _create_motor(cls, **kwargs: int | float | str | bool) -> "odoo.model.motor":
        deps = cls._create_motor_dependencies()

        motor_vals = {
            "manufacturer": deps["manufacturer"].id,
            "stroke": deps["stroke"].id,
            "configuration": deps["config"].id,
            "horsepower": 100.0,
            "year": "2024",
            "model": "TEST",
            "cost": 1000.0,
            "location": f"A{secrets.token_hex(2)}",
            "serial_number": f"SN{secrets.token_hex(4)}",
        }
        motor_vals.update(kwargs)

        return cls.env["motor"].create(motor_vals)

    @classmethod
    def _create_motor_product(cls, **kwargs: dict | int | float | str | bool) -> "odoo.model.product_template":
        motor_vals = kwargs.pop("motor_vals", {})
        template_vals = kwargs.pop("template_vals", {})
        with_image = kwargs.pop("with_image", False)

        motor = kwargs.pop("motor", None)
        if not motor:
            motor = cls._create_motor(**motor_vals)

        motor_product_template = kwargs.pop("motor_product_template", None)
        if not motor_product_template:
            deps = cls._create_motor_dependencies()
            default_template_vals = {
                "name": "Test Motor Part",
                "strokes": [(4, deps["stroke"].id)],
                "configurations": [(4, deps["config"].id)],
                "manufacturers": [(4, deps["manufacturer"].id)],
            }
            default_template_vals.update(template_vals)
            motor_product_template = cls.env["motor.product.template"].create(default_template_vals)

        product_vals = {
            "name": "Test Motor Product",
            "default_code": str(60000000 + secrets.randbelow(999999)),
            "type": "consu",
            "source": "motor",
            "motor": motor.id,
            "motor_product_template": motor_product_template.id,
        }
        product_vals.update(kwargs)

        product = cls.env["product.template"].create(product_vals)

        if with_image:
            # noinspection SpellCheckingInspection
            ProductImageFactory.create(
                cls.env,
                product_tmpl_id=product.id,
                image_1920="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
                name="test_image",
            )

        return product

    @classmethod
    def _create_default_test_products(cls) -> None:
        cls.test_partner = PartnerFactory.create(
            cls.env,
            **cls._get_default_partner_vals(),
            name="Test Customer",
        )

        cls.test_partners = []
        for i in range(3):
            partner = PartnerFactory.create(
                cls.env,
                **cls._get_default_partner_vals(),
                name=f"Test Customer {i + 1}",
                email=f"test{i + 1}@example.com",
            )
            cls.test_partners.append(partner)

        cls.test_product = ProductFactory.create(
            cls.env,
            **cls._get_default_product_vals(),
            name="Test Product",
            default_code="10000001",
        ).product_variant_id

        cls.test_service = ProductFactory.create(
            cls.env,
            **cls._get_default_product_vals(),
            name="Test Service",
            default_code="90000001",
            type="service",
            list_price=50.0,
        ).product_variant_id

        cls.test_product_ready = ProductFactory.create(
            cls.env,
            **cls._get_default_product_vals(),
            name="Test Product Ready",
            default_code="20000001",
            list_price=200.0,
            is_ready_for_sale=True,
            is_published=True,
        ).product_variant_id

        cls.test_products = []
        for i in range(10):
            sku_number = 30000001 + i
            product = ProductFactory.create(
                cls.env,
                **cls._get_default_product_vals(),
                name=f"Test Product {i + 1}",
                default_code=str(sku_number),
                list_price=50.0 + (i * 10),
            ).product_variant_id
            cls.test_products.append(product)

        cls.test_product_not_for_sale = ProductFactory.create(
            cls.env,
            **cls._get_default_product_vals(),
            name="Test Product Not For Sale",
            default_code="40000001",
            list_price=150.0,
            sale_ok=False,
        ).product_variant_id

        cls.test_product_unpublished = ProductFactory.create(
            cls.env,
            **cls._get_default_product_vals(),
            name="Test Product Unpublished",
            default_code="40000002",
            list_price=175.0,
            is_published=False,
            is_ready_for_sale=True,
        ).product_variant_id

        cls.test_product_motor = ProductFactory.create(
            cls.env,
            **cls._get_default_product_vals(),
            name="Test Motor Product",
            default_code="50000001",
            list_price=500.0,
            source="motor",
        ).product_variant_id


@tagged(*STANDARD_TAGS)
class ProductConnectHttpCase(HttpCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))

        cls._create_test_user()

        cls._setup_test_data()

    @classmethod
    def _create_test_user(cls, name: str = "Test User", login_prefix: str = "test_user") -> "odoo.model.res_users":
        unique_suffix = secrets.token_hex(4)
        login = f"{login_prefix}_{unique_suffix}"

        secure_password = secrets.token_urlsafe(32)

        cls.test_user = ResUsersFactory.create(
            cls.env,
            name=name,
            login=login,
            password=secure_password,
            groups_id=[
                (
                    6,
                    0,
                    [
                        cls.env.ref("base.group_user").id,
                        cls.env.ref("base.group_system").id,
                        cls.env.ref("base.group_partner_manager").id,
                        cls.env.ref("base.group_erp_manager").id,
                    ],
                )
            ],
        )

        cls.test_user_password = secure_password

        admin_user = cls.env.ref("base.user_admin")
        admin_user.write({"password": "admin"})

        return cls.test_user

    @classmethod
    def _setup_test_data(cls) -> None:
        pass

    def authenticate_test_user(self) -> None:
        self.authenticate(self.test_user.login, self.test_user_password)


@tagged(*STANDARD_TAGS)
class ProductConnectIntegrationCase(ProductConnectHttpCase):
    @classmethod
    def _setup_test_data(cls) -> None:
        super()._setup_test_data()

        if not cls.env["motor"].search([]):
            cls.test_motor = cls.env["motor"].create(
                {
                    "manufacturer": "TestMaker",
                    "stroke": "Four",
                    "configuration": "V8",
                    "horsepower": 250,
                    "location": "A1",
                    "serial_number": f"SN_{secrets.token_hex(4)}",
                    "year": 2024,
                    "model": "SuperV8",
                }
            )
        else:
            cls.test_motor = cls.env["motor"].search([], limit=1)


@tagged(*UNIT_TAGS)
class ProductConnectUnitCase(TransactionCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()

        cls.env = cls.env(user=cls.env.ref("base.user_admin"))

        cls.env = cls.env(
            context=dict(
                cls.env.context,
                tracking_disable=True,
                skip_shopify_sync=True,
                no_reset_password=True,
                mail_create_nosubscribe=True,
                mail_create_nolog=True,
            )
        )

        cls._setup_minimal_test_data()

    @classmethod
    def _setup_minimal_test_data(cls) -> None:
        import secrets

        unique_sku = f"1{secrets.randbelow(999):03d}"
        cls.test_product = cls.env["product.template"].create(
            {
                "name": "Unit Test Product",
                "default_code": unique_sku,
                "type": "consu",
                "list_price": 100.0,
            }
        )

        cls.test_partner = PartnerFactory.create(
            cls.env,
            name="Unit Test Partner",
            email="unit@test.com",
        )

        cls.test_service = cls.env["product.template"].create(
            {
                "name": "Unit Test Service",
                "type": "service",
                "list_price": 50.0,
            }
        )

    def setUp(self) -> None:
        super().setUp()


@tagged("post_install", "-at_install", "validation_test")
class ProductConnectValidationCase(TransactionCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()

        cls.env = cls.env(user=cls.env.ref("base.user_admin"))

        cls.env = cls.env(
            context=dict(
                cls.env.context,
                skip_shopify_sync=True,
            )
        )

        cls._setup_validation_context()

    @classmethod
    def _setup_validation_context(cls) -> None:
        cls.product_count = cls.env["product.template"].search_count([])
        cls.partner_count = cls.env["res.partner"].search_count([])
        cls.order_count = cls.env["sale.order"].search_count([])

        pass


@tagged(*TOUR_TAGS)
class ProductConnectTourCase(HttpCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()

        cls.env = cls.env(
            context=dict(
                cls.env.context,
                tracking_disable=True,
                skip_shopify_sync=True,
            )
        )

        cls._create_tour_test_user()

        cls._setup_tour_test_data()

    @classmethod
    def _create_tour_test_user(cls) -> None:
        unique_suffix = secrets.token_hex(4)
        login = f"tour_user_{unique_suffix}"

        password = secrets.token_urlsafe(16)

        cls.tour_user = ResUsersFactory.create(
            cls.env,
            name="Tour Test User",
            login=login,
            password=password,
            groups_id=[
                (
                    6,
                    0,
                    [
                        cls.env.ref("base.group_user").id,
                        cls.env.ref("base.group_system").id,
                    ],
                )
            ],
        )

        cls.tour_user_password = password

        admin = cls.env.ref("base.user_admin")
        admin.write({"password": "admin"})

    @classmethod
    def _setup_tour_test_data(cls) -> None:
        cls.test_product = cls.env["product.template"].create(
            {
                "name": "Tour Test Product",
                "default_code": "12345678",
                "type": "consu",
                "list_price": 100.0,
                "is_ready_for_sale": True,
            }
        )

        cls.test_partner = PartnerFactory.create(
            cls.env,
            name="Tour Test Customer",
            email="tour@test.com",
        )

    def start_tour(self, url_path: str, tour_name: str, login: str | None = None, **kwargs: object) -> None:
        if login:
            self.authenticate(login, self.tour_user_password)
        else:
            self.authenticate(self.tour_user.login, self.tour_user_password)

        super().start_tour(url_path, tour_name, login=False, **kwargs)
