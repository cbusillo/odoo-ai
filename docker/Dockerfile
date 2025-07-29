# syntax=docker/dockerfile:1.2
FROM postgres:17-bullseye AS pg17

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

FROM ghcr.io/adomi-io/odoo:18.0 as base
USER root
# bring in PostgreSQL 17 client tools
COPY --from=pg17 /usr/lib/postgresql/17/bin/pg_restore /usr/local/bin/pg_restore
COPY --from=pg17 /usr/lib/postgresql/17/bin/psql       /usr/local/bin/psql
COPY --from=pg17 /usr/lib/postgresql/17/bin/pg_dump      /usr/local/bin/pg_dump

ARG PYTHON_VERSION

RUN apt-get update && \
    apt-get install -y git openssh-client rsync software-properties-common curl && \
    add-apt-repository -y ppa:xtradeb/apps && \
    apt-get install -y --no-install-recommends chromium fonts-liberation libu2f-udev && \
    rm -rf /var/lib/apt/lists/*

# Install uv for modern Python package management
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Make uv available for ubuntu user too
RUN cp /root/.local/bin/uv* /usr/local/bin/

# allow Odoo’s HttpCase to locate the browser
ENV CHROME_BIN=/usr/bin/chromium

# Use uv for faster package installations
RUN uv pip install --no-deps --target=/opt/odoo-cleanup odoo-addon-database-cleanup --extra-index-url https://wheelhouse.odoo-community.org/oca-simple/
RUN uv pip install --target=/opt/odoo-upgrade git+https://github.com/odoo/upgrade-util
RUN uv pip install --target=/opt/odoo-stubs git+https://github.com/odoo-ide/odoo-stubs@18.0

RUN echo "/odoo" > /venv/lib/python${PYTHON_VERSION}/site-packages/odoo_local.pth \
    && echo "/volumes/enterprise" > /venv/lib/python${PYTHON_VERSION}/site-packages/odoo_enterprise.pth \
    && echo "/opt/odoo-upgrade" > /venv/lib/python${PYTHON_VERSION}/site-packages/upgrade_utils.pth \
    && echo "/opt/odoo-cleanup" > /venv/lib/python${PYTHON_VERSION}/site-packages/database_cleanup.pth \
    && echo "/opt/odoo-stubs" > /venv/lib/python${PYTHON_VERSION}/site-packages/odoostubs.pth

COPY --from=enterprise /enterprise /volumes/enterprise
COPY /docker/config /volumes/config
COPY /docker/scripts /volumes/scripts
COPY /addons /volumes/addons
COPY /pyproject.toml /volumes/pyproject.toml

RUN mkdir -p /tmp/enterprise_stub/src && \
    printf "[project]\nname = \"odoo18-enterprise\"\nversion = \"18.0.0\"\n" \
        > /tmp/enterprise_stub/pyproject.toml && \
    echo "/volumes/enterprise" > /tmp/enterprise_stub/src/odoo_enterprise.pth && \
    pip install --no-build-isolation --no-deps /tmp/enterprise_stub && \
    rm -rf /tmp/enterprise_stub

# Production build stage - only prod dependencies
FROM base AS production
WORKDIR /volumes/addons
RUN /volumes/scripts/install_prod_requirements.sh

# Common final steps
ENV HOOK_SETUP_FILE=/volumes/scripts/hook_setup
RUN if [ -f "$HOOK_SETUP_FILE" ]; then cp "$HOOK_SETUP_FILE" /; else echo "hook_setup file not found in /volumes/scrips, skipping"; fi

RUN ln -sf /etc/ssl/certs/ca-certificates.crt /usr/lib/ssl/cert.pem
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

WORKDIR /
USER ubuntu

# Development build stage - prod + dev dependencies
FROM base AS development
WORKDIR /volumes/addons
RUN /volumes/scripts/install_dev_requirements.sh

# Apply development patches for --dev mode issues
COPY patches/fix_dev_mode_validation.patch /tmp/
RUN cd / && \
    patch -p0 < /tmp/fix_dev_mode_validation.patch && \
    rm /tmp/fix_dev_mode_validation.patch && \
    echo "✓ Applied --dev mode validation fix"

# Common final steps
ENV HOOK_SETUP_FILE=/volumes/scripts/hook_setup
RUN if [ -f "$HOOK_SETUP_FILE" ]; then cp "$HOOK_SETUP_FILE" /; else echo "hook_setup file not found in /volumes/scrips, skipping"; fi

RUN ln -sf /etc/ssl/certs/ca-certificates.crt /usr/lib/ssl/cert.pem
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

WORKDIR /
USER ubuntu