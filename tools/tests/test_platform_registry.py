import unittest
from unittest.mock import patch

import click

from tools.platform import registry


class PlatformRegistryTests(unittest.TestCase):
    def test_resolve_base_images_for_build_preserves_both_env_vars(self) -> None:
        images = registry.resolve_base_images_for_build(
            {
                "ODOO_BASE_RUNTIME_IMAGE": "ghcr.io/example/shared:19.0",
                "ODOO_BASE_DEVTOOLS_IMAGE": "ghcr.io/example/shared:19.0",
            }
        )

        self.assertEqual(images, ("ghcr.io/example/shared:19.0", "ghcr.io/example/shared:19.0"))

    def test_resolve_required_base_images_for_production_build_still_requires_devtools(self) -> None:
        images = registry.resolve_required_base_images_for_build(
            {
                "COMPOSE_BUILD_TARGET": "production",
                "ODOO_BASE_RUNTIME_IMAGE": "ghcr.io/example/runtime:19.0",
                "ODOO_BASE_DEVTOOLS_IMAGE": "ghcr.io/example/devtools:19.0",
            }
        )

        self.assertEqual(
            images,
            (
                ("ODOO_BASE_RUNTIME_IMAGE", "ghcr.io/example/runtime:19.0"),
                ("ODOO_BASE_DEVTOOLS_IMAGE", "ghcr.io/example/devtools:19.0"),
            ),
        )

    def test_resolve_base_images_for_registry_auth_uses_only_explicit_values(self) -> None:
        images = registry.resolve_base_images_for_registry_auth(
            {
                "ODOO_BASE_RUNTIME_IMAGE": "ghcr.io/example/runtime:19.0",
                "ODOO_BASE_DEVTOOLS_IMAGE": "ghcr.io/example/devtools:19.0",
            }
        )

        self.assertEqual(images, ["ghcr.io/example/runtime:19.0", "ghcr.io/example/devtools:19.0"])

    def test_require_configured_base_images_for_build_rejects_placeholders(self) -> None:
        with self.assertRaises(click.ClickException) as captured_error:
            registry.require_configured_base_images_for_build({})

        self.assertIn("ODOO_BASE_RUNTIME_IMAGE", captured_error.exception.message)

    def test_require_configured_base_images_for_build_accepts_identical_real_tags(self) -> None:
        images = registry.require_configured_base_images_for_build(
            {
                "ODOO_BASE_RUNTIME_IMAGE": "ghcr.io/example/shared:19.0",
                "ODOO_BASE_DEVTOOLS_IMAGE": "ghcr.io/example/shared:19.0",
            }
        )

        self.assertEqual(images, ["ghcr.io/example/shared:19.0"])

    def test_require_configured_base_images_for_build_rejects_production_without_devtools_image(self) -> None:
        with self.assertRaises(click.ClickException) as captured_error:
            registry.require_configured_base_images_for_build(
                {
                    "COMPOSE_BUILD_TARGET": "production",
                    "ODOO_BASE_RUNTIME_IMAGE": "ghcr.io/example/runtime:19.0",
                }
            )

        self.assertIn("ODOO_BASE_DEVTOOLS_IMAGE", captured_error.exception.message)

    def test_ensure_registry_auth_for_base_images_skips_non_ghcr_real_images(self) -> None:
        with patch("tools.platform.registry.subprocess.run") as run_mock:
            registry.ensure_registry_auth_for_base_images(
                {
                    "ODOO_BASE_RUNTIME_IMAGE": "registry.example/private-runtime:19.0-runtime",
                    "ODOO_BASE_DEVTOOLS_IMAGE": "registry.example/private-devtools:19.0-devtools",
                }
            )

        run_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
