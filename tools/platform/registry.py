from __future__ import annotations

import os
import subprocess

import click

GHCR_HOST = "ghcr.io"
DEFAULT_ODOO_BASE_RUNTIME_IMAGE = "ghcr.io/cbusillo/odoo-enterprise-docker:19.0-runtime"
DEFAULT_ODOO_BASE_DEVTOOLS_IMAGE = "ghcr.io/cbusillo/odoo-enterprise-docker:19.0-devtools"

_REGISTRY_LOGINS_DONE: set[tuple[str, str]] = set()
_VERIFIED_IMAGE_ACCESS: set[str] = set()


def clean_optional_value(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def extract_registry_host(image_reference: str) -> str | None:
    candidate = image_reference.strip()
    if not candidate:
        return None
    without_digest = candidate.split("@", 1)[0]
    first_segment = without_digest.split("/", 1)[0]
    if "." in first_segment or ":" in first_segment or first_segment == "localhost":
        return first_segment.lower()
    return None


def extract_registry_owner(image_reference: str) -> str | None:
    candidate = image_reference.strip()
    if not candidate:
        return None
    without_digest = candidate.split("@", 1)[0]
    first_segment, separator, remainder = without_digest.partition("/")
    if not separator:
        return None
    if not ("." in first_segment or ":" in first_segment or first_segment == "localhost"):
        return None
    owner, owner_separator, _package_name = remainder.partition("/")
    if owner_separator and owner:
        return owner
    return None


def resolve_base_images_for_registry_auth(environment_values: dict[str, str]) -> list[str]:
    runtime_image = clean_optional_value(environment_values.get("ODOO_BASE_RUNTIME_IMAGE"))
    devtools_image = clean_optional_value(environment_values.get("ODOO_BASE_DEVTOOLS_IMAGE"))

    if runtime_image is None:
        runtime_image = DEFAULT_ODOO_BASE_RUNTIME_IMAGE
    if devtools_image is None:
        devtools_image = DEFAULT_ODOO_BASE_DEVTOOLS_IMAGE

    images: list[str] = []
    for image in (runtime_image, devtools_image):
        if image and image not in images:
            images.append(image)
    return images


def resolve_ghcr_username(environment_values: dict[str, str], image_reference: str) -> str | None:
    candidates = (
        environment_values.get("GHCR_USERNAME"),
        os.environ.get("GHCR_USERNAME"),
        environment_values.get("GITHUB_ACTOR"),
        os.environ.get("GITHUB_ACTOR"),
        extract_registry_owner(image_reference),
    )
    for candidate in candidates:
        cleaned = clean_optional_value(candidate)
        if cleaned:
            return cleaned
    return None


def resolve_ghcr_token(environment_values: dict[str, str]) -> str | None:
    candidates = (
        environment_values.get("GHCR_TOKEN"),
        os.environ.get("GHCR_TOKEN"),
        environment_values.get("GHCR_READ_TOKEN"),
        os.environ.get("GHCR_READ_TOKEN"),
        environment_values.get("GITHUB_TOKEN"),
        os.environ.get("GITHUB_TOKEN"),
    )
    for candidate in candidates:
        cleaned = clean_optional_value(candidate)
        if cleaned:
            return cleaned

    gh_token_result = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True)
    if gh_token_result.returncode == 0:
        gh_token = clean_optional_value(gh_token_result.stdout)
        if gh_token:
            return gh_token
    return None


def verify_base_image_access(image_reference: str) -> None:
    if image_reference in _VERIFIED_IMAGE_ACCESS:
        return
    inspect_result = subprocess.run(["docker", "buildx", "imagetools", "inspect", image_reference], capture_output=True, text=True)
    if inspect_result.returncode != 0:
        details = clean_optional_value(inspect_result.stderr) or clean_optional_value(inspect_result.stdout)
        raise click.ClickException(
            "Unable to read base image metadata for "
            f"'{image_reference}'. Ensure the GHCR token grants read access to the package."
            + (f"\nDocker reported: {details}" if details else ""),
        )
    _VERIFIED_IMAGE_ACCESS.add(image_reference)


def ensure_registry_auth_for_base_images(environment_values: dict[str, str]) -> None:
    images = resolve_base_images_for_registry_auth(environment_values)
    ghcr_images = [image for image in images if extract_registry_host(image) == GHCR_HOST]
    if not ghcr_images:
        return

    ghcr_username = resolve_ghcr_username(environment_values, ghcr_images[0])
    ghcr_token = resolve_ghcr_token(environment_values)

    if not ghcr_username:
        raise click.ClickException(
            "Missing GHCR username for private base image pull. Set GHCR_USERNAME in resolved environment "
            "(selected env file and/or platform/secrets.toml), or provide GITHUB_ACTOR in the current shell.",
        )
    if not ghcr_token:
        raise click.ClickException(
            "Missing GHCR token for private base image pull. Set GHCR_TOKEN (preferred) "
            "or GITHUB_TOKEN in resolved environment (selected env file and/or platform/secrets.toml) "
            "with read:packages access.",
        )

    login_key = (GHCR_HOST, ghcr_username)
    if login_key not in _REGISTRY_LOGINS_DONE:
        login_result = subprocess.run(
            ["docker", "login", GHCR_HOST, "-u", ghcr_username, "--password-stdin"],
            input=f"{ghcr_token}\n",
            capture_output=True,
            text=True,
        )
        if login_result.returncode != 0:
            details = clean_optional_value(login_result.stderr) or clean_optional_value(login_result.stdout)
            raise click.ClickException(
                "Docker login to GHCR failed. Ensure the token is valid and has package read permissions."
                + (f"\nDocker reported: {details}" if details else ""),
            )
        _REGISTRY_LOGINS_DONE.add(login_key)

    for image in ghcr_images:
        verify_base_image_access(image)
