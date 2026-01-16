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

    def test_normalize_authentik_validation_empty_claim_overrides(self) -> None:
        payload = {"sub": "user-2", "email": "user2@example.com"}

        with _set_env("ENV_OVERRIDE_AUTHENTIK__USER_ID_CLAIMS", " "):
            with _set_env("ENV_OVERRIDE_AUTHENTIK__LOGIN_CLAIMS", " "):
                normalized = self.Users._normalize_authentik_validation(payload)

        self.assertEqual(normalized.get("user_id"), "user-2")
        self.assertEqual(normalized.get("login"), "user2@example.com")
        self.assertEqual(normalized.get("email"), "user2@example.com")

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

    def test_sync_authentik_groups_uses_fallback_mapping(self) -> None:
        provider = self.env["auth.oauth.provider"].create(
            {
                "name": "Authentik",
                "auth_endpoint": "https://auth.example.com/authorize",
                "validation_endpoint": "https://auth.example.com/userinfo",
                "body": "Login with Authentik",
                "enabled": True,
            }
        )
        fallback_group = self.env["res.groups"].create({"name": "Fallback Team"})
        fallback_mapping = self.AuthentikMapping.search([("is_fallback", "=", True)], limit=1)
        if not fallback_mapping:
            fallback_mapping = self.AuthentikMapping.create({"is_fallback": True})
        fallback_mapping.write({"odoo_groups": [(4, fallback_group.id)]})
        user = self.env["res.users"].create(
            {
                "name": "Fallback User",
                "login": "fallback_user",
            }
        )

        self.Users._sync_authentik_groups(user, {}, provider.id)

        self.assertIn(user, fallback_group.user_ids)

    def test_sync_authentik_groups_without_mapping_logs_warning(self) -> None:
        provider = self.env["auth.oauth.provider"].create(
            {
                "name": "Authentik",
                "auth_endpoint": "https://auth.example.com/authorize",
                "validation_endpoint": "https://auth.example.com/userinfo",
                "body": "Login with Authentik",
                "enabled": True,
            }
        )
        self.AuthentikMapping.search([]).unlink()
        user = self.env["res.users"].create(
            {
                "name": "No Mapping User",
                "login": "no_mapping_user",
            }
        )

        with self.assertLogs("odoo.addons.authentik_sso.models.res_users", level="WARNING") as log_capture:
            self.Users._sync_authentik_groups(user, {"groups": ["Engineering"]}, provider.id)

        warning_messages = " ".join(log_capture.output)
        self.assertIn("no mappings configured", warning_messages)

    def test_ensure_default_mappings_does_not_override_custom_admin_mapping(self) -> None:
        admin_user = self.env.ref("base.user_admin")
        system_group = self.env.ref("base.group_system")
        mapping = self.env.ref("authentik_sso.authentik_group_mapping_admins")

        extra_group = self.env["res.groups"].create({"name": "Extra Admin"})
        admin_user.write({"group_ids": [(4, extra_group.id)]})

        mapping.write({"odoo_groups": [(6, 0, [system_group.id])]})
        self.AuthentikMapping.ensure_default_mappings()
        mapping = self.AuthentikMapping.browse(mapping.id)
        self.assertIn(extra_group.id, mapping.odoo_groups.ids)

        mapping.write({"odoo_groups": [(3, extra_group.id)]})
        group_ids_before = set(mapping.odoo_groups.ids)
        self.assertNotIn(extra_group.id, group_ids_before)

        self.AuthentikMapping.ensure_default_mappings()
        mapping = self.AuthentikMapping.browse(mapping.id)
        group_ids_after = set(mapping.odoo_groups.ids)
        self.assertEqual(group_ids_after, group_ids_before)
