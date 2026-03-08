from odoo.addons.marine_motors.tests.fixtures.factories import MotorFactory as SharedMotorFactory
from test_support.tests.fixtures.factories import PartnerFactory, ProductFactory, SaleOrderFactory


class MotorFactory:
    @staticmethod
    def create(*args: object, **kwargs: object) -> "odoo.model.product_template":
        return SharedMotorFactory.create(*args, **kwargs)

__all__ = [
    "MotorFactory",
    "PartnerFactory",
    "ProductFactory",
    "SaleOrderFactory",
]
