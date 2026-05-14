# Tools

This directory contains repository/operator/CI utilities for OCI Odoo image
workflows.

These scripts are not runtime image content and are not copied into production
containers by default. They are run from the base repository, from CI, or from a
derived image repository by pointing `OCI_ODOO_BASE_REPO` at this repository.

## Scripts

### `lock-repos`

Generates `repos.lock.yaml` from `repos.yaml`.

It is deliberately conservative:

- plain `lock-repos` preserves existing locked SHAs;
- new refs are resolved and added to the lock;
- deleted refs are removed from the lock;
- no branch is moved just because upstream advanced;
- it does not run `gitaggregate`;
- it does not materialize source trees;
- it does not generate or refresh `requirements.lock.txt`.

Refresh is always explicit:

```bash
tools/lock-repos
tools/lock-repos --refresh-merge ./odoo <remote> <ref>
tools/lock-repos --refresh ./odoo
tools/lock-repos --refresh-all
```

Use `--refresh-merge` for the surgical case: move exactly one selected merge.
Use `--refresh <dest>` to move every merge under one aggregate destination. Use
`--refresh-all` to move all selected sources in the repository.

If a merge is being added for the first time, plain `lock-repos` is enough.

### `odoo-enterprise-import`

Dry-runs an Odoo Enterprise source ZIP or already extracted source directory
against the exact Community checkout selected by `repos.lock.yaml`.

This tool is the first step of the Enterprise mirror flow. It does not download
from odoo.com and it does not write Git commits yet. It answers the question:
"given this Enterprise payload and this locked Community source, which modules
are Enterprise candidates and can be reviewed before importing into the private
Enterprise Git repo?"

Example:

```bash
tools/odoo-enterprise-import \
  --zip /path/to/odoo-enterprise-17.zip \
  --community-src /path/to/materialized/src/odoo \
  --repos-lock repos.lock.yaml \
  --current-src /path/to/private/odoo-enterprise \
  --yes \
  --report-json workdir/enterprise-import-report.json
```

If the Odoo Enterprise download has already been extracted, use
`--download-src` instead of `--zip`:

```bash
tools/odoo-enterprise-import \
  --download-src /path/to/extracted/odoo-enterprise-download \
  --community-src /path/to/materialized/src/odoo \
  --repos-lock repos.lock.yaml \
  --current-src /path/to/private/odoo-enterprise \
  --yes
```

The report records three separate identities:

- `zip_sha256`: the downloaded Enterprise ZIP identity;
- `community_lock_revision`: the Community commit from `repos.lock.yaml`;
- `community_worktree_head`: the local Community checkout used for comparison.

The command fails when the Enterprise payload is not an exhaustive superset of
the locked Community source, or when the local Community checkout is not at the
locked revision. Matching Community modules that drift byte-for-byte are
reported as warnings because Odoo controls the ZIP generation and it may not
match our current Community lock exactly.

The normal safe Enterprise import workflow is to refresh the Community lock
first:

```bash
tools/lock-repos --refresh ./odoo
```

Then materialize/use that locked Community source. The importer intentionally
trusts the Community source passed with `--community-src` as the source of
truth: every downloaded module absent from that Community checkout is treated as
Enterprise. No manual module-classification file is used.

When run interactively, the command prints this Enterprise import rule and asks
for confirmation before continuing. The warning says plainly that the command
imports Enterprise as `downloaded Odoo source - Community source`; therefore an
outdated `--community-src` can make normal Community modules enter the private
Enterprise mirror by mistake. In scripts/CI, pass `--yes` to acknowledge that
warning explicitly and avoid a prompt.

The tool still reads each Enterprise module manifest with `ast.literal_eval`
and reports the manifest license as useful metadata, but license is no longer
used to decide whether a module is Enterprise. Community membership decides.

If `--current-src` points to the current private/internal source repository,
the report also contains an `import_plan` with dry-run actions:

- `add`: Enterprise modules not present in the current Enterprise source;
- `update`: Enterprise modules present in both places but with different tree
  hashes;
- `remove`: current Enterprise source modules absent from the current Enterprise
  set;
- `unchanged`: Enterprise modules already identical in the current Enterprise
  source.

The plan is still review-only. Removals must be reviewed before any future
`--apply` mode.

By default, the command prints a short human summary followed by the full JSON
report. Use `--json-only` when stdout must be machine-parseable JSON only.

The old local proof of concept for downloading from odoo.com proved the
separate acquisition mechanics: HTTP session warm-up, subscription JSON-RPC
check, and following the CDN payload link when Odoo returns an HTML download
page. Keep that acquisition step separate from Docker builds and from this
classification/import validation.

### `update-base-image-digest`

Updates the pinned digest in `images/runtime/Dockerfile` for the selected
upstream base image.

Default target for the current Odoo 17 line:

```text
repository: library/python
tag:        3.10.20-slim-trixie
dockerfile: images/runtime/Dockerfile
```

Override with environment variables:

```bash
DOCKERFILE=images/runtime/Dockerfile \
BASE_IMAGE_REPOSITORY=library/python \
BASE_IMAGE_TAG=3.10.20-slim-trixie \
tools/update-base-image-digest
```

The script currently implements Docker Hub's registry API. If another registry
is needed later, add a dedicated resolver mode rather than partially
parameterizing Docker Hub URLs.

## Safety Rules

- Do not put credentials, tokens, private keys, kubeconfigs, or secret values
  in this directory.
- Do not make runtime containers depend on these scripts.
- Do not use these scripts to hide source generation inside a running Odoo
  container.
- Keep release materialization in the builder/source-build flow. In particular,
  `gitaggregate` must run only once for a release source-build.
- Keep operator-local paths out of committed examples. Use variables such as
  `OCI_ODOO_BASE_REPO` for transferable commands.
