# syntax=docker/dockerfile:1.6
ARG ODOO_VERSION=19.0

FROM postgres:17-bullseye AS pg17

FROM alpine/git AS addon_sources
ARG ODOO_ADDON_REPOSITORIES
ARG GITHUB_TOKEN
ARG ODOO_VERSION
SHELL ["/bin/sh", "-euxc"]
COPY /docker/scripts/fetch_addons.sh /usr/local/bin/fetch_addons.sh
RUN chmod +x /usr/local/bin/fetch_addons.sh \
    && /usr/local/bin/fetch_addons.sh

FROM ghcr.io/adomi-io/odoo:${ODOO_VERSION} AS base
ARG ODOO_VERSION
USER root
# bring in PostgreSQL 17 client tools
COPY --from=pg17 /usr/lib/postgresql/17/bin/pg_restore /usr/local/bin/pg_restore
COPY --from=pg17 /usr/lib/postgresql/17/bin/pg_dump      /usr/local/bin/pg_dump

ARG PYTHON_VERSION
ENV DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update \
    && apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      git \
      openssh-client \
      ripgrep \
      rsync \
    && rm -rf /var/lib/apt/lists/*

# Install uv for modern Python package management
RUN rm -rf /venv && curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"
ENV UV_CACHE_DIR=/root/.cache/uv
ENV UV_PROJECT_ENVIRONMENT=/venv
RUN uv venv /venv --python $PYTHON_VERSION

# Make uv available for ubuntu user too
RUN cp /root/.local/bin/uv* /usr/local/bin/


COPY /docker/config /volumes/config
COPY /docker/scripts /volumes/scripts
COPY /addons /volumes/addons
COPY --from=addon_sources /extra_addons /opt/extra_addons
COPY patches/base /tmp/patches/base
RUN /volumes/scripts/apply_patches.sh /tmp/patches/base /opt/extra_addons --cleanup
COPY /pyproject.toml /volumes/pyproject.toml
COPY /uv.lock /volumes/uv.lock

RUN mkdir -p /opt && ln -sfn /volumes /opt/project

# Production build stage - only prod dependencies
FROM base AS production
WORKDIR /volumes/addons
RUN --mount=type=cache,target=/root/.cache/uv \
    /volumes/scripts/install_prod_requirements.sh

# Common final steps
ENV HOOK_SETUP_FILE=/volumes/scripts/hook_setup
RUN if [ -f "$HOOK_SETUP_FILE" ]; then cp "$HOOK_SETUP_FILE" /; else echo "hook_setup file not found in /volumes/scripts, skipping"; fi

RUN ln -sf /etc/ssl/certs/ca-certificates.crt /usr/lib/ssl/cert.pem
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

WORKDIR /
USER ubuntu

# Development build stage - prod + dev dependencies
FROM base AS development
ARG PYTHON_VERSION
ARG SITE_PACKAGES_PATH=/venv/lib/python${PYTHON_VERSION}/site-packages
ARG UBUNTU_CODENAME
WORKDIR /volumes/addons
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update \
    && apt-get install -y --no-install-recommends \
      ca-certificates curl gnupg lsb-release \
    && mkdir -p /usr/share/keyrings \
    && curl -fsSL "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x82BB6851C64F6880" \
      | gpg --dearmor -o /usr/share/keyrings/xtradeb-archive-keyring.gpg \
    && if [ -z "$UBUNTU_CODENAME" ]; then UBUNTU_CODENAME="$(lsb_release -cs)"; fi \
    && if [ -z "$UBUNTU_CODENAME" ]; then echo "Missing VERSION_CODENAME in /etc/os-release" >&2; exit 1; fi \
    && echo "deb [signed-by=/usr/share/keyrings/xtradeb-archive-keyring.gpg] https://ppa.launchpadcontent.net/xtradeb/apps/ubuntu ${UBUNTU_CODENAME} main" \
      > /etc/apt/sources.list.d/xtradeb-apps.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
      chromium fonts-liberation libu2f-udev \
    && rm -rf /var/lib/apt/lists/*

# allow Odoo’s HttpCase to locate the browser
ENV CHROME_BIN=/usr/bin/chromium

RUN --mount=type=cache,target=/root/.cache/uv \
    /volumes/scripts/install_dev_requirements.sh

# Ensure Odoo roots are discoverable by IDEs without shadowing stdlib.
RUN printf '/odoo\n' > "${SITE_PACKAGES_PATH}/odoo_local.pth" \
    && printf '/odoo/addons\n' > "${SITE_PACKAGES_PATH}/odoo_addons.pth" \
    && printf '/opt/extra_addons\n' > "${SITE_PACKAGES_PATH}/odoo_enterprise.pth" \
    && printf '/opt/extra_addons/odoo-enterprise-mirror\n' > "${SITE_PACKAGES_PATH}/odoo_enterprise_mirror.pth" \
    && printf '/opt/extra_addons/OpenUpgrade\n' > "${SITE_PACKAGES_PATH}/upgrade_utils.pth"

# Apply development patches for --dev mode issues
COPY patches/dev /tmp/patches/dev
WORKDIR /
RUN /volumes/scripts/apply_patches.sh /tmp/patches/dev / --cleanup

# Common final steps
ENV HOOK_SETUP_FILE=/volumes/scripts/hook_setup
RUN if [ -f "$HOOK_SETUP_FILE" ]; then cp "$HOOK_SETUP_FILE" /; else echo "hook_setup file not found in /volumes/scripts, skipping"; fi

RUN ln -sf /etc/ssl/certs/ca-certificates.crt /usr/lib/ssl/cert.pem
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

USER ubuntu
