# syntax=docker/dockerfile:1.2
FROM alpine/git as enterprise

ARG ODOO_ENTERPRISE_REPOSITORY
ARG GITHUB_TOKEN
ARG ODOO_VERSION

RUN echo "Cloning Enterprise Addons from ${ODOO_ENTERPRISE_REPOSITORY} branch ${ODOO_VERSION}" && \
    if [[ -n "${ODOO_ENTERPRISE_REPOSITORY}" ]] ; then \
      git clone --branch ${ODOO_VERSION} --single-branch --depth 1 https://${GITHUB_TOKEN}@github.com/${ODOO_ENTERPRISE_REPOSITORY} /enterprise; \
    else \
      echo "ODOO_ENTERPRISE_REPOSITORY is empty; skipping clone."; \
      mkdir -p /enterprise; \
    fi

FROM ghcr.io/adomi-io/odoo:18.0 as odoo-base
USER root
ARG PYTHON_VERSION

RUN apt-get update && \
    apt-get install -y git openssh-client rsync && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-deps --target=/opt/odoo-cleanup odoo-addon-database-cleanup --extra-index-url https://wheelhouse.odoo-community.org/oca-simple/
RUN pip install --target=/opt/odoo-upgrade git+https://github.com/odoo/upgrade-util
RUN pip install --target=/opt/odoo-stubs git+https://github.com/odoo-ide/odoo-stubs@18.0



RUN echo "/odoo" > /venv/lib/python${PYTHON_VERSION}/site-packages/odoo_local.pth \
    && echo "/volumes/enterprise" > /venv/lib/python${PYTHON_VERSION}/site-packages/odoo_enterprise.pth \
    && echo "/opt/odoo-upgrade" > /venv/lib/python${PYTHON_VERSION}/site-packages/upgrade_utils.pth \
    && echo "/opt/odoo-cleanup" > /venv/lib/python${PYTHON_VERSION}/site-packages/database_cleanup.pth \
    && echo "/opt/odoo-stubs" > /venv/lib/python${PYTHON_VERSION}/site-packages/odoostubs.pth

COPY --from=enterprise /enterprise /volumes/enterprise
COPY /docker/config /volumes/config
COPY /docker/scripts /volumes/scripts
COPY /addons /volumes/addons

RUN mkdir -p /tmp/enterprise_stub/src && \
    printf "[project]\nname = \"odoo18-enterprise\"\nversion = \"18.0.0\"\n" \
        > /tmp/enterprise_stub/pyproject.toml && \
    echo "/volumes/enterprise" > /tmp/enterprise_stub/src/odoo_enterprise.pth && \
    pip install --no-build-isolation --no-deps /tmp/enterprise_stub && \
    rm -rf /tmp/enterprise_stub

ARG DEV_MODE=false

WORKDIR /volumes/addons

RUN /volumes/scripts/install_addon_requirements.sh
ENV HOOK_SETUP_FILE=/volumes/scripts/hook_setup
RUN if [ -f "$HOOK_SETUP_FILE" ]; then cp "$HOOK_SETUP_FILE" /; else echo "hook_setup file not found in /volumes/scrips, skipping"; fi

RUN ln -sf /etc/ssl/certs/ca-certificates.crt /usr/lib/ssl/cert.pem
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt


WORKDIR /
USER ubuntu