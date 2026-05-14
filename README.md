# Odyssey (`oci-odoo`)

Reproducible, immutable OCI releases for industrialized Odoo deployments.

Odyssey is the project name for `oci-odoo`, a reusable image and tooling system
for building reproducible Odoo OCI releases. This repository builds reusable
Odoo OCI image foundations for turning Odoo deployments into locked, reviewable,
rebuildable artifacts. The goal is to move Odoo delivery away from mutable
server state and toward explicit Git inputs, pinned locks, controlled refreshes,
and final images that contain the exact source tree and Python environment for a
release.

## Why This Exists

Many Odoo deployments work by convention: pull some repositories, install some
Python packages, patch server state, restart, and hope the next rebuild behaves
the same way. That is fast for manual operations, but weak for production
change control.

Odyssey makes the release contract explicit:

- source repositories are declared and then locked in `repos.lock.yaml`;
- Python dependencies are installed from `requirements.lock.txt` unless a
  refresh is explicitly requested;
- OCA, customer, Enterprise, and third-party addon sources are materialized once
  during the derived-image build flow;
- the generated addon path is baked into the final image;
- build-only tools stay out of the runtime image;
- system build/runtime packages are declared separately;
- runtime secrets are injected at container start, not stored in images or Git.

To our knowledge, `oci-odoo` is one of the few open-source Odoo
containerization projects focused explicitly on end-to-end reproducibility and
immutable deployable images. That claim is implemented through pinned
base-image digests, source locks, Python locks, conditional refresh semantics,
separate builder/runtime images, and deployment images that package the exact
Odoo source tree, virtualenv, and generated addon path for a release.

## What This Repository Builds

This repository is not a deployable Odoo image by itself. It builds the reusable
foundation images used by deployable Odoo image repositories. A deployment image
adds the exact Enterprise/OCA/customer/provider/third-party addon source
selection on top of these foundations.

The repository is versioned per Odoo line. For Odoo 17 work, use branch `17.0`.
The same branch publishes both foundation images:

```text
ghcr.io/nuobit/oci-odoo:17.0-py310-trixie-rNNNN
ghcr.io/nuobit/oci-odoo-builder:17.0-py310-trixie-rNNNN
```

## Kubernetes-ready, OCI-first

Odyssey is not tied to Kubernetes, but it includes a Kubernetes deployment
scaffold for production-style Odoo deployments. The same immutable image can run
under Kubernetes, Docker, Podman, Docker Compose, CI, or any OCI-capable
runtime.

The Kubernetes scaffold exists to make the production contract explicit: stable
Services select versioned Deployments, non-secret Odoo configuration lives in
ConfigMaps, credentials are mounted as Secret files, filestore data lives in
PVCs, registry access uses `imagePullSecrets`, and generated runtime config
stays under `/run/odoo` as ephemeral process state. Addon code belongs in the
image, not in mutable runtime volumes.

## Technical Map

The high-level implementation is:

```text
runtime image
  clean Odoo runtime base, pinned OS/Python digest, runtime wrappers

builder image
  git aggregation, lock tooling, Python environment build, addon path generation

derived image scaffold
  starting point for concrete deployable images

deployment scaffold
  examples for running a produced image in k8s or another OCI-capable runtime
```

The deep technical contract is documented below and in the subdirectory README
files. The README starts with the project goal, then keeps the exact build and
runtime rules in the same place so the repository remains self-contained.

## Repository Layout

```text
images/runtime/
  Dockerfile
  README.md
  scripts/
    odoo-run
    odoo-init
    odoo-update
    odoo-shell

images/builder/
  Dockerfile
  README.md
  scripts/
    odoo-build-image
    odoo-build-python-env
    odoo-generate-addons-path
    odoo-normalize-requirements

images/README.md
  image-family policy, OS/Python baseline, and Python variant rules

tools/
  README.md
  lock-repos
  update-base-image-digest

derived-image-scaffold/
  Dockerfile
  README.md
  repos.yaml
  requirements.in
  requirements-constraints.in
  system-build-packages.txt
  system-runtime-packages.txt
  .gitignore
  .dockerignore
```

`images/runtime` owns the clean runtime image published as:

```text
ghcr.io/nuobit/oci-odoo:<version>
```

`images/builder` owns the build-only image published as:

```text
ghcr.io/nuobit/oci-odoo-builder:<version>
```

`tools` are repository/operator/CI utilities. They are not owned by either
published image and are not copied into production runtime containers by
default.

`derived-image-scaffold` is scaffolding for new derived image repositories. It
is not runtime content and not builder-image content.

The locking/generation logic belongs here, not in each deployment image
repository:

```text
tools/lock-repos                         -> generates repos.lock.yaml
images/builder/scripts/odoo-build-image  -> single source-build execution for a derived image release
images/builder/scripts/odoo-generate-addons-path
  -> generates /etc/odoo/addons_path from repos.lock.yaml + materialized source tree
```

Deployment repositories version the generated lock files because they define the
exact release, but they should not reimplement the lock algorithms. The Python
lock must be generated during the same source-build execution that materializes
the source tree; do not run a separate requirements-lock command that executes
`gitaggregate` a second time.

## Image Contract

- Artifact format: OCI container image.
- Initial builder: `docker buildx build`.
- Runtime build file: `images/runtime/Dockerfile`.
- Builder build file: `images/builder/Dockerfile`.
- Runtime OS/Python base: selected per Odoo major version and pinned by digest,
  not by mutable upstream tag. For Odoo 17, the default is Debian trixie with
  Python 3.10.
- Published tags owned by us include the Odoo major, Python minor, Debian
  release, and release counter, for example `17.0-py310-trixie-r0001`.

Both images should be released with the same version tag when they are part of
the same runtime contract:

```text
ghcr.io/nuobit/oci-odoo:17.0-py310-trixie-r0001
ghcr.io/nuobit/oci-odoo-builder:17.0-py310-trixie-r0001
```

Publish GHCR images with OCI index annotations, not only Dockerfile labels.
GHCR tags published by current Docker/BuildKit flows are OCI indexes. In a
2026-05-13 controlled test, a fresh package with
`org.opencontainers.image.source` only as an image label was not automatically
linked to its repository; the same package linked correctly when the source was
present as an `index` annotation.

Use this pattern for each published image:

```bash
gh auth refresh -h github.com -s read:packages -s write:packages
gh auth token | docker login ghcr.io -u <github-user> --password-stdin

GHCR_REPO="ghcr.io/<owner>/<image>"
GHCR_TAG="17.0-py310-trixie-r0001"
GHCR_IMAGE="${GHCR_REPO}:${GHCR_TAG}"
LOCAL_IMAGE="local/<image>:${GHCR_TAG}"
OCI_SOURCE="https://github.com/<owner>/<repo>"
OCI_DESCRIPTION="<short image description>"

docker tag "$LOCAL_IMAGE" "$GHCR_IMAGE"
docker push "$GHCR_IMAGE"

GHCR_DIGEST="$(docker buildx imagetools inspect "$GHCR_IMAGE" | awk '/^Digest:/ {print $2; exit}')"

docker buildx imagetools create \
  --annotation "index:org.opencontainers.image.source=${OCI_SOURCE}" \
  --annotation "index:org.opencontainers.image.description=${OCI_DESCRIPTION}" \
  --tag "$GHCR_IMAGE" \
  "${GHCR_REPO}@${GHCR_DIGEST}"
```

`gh auth` and Docker registry authentication are separate. If `docker push`
reports that the token does not match the expected scopes while `gh auth status`
shows `write:packages`, refresh Docker's GHCR login with the `gh auth token |
docker login ... --password-stdin` line above and retry. Do not inspect Docker's
credential file while debugging; it may contain live registry credentials.

Concrete foundation values:

```text
ghcr.io/nuobit/oci-odoo
  source:      https://github.com/nuobit/oci-odoo
  description: Reusable Odoo OCI runtime foundation

ghcr.io/nuobit/oci-odoo-builder
  source:      https://github.com/nuobit/oci-odoo
  description: Reusable Odoo OCI build foundation
```

For production Kubernetes deployments built from this project, use both a
meaningful release tag and the resolved digest in manifests:

```text
ghcr.io/<client-org>/<image>:17.0-py310-trixie-r0002@sha256:<digest>
```

The tag is the human release name. The digest is the immutable artifact
identity. Project-owned tags must still be treated as immutable and never
rewritten; digest-pinned manifests add a second protection layer against human
error, CI mistakes, accidental republish, and future process drift.

After first publication, verify the GitHub package settings in the UI:

```text
Package -> Package settings

Repository link:
  must point to the source repository

Inherited access:
  enable "Inherit access from source repository"

Visibility:
  foundation images such as nuobit/oci-odoo and nuobit/oci-odoo-builder:
    set package visibility to Public when anonymous pulls should work

  client deployable images:
    keep package visibility Private
```

Important: GHCR may create a package as private even when it is linked to a
public repository. Public repository, repository link, inherited access, and
package visibility are separate settings. Changing a package to Public is a
manual UI action and GitHub warns it cannot be made private again.

If the inherited-access panel shows `0 members`, that does not mean inheritance
is broken. It means there are no direct package-level member grants listed
there; effective access comes from the linked source repository.

## Upstream Base Policy

External upstream tags are not trusted as immutable. The Dockerfile records the
human tag observed when selecting the base, but `FROM` uses the digest directly.
The tag/digest relation in the comment is only an observation at selection time;
it is not a guarantee that the tag will keep pointing to that digest.

This follows Docker's own guidance in
[Pin base image versions](https://docs.docker.com/develop/develop-images/dockerfile_best-practices/#pin-base-image-versions):
image tags are mutable, while a digest pins the exact image version.

To update the runtime base digest, run:

```bash
bash tools/update-base-image-digest
```

Review the resulting `images/runtime/Dockerfile` change in a dedicated
PR/commit. Do not mix a base refresh with unrelated runtime or client changes.

For Odoo 17, the default human reference is the latest selected specific
`docker.io/library/python:3.10.*-slim-trixie` tag, which is more informative
than a moving alias such as `3.10-slim` or `trixie`. The update tool is generic
around the base-image concept, but the current resolver is explicitly for
Docker Hub:

```bash
BASE_IMAGE_REPOSITORY=library/python BASE_IMAGE_TAG=3.10.20-slim-trixie bash tools/update-base-image-digest
```

Docker Hub's human registry name `docker.io`, API endpoint
`registry-1.docker.io`, auth endpoint `auth.docker.io`, and `/v2/...` manifest
path are one coupled implementation. If a future registry is needed, add a
dedicated resolver/mode instead of stretching this script into a half-generic
URL builder.

For Odoo 18 and later, do not reuse the Odoo 17 base automatically. Define the
major-version baseline first:

```text
Odoo major -> Debian release -> Python minor -> pinned base digest -> smoke tests
```

If the correct Python or operating-system base changes for that major, the
image line changes with it.

For Odoo 17 specifically, Debian trixie is fixed. If another Python minor is
ever needed inside the Odoo 17 line, create a new Python-on-trixie variant
instead of changing the OS base. That means overriding the base Python image,
human reference, interpreter path, and Python version together; rebuilding both
runtime and builder; refreshing the derived `requirements.lock.txt`; and
running smoke tests before publishing. The normal Odoo 17 baseline is Python
3.10 because Odoo 17 works with it and some client/provider modules may require
Python 3.10-compatible runtimes.

## What Belongs Here

- Runtime image:
  - common runtime conventions;
- generic scripts such as `odoo-run`, `odoo-init`, `odoo-update`, and
  `odoo-shell`;
  - shared runtime dependencies that are truly generic;
  - generic non-secret configuration conventions;
  - the Python virtual environment used by deployment images to install Odoo
    and addon runtime requirements.
- Builder image:
  - build-only tools such as `git` and `git-aggregator`;
  - Python lock tooling such as `pip-tools`;
  - high-level build commands such as `odoo-build-image`;
  - Python virtualenv/lock helper such as `odoo-build-python-env`, called by
    `odoo-build-image` after sources already exist;
  - addon path generation such as `odoo-generate-addons-path`;
  - requirement normalization such as `odoo-normalize-requirements`, called
    from `odoo-build-python-env` inside the single derived source-build workflow;
  - future build-only dependencies when they are genuinely needed.
- Repository-level tools:
  - source-locking and base-image maintenance helpers.
- Derived-image scaffold:
  - `derived-image-scaffold/Dockerfile`;
  - `derived-image-scaffold/repos.yaml`;
  - `derived-image-scaffold/requirements.in`;
  - `derived-image-scaffold/requirements-constraints.in`;
  - `derived-image-scaffold/requirements-overrides.in`;
  - `derived-image-scaffold/requirements.lock.txt` bootstrap placeholder.
  - `derived-image-scaffold/system-build-packages.txt`;
  - `derived-image-scaffold/system-runtime-packages.txt`.

The runtime base image does not contain Odoo source and does not inherit the
official Odoo `/entrypoint.sh`. Deployment images add Odoo source and selected
addons on top of this runtime foundation.

The builder image exists because build tools must not leak into the final image
that Docker, Podman, containerd, Kubernetes, Docker Compose, CI, or another
OCI-capable runtime runs. This follows Docker's multi-stage build pattern: use
one stage for build/composition and copy only the final artifacts into a clean
runtime stage.

Deployment image workflows should call the builder's high-level API, not
duplicate the implementation details. The authoritative contract is:

```text
builder image build:
  builds the toolbox image only; it does not run gitaggregate and does not know
  any client repos.

derived image release workflow:
  reads repos.lock.yaml, requirements*.in, and requirements.lock.txt;
  builds one temporary source-build image using oci-odoo-builder;
  executes gitaggregate exactly once;
  uses requirements.lock.txt as-is, or refreshes it only when explicitly requested;
  creates /opt/odoo/src and /opt/odoo/venv;
  generates /etc/odoo/addons_path from repos.lock.yaml and the materialized tree;
  keeps the refreshed lock in the temporary source-build image for extraction;
  packages /opt/odoo/src and /opt/odoo/venv into the final runtime image;
  packages /etc/odoo/addons_path into the final runtime image;
  does not copy requirements.lock.txt into the final runtime image.
```

`addons_path` generation has a strict ownership split:

```text
repos.yaml       -> operator intent: which repositories should exist
repos.lock.yaml  -> exact pinned repositories/revisions
/opt/odoo/src    -> clean materialized source tree created from the lock
/etc/odoo/addons_path -> generated build artifact consumed by odoo-run
```

The generator validates that every locked repository materialized in the
expected location. A locked repository with no detectable Odoo addon root is
allowed and its repository path is still included in `/etc/odoo/addons_path`.
This is useful for deployment repositories that should already be part of the
lock even before they contain their first module. The materialized filesystem is
validation/build output, not a second source of truth.

Removing a repo from `repos.yaml` and regenerating the lock must remove it from the next
clean image and from `/etc/odoo/addons_path`.

Odoo 17 only creates its two default addon paths when `addons_path` is empty or
`None`. If a custom value is supplied, Odoo normalizes exactly that value and
does not prepend defaults. Later module loading ensures the core path
`odoo/odoo/addons` is present in `odoo.addons.__path__`, but it does not
similarly guarantee the top-level `odoo/addons` path. For that reason,
`odoo-generate-addons-path` must include both Odoo roots explicitly when the
Odoo repo appears:

```text
/opt/odoo/src/odoo/odoo/addons
/opt/odoo/src/odoo/addons
```

Odoo also appends `data_dir/addons/<series>` to the runtime
`odoo.addons.__path__` when that path is readable; with the default data
directory this is `/var/lib/odoo/addons/17.0` for Odoo 17. This path is outside
the image source model and must not be used for deployment code. In Kubernetes
it normally sits under the filestore/data PVC; in Docker/Podman it may be a
volume-mounted data directory. Putting addons there would make code mutable
outside the immutable image.

The generator preserves deterministic `repos.lock.yaml` order. Use explicit
comment headings in `repos.yaml` and keep the headings in the same conceptual
order as the final source tree: Odoo, Enterprise when present, OCA, deployment
owner, then third-party providers. Inside each heading, keep repositories
alphabetically ordered by path. Odoo-first is recommended, but not hardcoded.

The `odoo` repo is the only normal special case: it expands to two addon roots.
Other repos should normally be addon roots already, so their generated path is
the materialized repository directory itself. Single-module/nested-root
detection is compatibility behavior, not the preferred layout.

If two addon roots contain a module with the same technical name, Odoo uses the
first matching path. The builder therefore fails on duplicate module names
instead of relying on path precedence. Patch source through Git composition
rather than shadowing modules by path order.

Runtime `odoo-run` reads `/etc/odoo/addons_path` automatically when no explicit
`ODOO_ADDONS_PATH` or `ODOO_ADDONS_PATH_FILE` is provided. Runtime/deployment
configuration, whether Kubernetes manifests, Docker Compose files, Podman
quadlets, or local Docker commands, should not need to repeat the baked image's
addon path unless deliberately overriding it for a special case.

`requirements.lock.txt` is committed release state. If it already exists and
refresh mode is disabled, the builder uses it as-is for `pip install`; it does
not generate a candidate just to compare. If that lock is incompatible with the
current materialized tree, `pip install` or `pip check` will fail naturally and
the release must be fixed deliberately.

Python lock refresh is conditional and defaults to no refresh:

```text
empty bootstrap requirements.lock.txt:
  fail unless refresh=true;
  refresh=true generates the lock from the single materialized tree;
  extract it from the temporary source-build image, review it, and commit it.

existing requirements.lock.txt + refresh=false:
  use the versioned lock as-is;
  install from it;
  do not generate a candidate just to compare;
  if pip install or pip check fails, fix the inputs or refresh deliberately.

existing requirements.lock.txt + refresh=true:
  regenerate lock from the single materialized tree;
  extract it from the temporary source-build image;
  review it, and commit it before publishing.
```

The empty-lock case is first bootstrap only. After that,
`requirements.lock.txt` should always exist in the deployable Git repository
with real package lines.
This default is required for immutability. `requirements.in` may contain bounded
ranges such as `<5`; without the no-refresh rule, two consecutive derived-image
builds could resolve different Python versions without an explicit Git change.

Derived image Dockerfiles should keep default `ARG` values for
`ODOO_BUILDER_IMAGE` and `ODOO_RUNTIME_IMAGE`. Those defaults are the release
source of truth for the base images. Use `--build-arg` only for local or
experimental builds, so official base-image changes remain visible in Git.

## Deferred Permanent Tests

Exploratory validation material from an implementation workspace is not part of
this repository and must not be referenced by the image documentation. Before
freezing and publishing the complete Odoo image workflow, promote useful
proving cases into permanent executable tests in the relevant repositories.

The permanent tests should live in the repository or CI, run against built
images, and never be copied into the final runtime image.

Minimum validation coverage to keep:

```text
build runtime and builder images
build a derived Odoo-only image from the scaffold
verify odoo-bin --version
verify pip check
verify selected Python imports
verify requirements-overrides.in behavior
verify system-build-packages.txt packages do not leak into final runtime
verify system-runtime-packages.txt packages are present when required
verify requirements.lock.txt is not copied into the final runtime image
verify .git directories are not copied into /opt/odoo/src
verify generated addons_path
run a PostgreSQL-backed Odoo smoke test with odoo-init
```

Rule: no image release should be published if the permanent validation suite
fails. Exploratory checks remain useful as historical reasoning, but the final
guardrail must be repeatable scripts/CI checks.

## What Must Not Belong Here

- OCA repository selection.
- Odoo Enterprise source.
- Organization/customer addon repositories.
- Deployment-specific `repos.yaml` or `repos.lock.yaml`.
- Deployment-specific `requirements.lock.txt` or populated
  `requirements.in` / `requirements-constraints.in`.
- Hand-maintained deployment-specific `addons_path`. The generated
  `/etc/odoo/addons_path` belongs to the derived image build output, not to the
  reusable base image.
- Secrets, credentials, SSH keys, tokens, or kubeconfig material.

`git`, `git-aggregator`, build caches, `.git` directories, `repos.yaml`,
`repos.lock.yaml`, and `requirements.lock.txt` must not be present in the final
runtime image by default. They may exist in the source-build execution. The
lock files must exist in GitHub; they do not need to be copied into the runtime
image. Future OCI labels can point from an image to the exact Git commit/tag
containing those locks.

Python dependency inputs are split by responsibility:

```text
src/odoo/requirements.txt   -> upstream Odoo requirements, always included
requirements.in             -> human-selected extra packages to install
requirements-constraints.in -> human compatibility bounds, installs nothing
requirements.lock.txt       -> generated exact install set
```

Do not feed full OCA/provider repository `requirements.txt` files into the lock
by default. A repository can contain many modules, and this image may use only
one of them. Add only the packages required by the selected addons to
`requirements.in`; use `requirements-constraints.in` only to constrain versions
requested elsewhere.

Avoid naked unbounded dependencies in `requirements.in`. Prefer exact pins for
direct extra packages, or a deliberate narrow range when exact pinning is not
appropriate. The generated `requirements.lock.txt` is still the exact install
set, but broad ranges should only move when the Python lock refresh mode is
explicitly enabled and the resulting diff is reviewed.

Linux system dependencies are split the same way:

```text
oci-odoo/images/runtime/Dockerfile
  -> shared runtime packages needed by almost every Odoo deployment

oci-odoo/images/builder/Dockerfile
  -> shared build tools/dev headers needed by the generic builder contract

derived image system-build-packages.txt
  -> Debian packages needed only while building this concrete deployment image

derived image system-runtime-packages.txt
  -> Debian runtime libraries needed by this concrete deployment image
```

Do not put every possible OCA/provider system package into the shared base "just
in case". Add a system package to the shared base only when it is part of the
generic Odoo/build contract. Otherwise declare it in the derived image. Example:
if a selected addon requires Python `pycups`, the derived image may need
`libcups2-dev` while building and `libcups2` while running. If a selected addon
requires `pyzbar`, the runtime image may need `libzbar0` even when `pip check`
passes.

The builder API currently produces two runtime artifacts:

```text
/opt/odoo/src   -> materialized Odoo/addon source tree
/opt/odoo/venv  -> immutable Python virtualenv with Odoo requirements installed
```

The final deployment image should copy both paths from the temporary builder
stage. Build-only packages needed to compile Python dependencies belong in
`images/builder/Dockerfile`, not in `images/runtime/Dockerfile`.

## Runtime Configuration And Secrets

`odoo-run` is the runtime entrypoint inherited by deployment images. It is not a
build script. With no runtime configuration environment it simply executes the
baked Odoo source. When runtime variables are provided, it writes a temporary
`/run/odoo/odoo-runtime.conf` with `0600` permissions and runs Odoo with `-c`.

`odoo-init` is an explicit operator tool for initializing a genuinely empty
PostgreSQL database as an Odoo database. It defaults to `base`, refuses to run
when Odoo metadata already exists, and refuses ambiguous non-empty databases.
This covers empty-DB smoke tests without making the normal image entrypoint
dangerous for restored production databases. Production cutover with restored
databases should start Odoo with `odoo-run`, not initialize the database.

Database passwords and Odoo master passwords must come from runtime secret
delivery, preferably mounted as files and referenced with
`ODOO_DB_PASSWORD_FILE` and `ODOO_ADMIN_PASSWD_FILE`. In Kubernetes this
usually means Secret-mounted files; in Docker/Podman/Compose it can be an
equivalent secret-file mount or environment-file mechanism. This keeps secrets
out of Dockerfiles, image layers, Git repositories, manifests/config files, and
command-line arguments.

The wrapper may translate runtime Secret/config inputs into Odoo's expected
configuration format. It must not fetch source, run `gitaggregate`, install
Python packages, alter addons, or mutate anything that belongs to the immutable
image release.

The intended runtime configuration merge is:

```text
deployment repo/copy:
  per-instance non-secret odoo.conf
        +
image:
  /etc/odoo/addons_path
        +
Secret-mounted files or equivalent runtime inputs:
  db_password, admin_passwd
        =
container temporary state:
  /run/odoo/odoo-runtime.conf
```

The real base `odoo.conf` is not part of `derived-image-scaffold/` because it
is not image build input. It belongs to the deployment repo/copy for each
runtime instance. It may contain non-secret settings such as database name,
database host/user, dbfilter, workers, queue-job channels, ports, proxy mode,
list_db, or extra sections such as `[queue_job]`. It must not contain
`db_password`, `admin_passwd`, or `addons_path`. `odoo-run` consumes it through
`ODOO_BASE_CONFIG_FILE` and renders `/run/odoo/odoo-runtime.conf`; generated
Secret/image values override same-named base options.

The generated file lives under `/run/odoo` because it is runtime process state.
It must remain ephemeral and non-versioned, but it should not live under `/tmp`,
where generic tmp-cleaning policies may remove files during long-running
processes. Security comes from permissions and non-persistence: `/run/odoo`
must be private to the `odoo` user (`0700`) and the generated config must be
`0600`.

Reusable deployment scaffolding lives under `deployment-scaffold/`, grouped by
target runtime/orchestrator. The current included example is
`deployment-scaffold/k8s/`, because this project currently includes a
Kubernetes deployment scaffold. Future siblings can be added for `podman/`,
`docker-compose/`, `nomad/`, or any other OCI-capable deployment model.

The k8s scaffold's `instances/instance1.example/odoo.conf` is the starting
point for real per-instance files such as `instances/production/odoo.conf` in a
client deployment repository. Its
`manifests/patterns/runtime-config-wiring.example.yaml` documents Kubernetes
ConfigMap/Secret/`/run/odoo` wiring without pretending to be a complete
production manifest. Its `manifests/secrets/README.md` documents the
Secret-name/key contract without containing Secret values.

The distinction is:

```text
images/runtime/   -> files that build ghcr.io/nuobit/oci-odoo
images/builder/   -> files that build ghcr.io/nuobit/oci-odoo-builder
tools/            -> repo/CI/operator commands, executed outside images
derived-image-scaffold/ -> starting point copied into derived image repos
deployment-scaffold/k8s/ -> Kubernetes deployment scaffold example
```

Do not move a file into `images/runtime` or `images/builder` unless it is part
of that published image's build context/contract.

Keep the image repository separate from the later deployment repository:

```text
image repo       -> what is packaged into an OCI image
deployment repo  -> how that image is executed for concrete instances
```

For example, a client may have:

```text
<client-org>/oci-odoo
  builds one deployable Odoo image, for example
  ghcr.io/<client-org>/oci-odoo:17.0-py310-trixie-r0001

<client-org>/k8s-odoo-<client-key>
  executes that image one or more times, for example one Pod per database or
  business instance
```

Concrete invented example:

```text
examplecorp/oci-odoo
  builds ghcr.io/examplecorp/oci-odoo:17.0-py310-trixie-r0001

examplecorp/k8s-odoo-examplecorp
  executes that same image for production, staging, or test instances
```

`repos.yaml` belongs to the image repo because it defines source code that is
materialized into `/opt/odoo/src` and therefore packaged into the image.

A real `odoo.conf` belongs to the deployment repo because it defines how one
runtime instance executes the image: database name, dbfilter, workers,
queue-job channels, ports, and similar instance-level settings. It must not be
baked into the derived image repo unless a project explicitly chooses a
single-instance image model.

The reusable base repository may provide a future deployment scaffold, but it
should stay separate from `derived-image-scaffold/`:

```text
derived-image-scaffold/      -> create a deployable image repo
deployment-scaffold/k8s/     -> create a Kubernetes deployment repo/copy
deployment-scaffold/podman/  -> future Podman deployment repo/copy
deployment-scaffold/docker-compose/ -> future Docker Compose deployment repo/copy
```

The second scaffold is reusable deployment knowledge, but the copied deployment
repo is client-specific. This preserves the ability to run the same derived
image with Docker, Podman, containerd, Kubernetes, Docker Compose, CI, or
local tests.

## License and Copyright

Odyssey / `oci-odoo` is copyright (C) 2026 NuoBiT Solutions, S.L.

This repository is licensed under the Apache License, Version 2.0. See
`LICENSE` and `NOTICE`.

The license applies to this repository's own code, documentation, Dockerfiles,
scripts, and scaffolding. Odoo, OCA addons, Odoo Enterprise code, Debian
packages, Python packages, base images, and other third-party components keep
their own licenses.

## Build Commands

Local foundation build example from the `oci-odoo` repository:

```bash
docker buildx build \
  -f images/runtime/Dockerfile \
  -t local/oci-odoo:17.0-py310-trixie-r0001 \
  --load .

docker buildx build \
  -f images/builder/Dockerfile \
  -t local/oci-odoo-builder:17.0-py310-trixie-r0001 \
  --load .
```

The builder image depends on the runtime image. Build/publish runtime first,
then builder.

## Manual Deployment-Image Flow

This is the current local flow an operator can run by hand to understand each
piece before CI/GitOps automation exists.

From the base repository:

```bash
export OCI_ODOO_WORKDIR="$HOME/src/container-infra/odoo"
export OCI_ODOO_BASE_REPO="$OCI_ODOO_WORKDIR/nuobit/oci-odoo"

cd "$OCI_ODOO_BASE_REPO"

docker buildx build \
  -f images/runtime/Dockerfile \
  -t local/oci-odoo:17.0-py310-trixie-r0001 \
  --load .

docker buildx build \
  -f images/builder/Dockerfile \
  -t local/oci-odoo-builder:17.0-py310-trixie-r0001 \
  --load .
```

From the deployable image repository:

```bash
cd "$OCI_ODOO_WORKDIR/examplecorp/oci-odoo"

"$OCI_ODOO_BASE_REPO/tools/lock-repos"

# If repos.lock.yaml references private HTTPS GitHub repositories, create a
# local Git credential-store file outside Git and pass it as a BuildKit secret:
#   https://x-access-token:<fine-grained-token-with-read-access>@github.com
#
# The builder reads it with a read-only Git credential helper during the
# source-build RUN. The secret is not copied into either image or any layer.
export GIT_CREDENTIALS_FILE="$HOME/.config/oci-odoo/credentials/examplecorp.git-credentials"

docker build \
  -f Dockerfile.source-build \
  --secret id=git_credentials,src="$GIT_CREDENTIALS_FILE" \
  --build-arg ODOO_BUILDER_IMAGE=local/oci-odoo-builder:17.0-py310-trixie-r0001 \
  -t local/examplecorp-oci-odoo-source-build:17.0-py310-trixie-r0001 \
  .

docker build \
  --build-arg ODOO_RUNTIME_IMAGE=local/oci-odoo:17.0-py310-trixie-r0001 \
  --build-arg ODOO_SOURCE_BUILD_IMAGE=local/examplecorp-oci-odoo-source-build:17.0-py310-trixie-r0001 \
  -t local/examplecorp-oci-odoo:17.0-py310-trixie-r0001 \
  .

docker run --rm local/examplecorp-oci-odoo:17.0-py310-trixie-r0001 --version
docker run --rm \
  --entrypoint /opt/odoo/venv/bin/python \
  local/examplecorp-oci-odoo:17.0-py310-trixie-r0001 \
  -m pip check
```

What each step means:

```text
lock-repos                -> repos.yaml to repos.lock.yaml, no gitaggregate
derived release workflow  -> one source-build image build:
                              gitaggregate once
                              use/generate/refresh requirements.lock.txt
                              create src + venv
                              keep requirements.lock.txt in temporary source-build image
                              extract/commit requirements.lock.txt if created/refreshed
                              package final deployable image
docker run checks         -> prove Odoo and Python dependencies are coherent
```

## Derived Image Release Phases

Keep these phases separate. They happen at different times and must not be
collapsed mentally into a single "build" step.

```text
1. Repository bootstrap
   Create the derived image repo and copy derived-image-scaffold/.
   Output: Dockerfile, README.md, repos.yaml, requirements.in,
   requirements-constraints.in, .gitignore, .dockerignore.

2. Source intent selection
   Edit repos.yaml manually and, if useful, run discovery tools such as a future
   OCA discovery helper. This is where OCA, organization-specific,
   customer-specific, or third-party repos are selected. Enterprise may require a separate
   customer-access download/acquisition flow and must not be assumed to be a
   normal public GitHub/gitaggregate repository.
   Output: updated repos.yaml.

   Preferred Enterprise direction: import Enterprise into a private internal Git
   service such as Gitea/Forgejo, then reference that private repo from
   `repos.yaml` and let `repos.lock.yaml` freeze the Enterprise commit like
   every other source. Do not keep ad hoc web-download processing logic in this
   image repo until that workflow is deliberately designed.

   Edit requirements.in only for extra Python packages actually needed by the
   selected addons. Do not bulk-copy OCA/provider requirements.txt files.
   Edit requirements-constraints.in only for compatibility bounds.

3. Release preparation / lock generation
   Run lock-repos to generate repos.lock.yaml.
   This resolves source refs only. It must not materialize sources with
   gitaggregate and must not generate requirements.lock.txt separately.

4. Derived image release workflow
   Run the builder-backed derived image workflow. This is the only place that
   executes gitaggregate. It uses an existing requirements.lock.txt as-is by
   default, or refreshes it from the same materialized tree when refresh mode is
   explicitly enabled. It creates /opt/odoo/src and /opt/odoo/venv and packages
   the final runtime image.

   The default requirements-lock mode is no refresh. If a versioned
   requirements.lock.txt exists, install from it without generating a comparison
   candidate. Use an explicit refresh mode only when intentionally accepting a
   changed Python dependency set and committing the new lock diff.

   When refresh mode generates a new lock, extract `/tmp/requirements.lock.txt`
   from the temporary source-build image and commit it. Do not run a second lock
   command for the same release.

5. Image validation
   Run the image and validate Odoo/Python coherency before pushing/deploying.
```

## Deployment Image Scaffold

Start every deployment image by copying the whole scaffold. Example for a new
client organization called `diaspora`:

```bash
export OCI_ODOO_WORKDIR="$HOME/src/container-infra/odoo"
export OCI_ODOO_BASE_REPO="$OCI_ODOO_WORKDIR/nuobit/oci-odoo"

cd "$OCI_ODOO_WORKDIR"
mkdir -p diaspora/oci-odoo
cd diaspora/oci-odoo
git init -b 17.0
cp -a "$OCI_ODOO_BASE_REPO/derived-image-scaffold/." .
```

This creates the deployment image `Dockerfile`, `README.md`, `repos.yaml`,
`requirements.in`, `requirements-constraints.in`, `.gitignore`, and
`.dockerignore`. Then edit `repos.yaml` for the concrete deployment. The file
uses the official `git-aggregator` format and starts with Odoo Community source
only. Enterprise, OCA, provider, and project-specific repositories are added by
the deployment image.

Do not generate locks before the source intent is correct. First edit
`repos.yaml` or run any source-discovery helper, then generate
`repos.lock.yaml`.

Do not run a separate Python-lock step that materializes sources before the
derived image workflow. That would execute `gitaggregate` twice. The Python lock
is used, generated, or refreshed inside the same source-build execution that
prepares the final `/opt/odoo/src` and `/opt/odoo/venv` artifacts. Even if an
upstream input such as Odoo's `pytz` line is not fully pinned, the generated
`requirements.lock.txt` remains in the temporary source-build image and is then
extracted back to GitHub for review as part of the release diff before
publishing a new image tag. This avoids a second `gitaggregate`.

NTH after this manual flow is proven: add a helper under `tools/`, for example
`tools/bootstrap-derived-image`, that creates the derived image directory,
initializes the branch, and copies `derived-image-scaffold/` in one command.
Keep it transparent: no hidden commit, no hidden push, and no lock generation
unless an explicit flag is added later.

Generate the lock file from the deployment image repository:

```bash
"$OCI_ODOO_BASE_REPO/tools/lock-repos"
```

This writes `repos.lock.yaml`. Edit `repos.yaml`; do not edit
`repos.lock.yaml` manually.

Default `lock-repos` behavior is conservative:

- existing refs already present in `repos.lock.yaml` keep their SHA;
- new refs added to `repos.yaml` are resolved and added;
- refs removed from `repos.yaml` disappear from the lock;
- no existing SHA moves unless refresh is explicitly requested.

Use the narrowest refresh mode:

```bash
# Move one merge inside an aggregate, keeping the rest frozen.
"$OCI_ODOO_BASE_REPO/tools/lock-repos" --refresh-merge ./odoo nuobit 17.0-hotfix-stock-based-on-P

# Move every merge inside one aggregate path.
"$OCI_ODOO_BASE_REPO/tools/lock-repos" --refresh ./odoo

# Move everything selected in repos.yaml.
"$OCI_ODOO_BASE_REPO/tools/lock-repos" --refresh-all
```

The generated lock includes comments such as `# locked-from: odoo 17.0`. They
are ignored by `git-aggregator` but used by `lock-repos` to preserve which
human ref produced each SHA. Do not remove them manually.

Example with several merges:

```yaml
./odoo:
  merges:
    - odoo 17.0
    - nuobit 17.0-hotfix-stock
    - ff 17.0-barcodes-patch
```

If the lock currently pins `odoo -> P`, `nuobit -> H1`, and `ff -> F1`:

- no-argument `lock-repos` keeps `P`, `H1`, and `F1`;
- `--refresh-merge ./odoo nuobit 17.0-hotfix-stock` moves only `H1 -> H2`;
- `--refresh ./odoo` moves all three merge lines;
- `--refresh-all` moves every merge in every aggregate path.

If a merge is being added for the first time, no refresh flag is needed. Edit
`repos.yaml` and run plain `lock-repos`; existing SHAs stay frozen and the new
merge is added with its current SHA.
