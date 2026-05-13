# Derived Odoo Image

This scaffold creates a deployable Odoo image derived from the base `oci-odoo`
image.

Initial files:

```text
Dockerfile
Dockerfile.source-build
README.md
repos.yaml
requirements.in
requirements-constraints.in
requirements-overrides.in
requirements.lock.txt
system-build-packages.txt
system-runtime-packages.txt
.gitignore
.dockerignore
```

`repos.yaml`, `requirements.in`, `requirements-constraints.in`,
`requirements-overrides.in`, `system-build-packages.txt`, and
`system-runtime-packages.txt` are the real maintained files for this deployable
image. `repos.lock.yaml` and `requirements.lock.txt` are generated release
files and must be committed after generation. The scaffold starts with a
bootstrap placeholder `requirements.lock.txt`; the first real build must refresh
it.

File roles:

```text
Dockerfile.source-build temporary source-build image; runs the only gitaggregate
                        for a release candidate and generates addons_path
Dockerfile              final runtime image; copies src/venv/addons_path from source-build
                        and never runs gitaggregate
README.md               local operator notes for this derived image repo
repos.yaml                    manual; git-aggregator source selection, Odoo included
repos.lock.yaml               generated; exact Git revisions, do not edit manually
requirements.in               manual; extra Python packages to install
requirements-constraints.in   manual; Python version bounds only, does not install
requirements-overrides.in     manual; explicit replacement for conflicting direct requirements
requirements.lock.txt         generated; exact Python dependency set, do not edit manually
system-build-packages.txt     manual; Debian packages needed only in the builder stage
system-runtime-packages.txt   manual; Debian packages needed in the final runtime image
.gitignore                    local Git hygiene; generated lock files are not ignored
.dockerignore                 Docker build context hygiene
```

This scaffold is only for the image repository: it defines what will be
packaged into a deployable OCI image. Do not add the real runtime `odoo.conf`
for a concrete database/business instance here.

The separation is:

```text
derived image repo  -> what is inside the image
deployment repo     -> how the image is executed
```

`repos.yaml` belongs here because it selects source code that becomes
`/opt/odoo/src` inside the final image. A real `odoo.conf` does not belong here
because it selects execution settings such as `db_name`, `dbfilter`, workers,
queue-job channels, ports, and runtime secrets wiring for one concrete
instance.

If the same image is used for multiple databases or business instances, each
one should have its own runtime/deployment configuration while all of them may
use the same image tag.

The derived image must use a coherent base image pair: the source-build image
uses `oci-odoo-builder:<tag>` and the final image uses `oci-odoo:<tag>` from
the same Odoo/Python/OS line. For Odoo 17, the default tag shape is
`17.0-py310-trixie-rNNNN`. If a deployment ever needs another Python minor,
create a new Python-on-trixie base variant first, then rebuild both the builder
and this derived image. Refresh `requirements.lock.txt` because Python markers
and wheels can change.

Runtime-specific execution templates should live in a separate deployment
scaffold, for example `deployment-scaffold/k8s/` in the base repository, and be
copied into a concrete deployment repo such as `k8s-odoo-<deployment-key>`.
Concrete invented example: `k8s-odoo-examplecorp`.
Kubernetes/k3s is only one supported deployment model for the OCI image. Future
deployment scaffolds may target Docker Compose, Podman, Nomad, or any other
runtime/orchestrator that can run OCI images.

The deployment repo can contain non-secret `odoo.conf` files, Deployments,
Services, Ingresses, PVCs, Jobs, ConfigMaps, and references to Secrets when the
target is Kubernetes/k3s. Equivalent Docker/Podman deployment repos would use
their own runtime-specific files instead.

Runtime should pass each non-secret `odoo.conf` with `ODOO_BASE_CONFIG_FILE`.
The inherited `odoo-run` entrypoint merges that file with the image-generated
`/etc/odoo/addons_path` and Secret-file values into
`/run/odoo/odoo-runtime.conf`.
Do not put `db_password`, `admin_passwd`, or `addons_path` in the base
`odoo.conf`.

`repos.yaml` uses the official `git-aggregator` format:

```text
https://github.com/acsone/git-aggregator
```

The copied file is the source of truth for repository membership. Existing
folders in a build tree must not add or remove repositories.

Keep `repos.yaml` readable with explicit section headings that match the final
source tree: Odoo repositories, OCA repositories, deployment-owner repositories,
and third-party repositories. If Enterprise is added later, give it its own
section. Keep repositories alphabetically ordered inside each section. The
builder preserves this order; it does not reorder the file for you.

Python dependencies are split deliberately:

```text
src/odoo/requirements.txt   upstream Odoo requirements; always included
requirements.in             manual; extra packages selected for this image
requirements-constraints.in manual; version limits for compatibility
requirements-overrides.in   manual; explicit conflict replacement decisions
requirements.lock.txt       generated; exact resolved install set
```

Do not install every `requirements.txt` from every selected OCA/provider
repository by default. Those files may cover many modules that this image does
not use, increasing dependency conflicts and image size. Add only the packages
actually needed by the selected addons to `requirements.in`.

`requirements.in` installs packages. If a selected addon needs a known
compatible version, pin it there:

```text
phonenumbers==8.13.47
```

`requirements-constraints.in` does not install anything. It only constrains
packages that are requested by Odoo, `requirements.in`, or transitive
dependencies:

```text
urllib3<2
```

`requirements-overrides.in` is only for direct requirement conflicts after
marker filtering. It replaces conflicting active lines with the exact line a
human selected. Do not use it as a casual pinning file.

Do not edit `requirements.lock.txt` by hand. If it exists and refresh mode is
disabled, the release workflow installs from it as-is. If it is incompatible
with the selected sources, `pip install` or `pip check` will fail and the
release must be fixed deliberately.

`Dockerfile.source-build` owns `requirements.lock.txt` inside the single
source-build execution that also runs `gitaggregate` and creates
`/opt/odoo/venv`. It must not run a separate requirements-lock step that
materializes sources a second time.

The same source-build execution also generates:

```text
/etc/odoo/addons_path
```

That file is generated from `repos.lock.yaml` after the locked sources have
materialized under `/opt/odoo/src`. It is copied into the final image and read
by `odoo-run` at startup when no explicit `ODOO_ADDONS_PATH` override is set.
Do not maintain `addons_path` by hand in runtime manifests/config files for the
normal case.

When the Odoo source repo is present, the generated file keeps both Odoo roots
explicitly and first: `/opt/odoo/src/odoo/odoo/addons` and
`/opt/odoo/src/odoo/addons`. Odoo 17 only creates both defaults when
`addons_path` is empty; with an explicit value it preserves the supplied list.
They are first when `odoo` is first in `repos.yaml`/`repos.lock.yaml`, which is
recommended but not forced. Remaining roots follow deterministic lock order.
The `odoo` repo is the special expansion case; other repos should normally be
addon roots already, so their generated path is their materialized directory.
If duplicate module names exist across roots, the build must fail; Odoo would
otherwise use the first path silently.

A locked repository that has no detectable Odoo addon root is still valid. It is
materialized, pinned, and still included in generated `addons_path`. If it is
empty, Odoo simply finds no modules there.

Odoo may still log `/var/lib/odoo/addons/17.0` in the effective runtime addon
path because it appends `data_dir/addons/<series>` internally. Do not use that
path for deployment code; it is mutable runtime data, not part of the immutable
image source tree.

Requirements-lock refresh is disabled by default. If a previous lock exists,
the workflow uses it directly and does not generate a comparison candidate. The
bootstrap placeholder is intentionally empty and will fail unless the first
build uses `--build-arg REFRESH_REQUIREMENTS_LOCK=1`.

When refresh mode is explicitly enabled, the same source-build execution
regenerates the lock from the materialized tree, installs from it, and leaves
that generated lock in the temporary source-build image at:

```text
/tmp/requirements.lock.txt
```

Extract that file from the temporary source-build image, replace the repository
`requirements.lock.txt`, review the diff, and commit it before building or
publishing the immutable final image tag. Do not run a separate lock command;
that would run `gitaggregate` again.

This protects determinism even when upstream inputs such as Odoo's `pytz`
requirement or a bounded direct requirement can resolve differently over time.

Refresh controls are deliberately split by artifact:

```bash
# Source lock: updates repos.lock.yaml only; does not run gitaggregate.
export OCI_ODOO_BASE_REPO="$HOME/src/container-infra/odoo/nuobit/oci-odoo"
"$OCI_ODOO_BASE_REPO/tools/lock-repos"
"$OCI_ODOO_BASE_REPO/tools/lock-repos" --refresh-merge ./odoo <remote> <ref>
"$OCI_ODOO_BASE_REPO/tools/lock-repos" --refresh ./odoo
"$OCI_ODOO_BASE_REPO/tools/lock-repos" --refresh-all

# Python lock: happens inside the one source-build execution.
docker build -f Dockerfile.source-build ...
docker build -f Dockerfile.source-build --build-arg REFRESH_REQUIREMENTS_LOCK=1 ...
```

Plain `lock-repos` preserves existing SHAs, adds new refs, removes deleted
refs, and never moves a locked ref because a branch advanced upstream.
`--refresh-merge` moves one selected merge, `--refresh <dest>` moves every
merge in one aggregate destination, and `--refresh-all` moves all selected
sources. If a merge is being added for the first time, plain `lock-repos` is
enough.

For Python, the default is no refresh: use the committed
`requirements.lock.txt` exactly as it is. Use
`REFRESH_REQUIREMENTS_LOCK=1` only when intentionally accepting a new Python
dependency set. The generated lock is left in the temporary source-build image
at `/tmp/requirements.lock.txt`; extract it, review it, and commit it before
publishing the final image. Never run a separate Python-lock command that
materializes sources, because that would run `gitaggregate` twice.

Linux system dependencies are declared separately from Python dependencies.
Use `system-build-packages.txt` for Debian packages required to build Python
packages or native extensions for this derived image. Use
`system-runtime-packages.txt` for Debian shared libraries required when the
final image runs. Both files allow one package per line; blank lines and
comments are ignored.

Examples:

```text
pycups  -> system-build-packages.txt: libcups2-dev
pycups  -> system-runtime-packages.txt: libcups2
pyzbar  -> system-runtime-packages.txt: libzbar0
```

If a system package becomes generic enough to belong to all Odoo builds, move
that decision up to the base `oci-odoo` or `oci-odoo-builder` Dockerfile in a
dedicated release change. Do not preinstall every possible OCA/provider system
package in the base images.

Build flow:

If `repos.lock.yaml` references private HTTPS GitHub repositories, pass
credentials as a BuildKit secret. The committed Dockerfile exposes only the
secret identifier (`git_credentials`), never the credential contents nor the
operator's host path.

For a new workstation or cleaner build identity, create a separate read-only
build token and store it in a dedicated local secret file:

`~/.config/oci-odoo/` is the default local operator configuration directory for
OCI Odoo image builds. It is outside Git and can hold build-only credentials or
future local build configuration. The directory is generic, but credential files
should be scope-specific, for example
`~/.config/oci-odoo/credentials/examplecorp.git-credentials`.

```bash
mkdir -p "$HOME/.config/oci-odoo"
chmod 700 "$HOME/.config/oci-odoo"
mkdir -p "$HOME/.config/oci-odoo/credentials"
chmod 700 "$HOME/.config/oci-odoo/credentials"

# Paste one line in Git credential-store format:
# https://x-access-token:<TOKEN>@github.com
$EDITOR "$HOME/.config/oci-odoo/credentials/<scope>.git-credentials"
chmod 600 "$HOME/.config/oci-odoo/credentials/<scope>.git-credentials"

export GIT_CREDENTIALS_FILE="$HOME/.config/oci-odoo/credentials/<scope>.git-credentials"
--secret id=git_credentials,src="$GIT_CREDENTIALS_FILE"
```

Create the token as a GitHub fine-grained personal access token whenever
possible:

```text
GitHub -> Settings -> Developer settings -> Personal access tokens
       -> Fine-grained tokens -> Generate new token
```

```text
Token name:
  OCI Odoo <Client> Source Build
Resource owner:
  GitHub owner of the private repos
Expiration:
  No expiration, unless organization policy forces one
Repository access:
  Only select repositories
Selected repositories:
  every private repo referenced by repos.lock.yaml
Repository permissions:
  Contents: Read-only
  Metadata: Read-only
  Everything else: No access
```

Classic PATs are a fallback only; for private repositories they generally need
the broad `repo` scope and cannot be limited to selected repositories like a
fine-grained token.

If the workstation already has a suitably limited `~/.git-credentials`, it can
be used as that local secret source instead of duplicating the token. That
choice belongs to the operator command, not to the Dockerfile.

The secret is mounted only during the source-build `RUN`; it is not copied into
the source-build image, final image, or Docker layers. Omit `--secret` when all
repositories are public.

Inside the source-build `RUN`, the builder command configures Git with a
read-only credential helper. The helper keeps the input format as a normal Git
credentials file, delegates only `get` to `git credential-store`, and ignores
`store`/`erase` so Git cannot try to write back to the read-only BuildKit
secret. This avoids `.netrc`, `GIT_ASKPASS`, manual token parsing, and
temporary credential copies in every derived Dockerfile.

Before running the full build, validate the credential with one read-only Git
operation against a selected private repo:

```bash
GIT_TERMINAL_PROMPT=0 \
git \
  -c credential.helper= \
  -c credential.helper='!f() { case "$1" in get) git credential-store --file="$GIT_CREDENTIALS_FILE" get ;; store|erase) cat >/dev/null ;; *) cat >/dev/null ;; esac; }; f' \
  ls-remote --heads https://github.com/<org>/<private-repo>.git <branch>
```

```bash
docker build \
  -f Dockerfile.source-build \
  --secret id=git_credentials,src="$GIT_CREDENTIALS_FILE" \
  --build-arg REFRESH_REQUIREMENTS_LOCK=1 \
  -t local/oci-odoo-example-source-build:17.0-py310-trixie-r0001 \
  .

cid="$(docker create local/oci-odoo-example-source-build:17.0-py310-trixie-r0001)"
docker cp "$cid:/tmp/requirements.lock.txt" requirements.lock.txt
docker rm "$cid"

docker build \
  --build-arg ODOO_SOURCE_BUILD_IMAGE=local/oci-odoo-example-source-build:17.0-py310-trixie-r0001 \
  --build-arg OCI_IMAGE_SOURCE=https://github.com/examplecorp/oci-odoo \
  --build-arg "OCI_IMAGE_DESCRIPTION=Example Odoo 17 deployable image" \
  -t local/oci-odoo-example:17.0-py310-trixie-r0001 \
  .
```

For normal builds after the lock is committed, omit
`--build-arg REFRESH_REQUIREMENTS_LOCK=1` in the source-build image build.

`Dockerfile.source-build` creates a temporary local image. It is not pushed and
not deployed. The final `Dockerfile` creates the image that goes to the OCI
registry. It can then be run by Docker, Podman, containerd, Kubernetes/k3s,
Docker Compose, CI, or another OCI-capable runtime.

When publishing the final image to GHCR, keep source/description in two places:
Dockerfile labels for the executable image, and index annotations for the
published OCI index that GHCR uses as the package tag.

```bash
GHCR_REPO="ghcr.io/examplecorp/oci-odoo"
GHCR_TAG="17.0-py310-trixie-r0001"
GHCR_IMAGE="${GHCR_REPO}:${GHCR_TAG}"
LOCAL_IMAGE="local/oci-odoo-example:${GHCR_TAG}"
OCI_SOURCE="https://github.com/examplecorp/oci-odoo"
OCI_DESCRIPTION="Example Odoo 17 deployable image"

docker tag "$LOCAL_IMAGE" "$GHCR_IMAGE"
docker push "$GHCR_IMAGE"

GHCR_DIGEST="$(docker buildx imagetools inspect "$GHCR_IMAGE" | awk '/^Digest:/ {print $2; exit}')"

docker buildx imagetools create \
  --annotation "index:org.opencontainers.image.source=${OCI_SOURCE}" \
  --annotation "index:org.opencontainers.image.description=${OCI_DESCRIPTION}" \
  --tag "$GHCR_IMAGE" \
  "${GHCR_REPO}@${GHCR_DIGEST}"
```

This is required for reliable GHCR repository auto-linking in the tested
laptop-publish workflow. If the package already exists without the source index
annotation, connect it once from the GitHub package UI; after that the link is
package-level and should survive normal tag updates.

The `Dockerfile*` default `ARG` values point to immutable `ghcr.io/nuobit` base
image releases and are the release source of truth. Use `--build-arg` only for
local or experimental builds.

## Future Tests

This scaffold currently documents the manual release flow. After the complete
image model works with Odoo, addons, generated `addons_path`, requirements,
overrides, and system packages, create permanent tests in the derived image
repository or CI. Those tests should execute against built images and must not
be copied into the final runtime image.

At minimum, keep tests for:

```text
source-build image succeeds
final runtime image succeeds
requirements.lock.txt refresh/no-refresh behavior
pip check
runtime Python imports for selected dependencies
absence of .git and requirements.lock.txt in the final image
absence of build-only Debian packages in the final image
presence of required runtime Debian shared libraries
generated /etc/odoo/addons_path
Odoo smoke with temporary PostgreSQL and -i base --stop-after-init
```
