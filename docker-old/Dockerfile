# syntax=docker/dockerfile:1.2
FROM alpine/git as enterprise

ARG ODOO_ENTERPRISE_REPOSITORY
ARG GITHUB_TOKEN
ARG ODOO_VERSION

RUN if [[ -n "${ODOO_ENTERPRISE_REPOSITORY}" ]] ; then \
      git clone --branch ${ODOO_VERSION} --single-branch --depth 1 https://${GITHUB_TOKEN}@github.com/${ODOO_ENTERPRISE_REPOSITORY} /enterprise; \
    else \
      echo "ODOO_ENTERPRISE_REPOSITORY is empty; skipping clone."; \
      mkdir -p /enterprise; \
    fi

FROM ghcr.io/adomi-io/odoo:18.0 as odoo-base
USER root

RUN apt-get update && \
    apt-get install -y git openssh-client rsync && \
    rm -rf /var/lib/apt/lists/*

ARG PYTHON_VERSION
RUN pip install --target=/opt/odoo-upgrade git+https://github.com/odoo/upgrade-util
RUN echo "/odoo" > /venv/lib/python${PYTHON_VERSION}/site-packages/odoo_local.pth \
    && echo "/volume/enterprise" > /venv/lib/python${PYTHON_VERSION}/site-packages/odoo_enterprise.pth \
    && echo "/opt/odoo-upgrade" > /venv/lib/python${PYTHON_VERSION}/site-packages/upgrade_utils.pth

COPY --from=enterprise /enterprise /volumes/enterprise
COPY docker/config/odoo.conf /volumes/config/odoo.conf
COPY docker/scripts /volumes/scripts
COPY addons /volumes/addons

ARG DEV_MODE=false

WORKDIR /volumes/addons

RUN /volumes/scripts/install_addon_requirements.sh
ENV HOOK_SETUP_FILE=/volumes/scripts/hook_setup
RUN if [ -f "$HOOK_SETUP_FILE" ]; then cp "$HOOK_SETUP_FILE" /; else echo "hook_setup file not found in /volumes/scrips, skipping"; fi

WORKDIR /
USER ubuntu