import os
from collections.abc import Iterator
from contextlib import contextmanager

from ..common_imports import UNIT_TAGS, tagged
from ..fixtures.base import UnitTestCase


@contextmanager
def _set_env(key: str, value: str | None) -> Iterator[None]:
    previous = os.environ.get(key)
    if value is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = value
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = previous


@tagged(*UNIT_TAGS)
class TestAuthentikSso(UnitTestCase):
    def test_normalize_authentik_validation_defaults(self) -> None:
        payload = {"sub": "user-1", "email": "user@example.com"}

        normalized = self.Users._normalize_authentik_validation(payload)

        self.assertEqual(normalized.get("user_id"), "user-1")
        self.assertEqual(normalized.get("login"), "user@example.com")
        self.assertEqual(normalized.get("email"), "user@example.com")
        self.assertEqual(normalized.get("name"), "user@example.com")

    def test_extract_authentik_groups(self) -> None:
        payload = {"groups": ["Admins", " Users ", ""]}

        with _set_env("ENV_OVERRIDE_AUTHENTIK__GROUP_CLAIM", "groups"):
            groups = self.Users._extract_authentik_groups(payload)

        self.assertEqual(groups, {"Admins", "Users"})

    def test_sync_authentik_groups_applies_mapping(self) -> None:
        provider = self.env["auth.oauth.provider"].create(
            {
                "name": "Authentik",
                "auth_endpoint": "https://auth.example.com/authorize",
                "validation_endpoint": "https://auth.example.com/userinfo",
                "body": "Login with Authentik",
                "enabled": True,
            }
        )
        engineering_group = self.env["res.groups"].create({"name": "Engineering"})
        mapping = self.AuthentikMapping.create(
            {
                "authentik_group": "Engineering",
                "odoo_groups": [(6, 0, [engineering_group.id])],
                "sequence": 5,
            }
        )
        self.assertTrue(mapping)

        self.env["ir.model.data"].create(
            {
                "name": "engineering_group",
                "module": "authentik_sso",
                "model": "res.groups",
                "res_id": engineering_group.id,
                "noupdate": True,
            }
        )
        user = self.env["res.users"].create(
            {
                "name": "OAuth User",
                "login": "oauth_user",
            }
        )

        self.Users._sync_authentik_groups(user, {"groups": ["Engineering"]}, provider.id)

        self.assertIn(user, engineering_group.user_ids)
        self.assertTrue(user.has_group("base.group_user"))
