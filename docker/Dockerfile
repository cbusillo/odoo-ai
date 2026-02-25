# syntax=docker/dockerfile:1.6
ARG ODOO_VERSION=19.0
ARG ODOO_BASE_RUNTIME_IMAGE=ghcr.io/cbusillo/odoo-enterprise-docker:19.0-runtime
ARG ODOO_BASE_DEVTOOLS_IMAGE=ghcr.io/cbusillo/odoo-enterprise-docker:19.0-devtools

FROM alpine:3.20 AS addon_sources
ARG ODOO_ADDON_REPOSITORIES
ARG ODOO_VERSION
SHELL ["/bin/sh", "-euc"]
RUN apk add --no-cache ca-certificates curl tar
COPY /docker/scripts/fetch_addons.sh /usr/local/bin/fetch_addons.sh
RUN --mount=type=secret,id=github_token \
    chmod +x /usr/local/bin/fetch_addons.sh \
    && GITHUB_TOKEN="$(cat /run/secrets/github_token 2>/dev/null || true)" /usr/local/bin/fetch_addons.sh

FROM ${ODOO_BASE_RUNTIME_IMAGE} AS base-runtime
USER root
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

COPY /docker/config /volumes/config
COPY /docker/scripts /volumes/scripts
COPY /addons /volumes/addons
COPY --from=addon_sources /extra_addons /opt/extra_addons
COPY /pyproject.toml /volumes/pyproject.toml
COPY /uv.lock /volumes/uv.lock

RUN mkdir -p /opt \
    && rm -rf /opt/project \
    && ln -s /volumes /opt/project

RUN set -eux; \
    if ! command -v uv >/dev/null 2>&1; then \
        curl -LsSf https://astral.sh/uv/install.sh | sh; \
        cp /root/.local/bin/uv* /usr/local/bin/; \
    fi

RUN set -eux; \
    if grep -q "ODOO_SOURCE_BIN" /odoo/odoo-bin; then \
        if [ ! -f /usr/local/bin/odoo-source-bin ]; then \
            echo "Missing /usr/local/bin/odoo-source-bin while /odoo/odoo-bin is already a wrapper" >&2; \
            exit 1; \
        fi; \
    else \
        cp /odoo/odoo-bin /usr/local/bin/odoo-source-bin; \
    fi; \
    printf '%s\n' \
        '#!/usr/bin/env bash' \
        'set -euo pipefail' \
        '' \
        'odoo_script="${ODOO_SOURCE_BIN:-/usr/local/bin/odoo-source-bin}"' \
        'python_executable="${ODOO_WRAPPER_PYTHON:-/venv/bin/python}"' \
        '' \
        'if [[ ! -x "$odoo_script" ]]; then' \
        '  echo "Missing Odoo executable at ${odoo_script}" >&2' \
        '  exit 1' \
        'fi' \
        '' \
        'if [[ ! -x "$python_executable" ]]; then' \
        '  echo "Missing Python executable at ${python_executable}" >&2' \
        '  exit 1' \
        'fi' \
        '' \
        'exec "$python_executable" "$odoo_script" "$@"' \
        > /odoo/odoo-bin; \
    chmod +x /odoo/odoo-bin /usr/local/bin/odoo-source-bin

FROM ${ODOO_BASE_DEVTOOLS_IMAGE} AS base-devtools
USER root
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

COPY /docker/config /volumes/config
COPY /docker/scripts /volumes/scripts
COPY /addons /volumes/addons
COPY --from=addon_sources /extra_addons /opt/extra_addons
COPY /pyproject.toml /volumes/pyproject.toml
COPY /uv.lock /volumes/uv.lock

RUN mkdir -p /opt \
    && rm -rf /opt/project \
    && ln -s /volumes /opt/project

RUN set -eux; \
    if ! command -v uv >/dev/null 2>&1; then \
        curl -LsSf https://astral.sh/uv/install.sh | sh; \
        cp /root/.local/bin/uv* /usr/local/bin/; \
    fi

RUN set -eux; \
    if grep -q "ODOO_SOURCE_BIN" /odoo/odoo-bin; then \
        if [ ! -f /usr/local/bin/odoo-source-bin ]; then \
            echo "Missing /usr/local/bin/odoo-source-bin while /odoo/odoo-bin is already a wrapper" >&2; \
            exit 1; \
        fi; \
    else \
        cp /odoo/odoo-bin /usr/local/bin/odoo-source-bin; \
    fi; \
    printf '%s\n' \
        '#!/usr/bin/env bash' \
        'set -euo pipefail' \
        '' \
        'odoo_script="${ODOO_SOURCE_BIN:-/usr/local/bin/odoo-source-bin}"' \
        'python_executable="${ODOO_WRAPPER_PYTHON:-/venv/bin/python}"' \
        '' \
        'if [[ ! -x "$odoo_script" ]]; then' \
        '  echo "Missing Odoo executable at ${odoo_script}" >&2' \
        '  exit 1' \
        'fi' \
        '' \
        'if [[ ! -x "$python_executable" ]]; then' \
        '  echo "Missing Python executable at ${python_executable}" >&2' \
        '  exit 1' \
        'fi' \
        '' \
        'exec "$python_executable" "$odoo_script" "$@"' \
        > /odoo/odoo-bin; \
    chmod +x /odoo/odoo-bin /usr/local/bin/odoo-source-bin

FROM base-runtime AS runtime-common
ENV HOOK_SETUP_FILE=/volumes/scripts/hook_setup
RUN if [ -f "$HOOK_SETUP_FILE" ]; then cp "$HOOK_SETUP_FILE" /; else echo "hook_setup file not found in /volumes/scripts, skipping"; fi
RUN ln -sf /etc/ssl/certs/ca-certificates.crt /usr/lib/ssl/cert.pem
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

# Production build stage - only prod dependencies
FROM runtime-common AS production
WORKDIR /volumes/addons
RUN --mount=type=cache,target=/root/.cache/uv \
    /volumes/scripts/install_prod_requirements.sh
WORKDIR /
USER ubuntu

# Development build stage - prod + dev dependencies
FROM base-devtools AS development
WORKDIR /volumes/addons

ENV HOOK_SETUP_FILE=/volumes/scripts/hook_setup
RUN if [ -f "$HOOK_SETUP_FILE" ]; then cp "$HOOK_SETUP_FILE" /; else echo "hook_setup file not found in /volumes/scripts, skipping"; fi
RUN ln -sf /etc/ssl/certs/ca-certificates.crt /usr/lib/ssl/cert.pem
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

RUN --mount=type=cache,target=/root/.cache/uv \
    /volumes/scripts/install_dev_requirements.sh
USER ubuntu
