# syntax=docker/dockerfile:1.7
# SPDX-FileCopyrightText: 2026 NuoBiT Solutions, S.L.
# SPDX-License-Identifier: Apache-2.0

# Default base image selected on 2026-05-11:
#   docker.io/library/python:3.10.20-slim-trixie
#
# This tag is intentionally NOT used in FROM because upstream tags are mutable:
# the upstream registry may retarget this tag to a different digest at any time.
# Docker documents this under "Pin base image versions":
# https://docs.docker.com/develop/develop-images/dockerfile_best-practices/#pin-base-image-versions
#
# The Odoo Python runtime is deliberately selected through this base image,
# not inherited from the Debian release. For Odoo 17, Debian is fixed to
# trixie; override ODOO_BASE_IMAGE, ODOO_PYTHON, and ODOO_PYTHON_VERSION
# together only to build another Python-on-trixie supported variant.
ARG ODOO_BASE_IMAGE=docker.io/library/python@sha256:3ff3599b60b92eeb304e6bd580b765c4e46f0290e687926bb37a078c74a181a1
FROM ${ODOO_BASE_IMAGE}

ARG ODOO_BASE_IMAGE
ARG ODOO_BASE_IMAGE_HUMAN_REF=docker.io/library/python:3.10.20-slim-trixie
ARG ODOO_PYTHON=/usr/local/bin/python3.10
ARG ODOO_PYTHON_VERSION=3.10

LABEL org.opencontainers.image.title="oci-odoo"
LABEL org.opencontainers.image.description="Reusable Odoo OCI runtime foundation"
LABEL org.opencontainers.image.source="https://github.com/nuobit/oci-odoo"
LABEL org.opencontainers.image.vendor="NuoBiT Solutions, S.L."
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.base.name="${ODOO_BASE_IMAGE_HUMAN_REF}"
LABEL org.opencontainers.image.python.version="${ODOO_PYTHON_VERSION}"

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    ODOO_HOME=/opt/odoo \
    ODOO_SRC=/opt/odoo/src \
    ODOO_BIN=/opt/odoo/src/odoo/odoo-bin \
    ODOO_ADDONS_ROOT=/opt/odoo/src/addons \
    ODOO_VENV=/opt/odoo/venv \
    ODOO_PYTHON=${ODOO_PYTHON} \
    ODOO_PYTHON_VERSION=${ODOO_PYTHON_VERSION} \
    ODOO_RC=/etc/odoo/odoo.conf \
    ODOO_DATA_DIR=/var/lib/odoo \
    PATH=/opt/odoo/venv/bin:$PATH

ARG TARGETARCH
ARG WKHTMLTOX_VERSION=0.12.6.1-3
ARG WKHTMLTOX_AMD64_SHA256=98ba0d157b50d36f23bd0dedf4c0aa28c7b0c50fcdcdc54aa5b6bbba81a3941d

USER root

RUN groupadd --gid 1000 odoo \
    && useradd --uid 1000 --gid odoo --home-dir "${ODOO_HOME}" --create-home --shell /bin/bash odoo \
    && mkdir -p "${ODOO_SRC}" "${ODOO_ADDONS_ROOT}" "${ODOO_DATA_DIR}" /etc/odoo /run/odoo /var/log/odoo

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        fonts-noto-cjk \
        libldap2 \
        libmagic1 \
        libpq5 \
        libsasl2-2 \
        node-less \
        npm \
        postgresql-client \
        xz-utils \
    && npm install -g rtlcss \
    && arch="${TARGETARCH:-$(dpkg --print-architecture)}" \
    && case "${arch}" in \
        amd64) wkhtmltox_arch="amd64"; wkhtmltox_sha256="${WKHTMLTOX_AMD64_SHA256}" ;; \
        *) echo "Unsupported wkhtmltox architecture for this scaffold: ${arch}" >&2; exit 1 ;; \
    esac \
    && curl -fsSLo /tmp/wkhtmltox.deb \
        "https://github.com/wkhtmltopdf/packaging/releases/download/${WKHTMLTOX_VERSION}/wkhtmltox_${WKHTMLTOX_VERSION}.bookworm_${wkhtmltox_arch}.deb" \
    && echo "${wkhtmltox_sha256}  /tmp/wkhtmltox.deb" | sha256sum -c - \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends /tmp/wkhtmltox.deb \
    && "${ODOO_PYTHON}" -c 'import sys; expected = sys.argv[1]; actual = f"{sys.version_info.major}.{sys.version_info.minor}"; sys.exit(0 if actual == expected else f"Expected Python {expected}, got {actual}")' "${ODOO_PYTHON_VERSION}" \
    && "${ODOO_PYTHON}" -m venv "${ODOO_VENV}" \
    && DEBIAN_FRONTEND=noninteractive apt-get purge -y --auto-remove \
        curl \
        npm \
        xz-utils \
    && rm -rf /var/lib/apt/lists/* /tmp/wkhtmltox.deb /root/.npm \
    && chown -R odoo:odoo "${ODOO_HOME}" "${ODOO_DATA_DIR}" /etc/odoo /run/odoo /var/log/odoo \
    && chmod 0700 /run/odoo

COPY images/runtime/scripts/odoo-run /usr/local/bin/odoo-run
COPY images/runtime/scripts/odoo-update /usr/local/bin/odoo-update
COPY images/runtime/scripts/odoo-shell /usr/local/bin/odoo-shell

RUN chmod 0755 /usr/local/bin/odoo-run /usr/local/bin/odoo-update /usr/local/bin/odoo-shell

VOLUME ["/var/lib/odoo"]
EXPOSE 8069 8071 8072

USER odoo

ENTRYPOINT ["odoo-run"]
