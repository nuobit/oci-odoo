# oci-odoo Runtime Image

This directory owns the clean Odoo runtime base image:

```text
ghcr.io/nuobit/oci-odoo:<version>
```

It contains only the common pieces needed to run an already-built Odoo release:

- Debian/Python runtime dependencies;
- `wkhtmltox` and common Odoo runtime packages;
- the `odoo` user and filesystem contract;
- generic runtime scripts such as `odoo-run`, `odoo-init`, `odoo-update`,
  `odoo-neutralize`, and `odoo-shell`;
- generic non-secret configuration conventions.

For Odoo 17, this runtime line uses Debian trixie with Python 3.10 from the
official Python slim image, pinned by digest. The operating-system base is fixed
for the Odoo 17 line; another Python minor would be a separate
Python-on-trixie variant, not an implicit OS change.

The final deployment image and the builder image must use the same Python
variant. Do not build sources/venv with a builder based on one Python minor and
then copy them into a runtime image based on another.

At runtime, Odoo must execute with the virtualenv Python:
`/opt/odoo/venv/bin/python`. `ODOO_PYTHON` identifies the base interpreter used
by the image variant and as a fallback, but it must not take precedence over
the venv for running Odoo because the Python packages are installed in the
venv. Use `ODOO_RUN_PYTHON` only for an explicit debugging override.

It must not contain client source selection or build tooling:

- no Odoo source tree;
- no Odoo Enterprise/private/OCA/customer addons;
- no `git`;
- no `git-aggregator`;
- no `.git` directories;
- no `repos.yaml` or `repos.lock.yaml`;
- no credentials, tokens, private keys, or kubeconfig material.

Deployable images copy their final source tree into this runtime base from a
temporary builder stage. The resulting OCI image is generic: it can run with
Docker, Podman, containerd, Kubernetes, Docker Compose, CI, or another
OCI-capable runtime. Every runtime inherits the same contract.

## Runtime Configuration Contract

`odoo-run` is the single runtime entrypoint. With no runtime configuration
environment it simply executes the packaged Odoo source:

```bash
odoo-run --version
```

When the deployment runtime provides runtime values, `odoo-run` renders a
generated runtime config file at `/run/odoo/odoo-runtime.conf`, mode `0600`, and
executes Odoo with `-c`.
Passwords must come from the runtime secret-delivery mechanism, preferably
mounted as files and referenced with `*_FILE` variables so they are not placed
on the command line. In Kubernetes this means Secret-mounted files; in
Docker, Podman, Docker Compose, or another OCI runtime it means the equivalent
secret or env-file mechanism for that runtime.
`/run/odoo` is owned by the `odoo` user and mode `0700`; if the deployment
mounts it as a volume, preserve that ownership/permission contract.
For the strictest runtime model, mount `/run/odoo` as memory-backed runtime
state, for example a Kubernetes `emptyDir`, so the generated config is
per-container volatile state rather than image, Git, persistent volume,
ConfigMap, log, or command-line data.

`ODOO_BASE_CONFIG_FILE` may point to a non-secret base `odoo.conf` supplied by
the deployment layer. `odoo-run` copies its allowed settings and merges runtime
values into `/run/odoo/odoo-runtime.conf`. The base config may contain normal
instance settings and extra sections such as `[queue_job]`, but it must not
contain `db_password`, `admin_passwd`, or `addons_path`. Those values come from
Secret files or from the image-generated `/etc/odoo/addons_path`.

Supported runtime variables:

```text
ODOO_BASE_CONFIG_FILE
ODOO_DB_HOST
ODOO_DB_PORT
ODOO_DB_USER
ODOO_DB_PASSWORD
ODOO_DB_PASSWORD_FILE
ODOO_DB_NAME
ODOO_DBFILTER
ODOO_ADMIN_PASSWD
ODOO_ADMIN_PASSWD_FILE
ODOO_ADDONS_PATH
ODOO_DATA_DIR
ODOO_PROXY_MODE
ODOO_LIST_DB
ODOO_WORKERS
ODOO_MAX_CRON_THREADS
ODOO_HTTP_PORT
ODOO_GEVENT_PORT
```

Use either `ODOO_DB_PASSWORD` or `ODOO_DB_PASSWORD_FILE`, not both. Same rule
for `ODOO_ADMIN_PASSWD` and `ODOO_ADMIN_PASSWD_FILE`.

Generated runtime values override same-named non-secret options from the base
config. This keeps runtime/secret-provided values authoritative without mutating
the image or the deployment config file.

This runtime config step may configure how the released image runs, but it must
not build the release. `odoo-run`, `odoo-init`, `odoo-update`,
`odoo-neutralize`, and `odoo-shell` must not fetch Git repositories, run
`gitaggregate`, install Python packages, mutate addons, or change the baked
source tree.

## Database Lifecycle Helpers

`odoo-run` is the normal long-running entrypoint.

When wrapping Odoo CLI subcommands, `odoo-run` preserves Odoo's command order:
`odoo-bin <command> -c <generated-config> ...`. Do not move `-c` before the
command; Odoo treats that as the default `server` command and rejects
subcommands such as `shell` or `neutralize`.

`odoo-init` is an explicit operator tool for the special case where a
PostgreSQL database exists but is completely empty and must be initialized as
an Odoo database:

```bash
odoo-init <database>
odoo-init <database> <modules>
```

The default module set is `base`, equivalent to running Odoo with
`-i base --stop-after-init --without-demo=all`.

`odoo-init` is deliberately not automatic. It is not run by the image entrypoint
and must not be embedded blindly in normal Deployments. Before initializing, it
connects to PostgreSQL using the same non-secret config and secret-file
conventions as `odoo-run` and refuses to proceed when:

- `ir_module_module` already exists, meaning the database is already an Odoo
  database;
- any non-system table exists but Odoo metadata is missing, meaning the database
  is ambiguous and should be inspected manually.

Use `odoo-update <database> <modules|all>` for already-initialized Odoo
databases.

Use `odoo-neutralize <database>` for preview/test copies restored from
production data:

```bash
odoo-neutralize <database>
odoo-neutralize <database> --stdout
```

It calls Odoo's standard `neutralize` command through `odoo-run`, so it uses the
same generated runtime config and Secret-file values as the normal container.
The command executes `data/neutralize.sql` from installed modules. This is real
Odoo neutralization, not only a banner. Odoo core disables scheduled actions
except the base autovacuum cron, disables real outgoing mail by replacing it
with a dummy SMTP host, sets the neutralization flag, and lets installed modules
apply their own neutralization SQL. This does not remove the need to review
custom connectors or third-party side effects before exposing a copied database
to users.

For Kubernetes, a one-off empty-DB smoke can run `odoo-init` inside an existing
Pod or in a dedicated Job that mounts the same ConfigMap and Secret files as
the normal Deployment. Do not run it during production cutover with restored
client databases.
