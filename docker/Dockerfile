# syntax=docker/dockerfile:1.6
ARG ODOO_VERSION=19.0
ARG ODOO_BASE_RUNTIME_IMAGE=ghcr.io/cbusillo/odoo-enterprise-docker:19.0-runtime
ARG ODOO_BASE_DEVTOOLS_IMAGE=ghcr.io/cbusillo/odoo-enterprise-docker:19.0-devtools
ARG ODOO_ADDON_REPOSITORIES
ARG ODOO_PYTHON_SYNC_SKIP_ADDONS

FROM ${ODOO_BASE_RUNTIME_IMAGE} AS addon-sources
ARG ODOO_ADDON_REPOSITORIES
USER root
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN --mount=type=secret,id=github_token \
    GITHUB_TOKEN="$(cat /run/secrets/github_token 2>/dev/null || true)" \
    ODOO_ADDON_REPOSITORIES="${ODOO_ADDON_REPOSITORIES}" \
    /usr/local/bin/odoo-fetch-addons.sh

FROM ${ODOO_BASE_RUNTIME_IMAGE} AS base-runtime
ARG ODOO_ADDON_REPOSITORIES
ARG ODOO_PYTHON_SYNC_SKIP_ADDONS
USER root
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

COPY /platform/config /volumes/config
COPY /docker/scripts /volumes/scripts
COPY /addons /volumes/addons
COPY --from=addon-sources --chown=ubuntu:ubuntu /opt/extra_addons /opt/extra_addons
COPY /pyproject.toml /volumes/pyproject.toml
COPY /uv.lock /volumes/uv.lock

RUN mkdir -p /opt \
    && rm -rf /opt/project \
    && ln -s /volumes /opt/project

FROM ${ODOO_BASE_DEVTOOLS_IMAGE} AS base-devtools
ARG ODOO_ADDON_REPOSITORIES
ARG ODOO_PYTHON_SYNC_SKIP_ADDONS
USER root
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

COPY /platform/config /volumes/config
COPY /docker/scripts /volumes/scripts
COPY /addons /volumes/addons
COPY --from=addon-sources --chown=ubuntu:ubuntu /opt/extra_addons /opt/extra_addons
COPY /pyproject.toml /volumes/pyproject.toml
COPY /uv.lock /volumes/uv.lock

RUN mkdir -p /opt \
    && rm -rf /opt/project \
    && ln -s /volumes /opt/project

FROM base-runtime AS runtime-common
FROM runtime-common AS production
WORKDIR /opt/project
RUN --mount=type=cache,target=/home/ubuntu/.cache/uv,uid=1000,gid=1000,sharing=locked \
	ODOO_PYTHON_SYNC_SKIP_ADDONS="${ODOO_PYTHON_SYNC_SKIP_ADDONS}" /usr/local/bin/odoo-python-sync.sh prod
RUN if [[ ",${ODOO_ADDON_REPOSITORIES}," == *,OCA/OpenUpgrade@* ]] || [[ ",${ODOO_ADDON_REPOSITORIES}," == *,OCA/OpenUpgrade,* ]]; then \
		uv pip install --python /venv/bin/python openupgradelib==3.12.0; \
	fi
WORKDIR /
USER ubuntu

FROM base-devtools AS development
WORKDIR /opt/project

RUN --mount=type=cache,target=/home/ubuntu/.cache/uv,uid=1000,gid=1000,sharing=locked \
	ODOO_PYTHON_SYNC_SKIP_ADDONS="${ODOO_PYTHON_SYNC_SKIP_ADDONS}" /usr/local/bin/odoo-python-sync.sh dev
RUN if [[ ",${ODOO_ADDON_REPOSITORIES}," == *,OCA/OpenUpgrade@* ]] || [[ ",${ODOO_ADDON_REPOSITORIES}," == *,OCA/OpenUpgrade,* ]]; then \
		uv pip install --python /venv/bin/python openupgradelib==3.12.0; \
	fi
USER ubuntu
