# syntax=docker/dockerfile:1.7
# SPDX-FileCopyrightText: 2026 NuoBiT Solutions, S.L.
# SPDX-License-Identifier: Apache-2.0

ARG ODOO_RUNTIME_IMAGE=local/oci-odoo:17.0-py310-trixie-r0001
FROM ${ODOO_RUNTIME_IMAGE}

LABEL org.opencontainers.image.title="oci-odoo-builder"
LABEL org.opencontainers.image.description="Reusable Odoo OCI build foundation"
LABEL org.opencontainers.image.vendor="NuoBiT Solutions, S.L."
LABEL org.opencontainers.image.licenses="Apache-2.0"

ENV ODOO_BUILDER_HOME=/opt/odoo-builder \
    ODOO_BUILDER_VENV=/opt/odoo-builder/venv \
    PATH=/opt/odoo-builder/venv/bin:$PATH

USER root

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        build-essential \
        git \
        libldap2-dev \
        libpq-dev \
        libsasl2-dev \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p "${ODOO_BUILDER_HOME}" \
    && "${ODOO_PYTHON}" -m venv "${ODOO_BUILDER_VENV}" \
    && "${ODOO_BUILDER_VENV}/bin/pip" install --no-cache-dir \
        git-aggregator==4.1 \
        packaging==26.2 \
        pip-requirements-parser==32.0.1 \
        PyYAML==6.0.2 \
        pip-tools==7.4.1

COPY images/builder/scripts/odoo-build-image /usr/local/bin/odoo-build-image
COPY images/builder/scripts/odoo-build-python-env /usr/local/bin/odoo-build-python-env
COPY images/builder/scripts/odoo-generate-addons-path /usr/local/bin/odoo-generate-addons-path
COPY images/builder/scripts/odoo-normalize-requirements /usr/local/bin/odoo-normalize-requirements

RUN chmod 0755 \
    /usr/local/bin/odoo-build-image \
    /usr/local/bin/odoo-build-python-env \
    /usr/local/bin/odoo-generate-addons-path \
    /usr/local/bin/odoo-normalize-requirements

WORKDIR /opt/odoo/src
