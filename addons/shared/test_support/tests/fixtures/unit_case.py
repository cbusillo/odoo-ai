from typing import Any, ClassVar

from odoo.tests import TransactionCase


class AdminContextUnitTestCase(TransactionCase):
    """Run tests as admin with predictable context and optional model aliases."""

    default_test_context: ClassVar[dict[str, Any]] = {}
    model_aliases: ClassVar[dict[str, str]] = {}

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.env = cls.env(user=cls.env.ref("base.user_admin"))
        if cls.default_test_context:
            cls.env = cls.env(context=dict(cls.env.context, **cls.default_test_context))
        cls._bind_model_aliases()

    @classmethod
    def _bind_model_aliases(cls) -> None:
        for alias_name, model_name in cls.model_aliases.items():
            setattr(cls, alias_name, cls.env[model_name])


__all__ = ["AdminContextUnitTestCase"]
