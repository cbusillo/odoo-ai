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
