ARG ODOO_VERSION=18.0

FROM postgres:17-bullseye AS pg17

FROM alpine/git AS enterprise
ARG ODOO_ENTERPRISE_REPOSITORY
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
COPY --from=pg17 /usr/lib/postgresql/17/bin/psql       /usr/local/bin/psql
COPY --from=pg17 /usr/lib/postgresql/17/bin/pg_dump      /usr/local/bin/pg_dump

ARG PYTHON_VERSION
ENV DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      git \
      openssh-client \
      ripgrep \
      rsync \
    && rm -rf /var/lib/apt/lists/*

# Install uv for modern Python package management
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Make uv available for ubuntu user too
RUN cp /root/.local/bin/uv* /usr/local/bin/

# Use uv for faster package installations
RUN uv pip install --target=/opt/odoo-upgrade git+https://github.com/odoo/upgrade-util \
    && uv pip install --target=/opt/odoo-stubs git+https://github.com/odoo-ide/odoo-stubs@18.0

RUN PY_SITE="$(python3 -c "import site; print(site.getsitepackages()[0])")" \
    && echo "/odoo" > "${PY_SITE}/odoo_local.pth" \
    && echo "/volumes/enterprise" > "${PY_SITE}/odoo_enterprise.pth" \
    && echo "/opt/odoo-upgrade" > "${PY_SITE}/upgrade_utils.pth" \
    && echo "/opt/odoo-stubs" > "${PY_SITE}/odoostubs.pth"

COPY --from=enterprise /enterprise /volumes/enterprise
COPY /docker/config /volumes/config
COPY /docker/scripts /volumes/scripts
COPY /addons /volumes/addons
COPY --from=enterprise /addons /volumes/addons
COPY /pyproject.toml /volumes/pyproject.toml
COPY /uv.lock /volumes/uv.lock

RUN mkdir -p /opt && ln -sfn /volumes /opt/project

# Production build stage - only prod dependencies
FROM base AS production
WORKDIR /volumes/addons
RUN /volumes/scripts/install_prod_requirements.sh

# Common final steps
ENV HOOK_SETUP_FILE=/volumes/scripts/hook_setup
RUN if [ -f "$HOOK_SETUP_FILE" ]; then cp "$HOOK_SETUP_FILE" /; else echo "hook_setup file not found in /volumes/scripts, skipping"; fi

RUN ln -sf /etc/ssl/certs/ca-certificates.crt /usr/lib/ssl/cert.pem
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

WORKDIR /
USER ubuntu

# Development build stage - prod + dev dependencies
FROM base AS development
WORKDIR /volumes/addons
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      software-properties-common \
    && add-apt-repository -y ppa:xtradeb/apps \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
      chromium \
      fonts-liberation \
      libu2f-udev \
    && rm -rf /var/lib/apt/lists/*

# allow Odoo’s HttpCase to locate the browser
ENV CHROME_BIN=/usr/bin/chromium

RUN /volumes/scripts/install_dev_requirements.sh

# Apply development patches for --dev mode issues
COPY patches/fix_dev_mode_validation.patch /tmp/
RUN cd / && \
    patch -p0 < /tmp/fix_dev_mode_validation.patch && \
    rm /tmp/fix_dev_mode_validation.patch && \
    echo "✓ Applied --dev mode validation fix"

# Common final steps
ENV HOOK_SETUP_FILE=/volumes/scripts/hook_setup
RUN if [ -f "$HOOK_SETUP_FILE" ]; then cp "$HOOK_SETUP_FILE" /; else echo "hook_setup file not found in /volumes/scripts, skipping"; fi

RUN ln -sf /etc/ssl/certs/ca-certificates.crt /usr/lib/ssl/cert.pem
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

WORKDIR /
USER ubuntu
