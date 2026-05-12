# syntax=docker/dockerfile:1.7
# SPDX-FileCopyrightText: 2026 NuoBiT Solutions, S.L.
# SPDX-License-Identifier: Apache-2.0

# Final deployable image.
# Build Dockerfile.source-build first, then pass that local image here.
ARG ODOO_RUNTIME_IMAGE=ghcr.io/nuobit/oci-odoo:17.0-py310-trixie-r0001
ARG ODOO_SOURCE_BUILD_IMAGE=local/oci-odoo-derived-source-build:17.0-py310-trixie-r0001

FROM ${ODOO_SOURCE_BUILD_IMAGE} AS source-build

FROM ${ODOO_RUNTIME_IMAGE}

USER root

COPY system-runtime-packages.txt /tmp/system-runtime-packages.txt

RUN set -eu; \
    packages="$(sed -e 's/#.*//' -e '/^[[:space:]]*$/d' /tmp/system-runtime-packages.txt)"; \
    if [ -n "${packages}" ]; then \
        apt-get update; \
        DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ${packages}; \
        rm -rf /var/lib/apt/lists/*; \
    fi; \
    rm -f /tmp/system-runtime-packages.txt

COPY --from=source-build --chown=odoo:odoo /opt/odoo/src/ /opt/odoo/src/
COPY --from=source-build --chown=odoo:odoo /opt/odoo/venv/ /opt/odoo/venv/
COPY --from=source-build --chown=odoo:odoo /etc/odoo/addons_path /etc/odoo/addons_path

USER odoo
