# Images

This directory owns the published foundation image families:

```text
runtime/  -> clean Odoo runtime image
builder/  -> build-only image that materializes sources, locks Python, and creates the venv
```

The Odoo Python runtime and the operating-system base are selected explicitly
per Odoo major version. Do not let one Odoo line inherit the baseline from a
previous line by inertia.

For Odoo 17, the selected operating-system base is Debian trixie and the
default runtime Python is Python 3.10. This is a deliberate Odoo 17 contract,
not a rule for Odoo 18 or later.

For Odoo 18 and later, define a new baseline before building images:

```text
Odoo major -> Debian release -> Python minor -> pinned base digest -> smoke tests
```

If the appropriate Python changes, use that Python by default for that Odoo
major. If the appropriate Debian release changes too, move the OS baseline for
that major as a documented platform decision. Do not keep Debian trixie or
Python 3.10 just because Odoo 17 used them.

The default for an image line is the latest specific `python:<minor>.*-slim-<debian>`
tag available when the line is defined, pinned by digest. Do not use moving
tags in `FROM`. The Dockerfile pins the actual base image by digest; the human
tag is only documentation.

## Odoo 17 Default Variant

The default Python 3.10 trixie base verified on 2026-05-11 is:

```text
Human reference: docker.io/library/python:3.10.20-slim-trixie
Digest:          sha256:3ff3599b60b92eeb304e6bd580b765c4e46f0290e687926bb37a078c74a181a1
Odoo Python:     /usr/local/bin/python3.10
Tag:             17.0-py310-trixie-r0001
```

Python 3.10 is accepted here as an Odoo 17 compatibility line for client or
provider modules that require Python 3.10-compatible runtimes. It is not a
long-term default for future Odoo majors. Python 3.10 reaches end of life in
October 2026, so this line must be revisited before then. Track that date from
the official Python version status:
https://devguide.python.org/versions/

## Odoo 17 Python Changes

For Odoo 17, the operating-system base is fixed to Debian trixie. If a future
Odoo 17 deployment needs another Python minor, build another Python-on-trixie
variant. Do not change the Debian release just because Python changes.

Changing Python is a release decision, not an ad hoc local build tweak. The
operator must:

1. Pick the most specific upstream Python tag for trixie, for example
   `python:3.11.15-slim-trixie`.
2. Resolve and pin the tag digest.
3. Override all Python-related runtime arguments together:
   `ODOO_BASE_IMAGE`, `ODOO_BASE_IMAGE_HUMAN_REF`, `ODOO_PYTHON`, and
   `ODOO_PYTHON_VERSION`.
4. Build the matching runtime and builder tags.
5. Rebuild the derived source-build image, refreshing `requirements.lock.txt`
   because the active Python markers may change.
6. Extract, review, and commit the regenerated lock.
7. Build the final image and run the smoke tests.

Do not publish or deploy a mixed variant where the runtime image, builder image,
and derived image were built with different Python minors.

In the current Odoo 17 line there is no expected need to move away from Python
3.10 when selected client/provider modules require it. Treat another Python
minor as an exception that must justify itself.

Build the runtime:

```bash
docker build \
  -f images/runtime/Dockerfile \
  -t local/oci-odoo:17.0-py310-trixie-r0001 \
  .
```

Then build the matching builder:

```bash
docker build \
  --build-arg ODOO_RUNTIME_IMAGE=local/oci-odoo:17.0-py310-trixie-r0001 \
  -f images/builder/Dockerfile \
  -t local/oci-odoo-builder:17.0-py310-trixie-r0001 \
  .
```

Build another Python-on-trixie variant only by overriding all four runtime args
together:

```bash
docker build \
  --build-arg ODOO_BASE_IMAGE=docker.io/library/python@sha256:a5b427ace4900267d93db34138e512325c6fa6af84ad5e4ed5f3b36258cc4142 \
  --build-arg ODOO_BASE_IMAGE_HUMAN_REF=docker.io/library/python:3.11.15-slim-trixie \
  --build-arg ODOO_PYTHON=/usr/local/bin/python3.11 \
  --build-arg ODOO_PYTHON_VERSION=3.11 \
  -f images/runtime/Dockerfile \
  -t local/oci-odoo:17.0-py311-trixie-r0001 \
  .
```

## Rules

- APT is for native/system packages.
- For Odoo 17, APT package names target Debian trixie. Do not add cross-Debian
  compatibility branches unless a future image line explicitly decides to
  support another Debian release.
- For Odoo 18 and later, choose the Debian release and Python minor again from
  that Odoo major's real requirements. The result may be another Debian release,
  another Python minor, or both.
- Python dependencies belong in the Odoo venv and are resolved from the
  derived image's `requirements.lock.txt`.
- Do not install Debian `python3-*` packages expecting them to feed Odoo.
- Runtime and builder tags must be built from the same Python variant.
- Every new Python/OS combination needs smoke tests before it becomes a
  supported tag.
