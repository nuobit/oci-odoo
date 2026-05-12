# oci-odoo-builder

Generic Odoo OCI build foundation.

This image is a build-stage base, not a runtime image and not a deployable Odoo
image. Deployment image Dockerfiles use it only in a temporary multi-stage
builder stage.

## Why This Exists

`oci-odoo` is the clean runtime base. It should contain only what is needed to
run Odoo in a final OCI image. That image can be executed by Docker, Podman,
containerd, Kubernetes/k3s, Docker Compose, CI, or another OCI-capable runtime.

`oci-odoo-builder` contains tools needed to build the final deployment image:

- `git`;
- `git-aggregator`;
- build-only Python/native dependency tooling such as compiler tools,
  `python3-dev`, `libpq-dev`, `libldap2-dev`, and `libsasl2-dev`;
- `odoo-build-image`, the high-level build command used by deployment image
  Dockerfiles;
- `odoo-build-python-env`, the internal helper that uses or refreshes
  `requirements.lock.txt` and creates `/opt/odoo/venv` after sources already
  exist;
- `odoo-generate-addons-path`, the helper that derives `/etc/odoo/addons_path`
  from `repos.lock.yaml` and the materialized source tree;
- future build-only tools when they are genuinely needed.

The builder inherits the Python runtime contract from the matching
`oci-odoo` runtime image. For Odoo 17, the default builder line is based on the
same Debian trixie + Python 3.10 runtime as `oci-odoo`. Build and publish
runtime and builder tags as a pair; a derived image must not use mismatched
Python variants.

For Odoo's own source repository, `odoo-generate-addons-path` writes both
Odoo-owned roots explicitly and before extra addon repositories:

```text
/opt/odoo/src/odoo/odoo/addons
/opt/odoo/src/odoo/addons
```

This is intentional. Odoo 17 only creates both defaults when `addons_path` is
empty. With an explicit `addons_path`, it preserves the supplied order; later
module initialization guarantees only the base/core root if it was missing.

The remaining addon roots follow deterministic `repos.lock.yaml` order. The
generator does not silently reorder repositories. Odoo-first is recommended in
`repos.yaml`, but not hardcoded.

The `odoo` repo is special: it expands to `/opt/odoo/src/odoo/odoo/addons` and
`/opt/odoo/src/odoo/addons`. Other repos should normally be addon roots already,
so their generated path is the materialized repo directory itself.

Locked repositories that do not yet contain Odoo modules are allowed. They are
materialized, remain pinned by `repos.lock.yaml`, and still appear in generated
`addons_path`. An empty addon path is harmless; Odoo simply finds no modules there.

Odoo resolves duplicate module names by first path match. The builder treats
duplicates as an error so the image does not depend on a silent precedence rule.

Those tools must not be installed in the final runtime image. They increase the
image size, expand the attack surface, and make it easier to accidentally
mutate runtime containers.

This builder image exists so every deployment image can share the same build
environment without duplicating build-tool installation in each client
Dockerfile.

It is intentionally separate from `tools/`:

- `images/builder/` builds a published OCI image used in Dockerfile
  multi-stage builds;
- `tools/` contains repository/operator scripts run from the laptop or CI before
  or around the image build.

## Pattern

Deployment images should use this conceptual shape:

```text
Dockerfile.source-build:
  FROM oci-odoo-builder
  receives repos.lock.yaml, requirements*.in, requirements.lock.txt
  runs gitaggregate exactly once
  uses requirements.lock.txt as-is when it exists and refresh is false
  regenerates requirements.lock.txt only when refresh is explicit
  creates /opt/odoo/src and /opt/odoo/venv
  creates /etc/odoo/addons_path
  keeps /tmp/requirements.lock.txt for optional extraction

Dockerfile:
  FROM oci-odoo
  FROM local/<derived>-source-build AS source-build
  copy /opt/odoo/src
  copy /opt/odoo/venv
  copy /etc/odoo/addons_path
```

The deployment image Dockerfile should not know whether source construction is
internally three steps, four steps, or more. That is the builder image's
contract. The final runtime image must not contain `repos.yaml`,
`repos.lock.yaml`, `requirements.lock.txt`, `.git`, build caches, or builder
tools. The temporary source-build image may contain the generated
`requirements.lock.txt` so the operator can extract the exact refreshed lock
without running `gitaggregate` a second time.

The temporary source-build image is a local build artifact, not a deployed
image. The final image receives only the files explicitly copied with
`COPY --from=source-build`.

Do not generate Python locks with a separate command that materializes sources
before the source-build image. That would run `gitaggregate` twice. Python
lock generation/verification belongs inside the same source-build execution
that produces `/opt/odoo/src` and `/opt/odoo/venv`.

## Private Git Credentials

Derived images pass private HTTPS GitHub credentials as a BuildKit secret named
`git_credentials`:

```text
--secret id=git_credentials,src="$GIT_CREDENTIALS_FILE"
```

The secret file uses Git's normal credential-store format:

```text
https://x-access-token:<TOKEN>@github.com
```

`odoo-build-image` configures Git only for its single `gitaggregate` step. It
installs a read-only credential helper that delegates only `get` to Git's own
`credential-store` parser:

```text
get          -> git credential-store --file=/run/secrets/git-credentials get
store/erase  -> consume stdin and do nothing
```

This keeps the token out of Docker layers, keeps the input format Git-native,
and avoids the writeback problem caused by pointing plain
`credential.helper store` directly at a read-only BuildKit secret. The builder
does not copy the secret to a temporary writable file, does not parse the token
manually, does not use `GIT_ASKPASS`, and does not use `.netrc`.

Requirements-lock refresh is off by default. The rules are:

```text
requirements.lock.txt exists + refresh=false:
  use it as-is for pip install;
  do not regenerate;
  do not compare with a newly generated candidate.

requirements.lock.txt exists + refresh=true:
  regenerate it from the single materialized tree;
  keep the new lock in the temporary source-build image for extraction and Git review/commit.

requirements.lock.txt empty bootstrap placeholder + refresh=false:
  fail and tell the operator to build once with explicit refresh.
```

The empty-lock case is only the first bootstrap of a derived image. After that,
the lock should always exist in Git with real package lines. This prevents broad
ranges such as `<5` from silently resolving to different versions across two
builds of the same apparent image definition. If the existing lock is
incompatible with the current sources, `pip install` or `pip check` will fail
and the release must be fixed or refreshed deliberately.

Do not feed every OCA/provider repository `requirements.txt` into the lock by
default. Those files can cover many modules that are not selected for this
deployment image. Use `requirements.in` for the extra packages actually needed
by the selected addons, and use `requirements-constraints.in` only to constrain
versions requested elsewhere.

`odoo-build-image` should own the single source-build execution: materialize
locked sources, generate `/etc/odoo/addons_path`, call `odoo-build-python-env`
to use or explicitly refresh `requirements.lock.txt` and create
`/opt/odoo/venv`, validate `odoo-bin --version`, and remove `.git` /
`__pycache__` directories from the source tree. The final runtime image should
not contain `git`, `gitaggregate`, `pip-tools`, compilers, or repository
metadata.

`odoo-build-python-env` is intentionally not a source materializer. It receives
an already materialized Odoo `requirements.txt`, the deployment requirement
inputs, the lock path, and the venv path. It must not call `gitaggregate`.

Do not add a separate requirements-lock command that materializes sources. That
creates a second path capable of running `gitaggregate` and violates the rule
that each release candidate materializes sources exactly once.

Do not add `AS runtime` to the final `FROM` unless that stage is referenced
later. The last stage is already the final runtime image.
