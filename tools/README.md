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

### `odoo-enterprise-download`

Downloads an Odoo Enterprise source bundle from Odoo's official download
portal.

This is an acquisition tool only. It does not classify modules, does not import
Enterprise source into Git, and must never run inside Docker builds. The normal
flow is:

```text
odoo-enterprise-download -> source bundle + sha256
odoo-enterprise-import   -> private Enterprise Git mirror/cache
repos.yaml/repos.lock    -> normal image build
```

Example using a private subscription-code file:

```bash
tools/odoo-enterprise-download \
  --platform-version src_17e \
  --subscription-code-file ~/.config/oci-odoo/navalen/odoo-enterprise-subscription-code \
  --output-dir workdir/downloads \
  --report-json workdir/enterprise-download-report.json
```

The subscription code can be supplied in four ways:

- `--subscription-code-file`: recommended for automation. The file must be
  private (`chmod 600` or `chmod 400`).
- hidden interactive prompt: recommended for one-off manual runs.
- `ODOO_ENTERPRISE_SUBSCRIPTION_CODE`: acceptable for controlled CI/operator
  environments.
- `--subscription-code`: supported but not recommended because command-line
  arguments can leak through shell history and process listings.

The command prints and records:

- downloaded source bundle path;
- source bundle type;
- byte size;
- `sha256`;
- Odoo subscription-check result.

It does not write or print the subscription code. `--debug-http` redacts query
values from URLs before printing HTTP diagnostics.

Do not assume the source download is a ZIP. For `src_17e`, Odoo returned a
gzip-compressed TAR source bundle in May 2026. The downloader validates the payload as
a supported source bundle and records the detected type.

### `odoo-enterprise-import`

Inspects or imports an Odoo Enterprise source bundle or already extracted
source directory against the exact Community checkout selected by
`repos.lock.yaml`.

This tool is the Enterprise mirror import flow. It does not download from
odoo.com. By default it is a dry-run and answers the question: "given this
Enterprise payload and this pinned official Community source, which modules are
Enterprise candidates and what would change in the private Enterprise Git
repo?" With `--apply`, it writes those changes into a clean local Enterprise
Git worktree.

Example:

```bash
tools/odoo-enterprise-import \
  --source-bundle /path/to/odoo-enterprise-17.tar.gz \
  --community-src /path/to/materialized/src/odoo \
  --repos-lock repos.lock.yaml \
  --current-src /path/to/private/odoo-enterprise \
  --report-json workdir/enterprise-import-report.json
```

If the Odoo Enterprise download has already been extracted, use
`--download-src` instead of `--source-bundle`:

```bash
tools/odoo-enterprise-import \
  --download-src /path/to/extracted/odoo-enterprise-download \
  --community-src /path/to/materialized/src/odoo \
  --repos-lock repos.lock.yaml \
  --current-src /path/to/private/odoo-enterprise
```

The report records three separate identities:

- `source_bundle_sha256`: the downloaded Enterprise source bundle identity;
- `community_lock_revision`: the Community commit from `repos.lock.yaml`;
- `community_worktree_head`: the local Community checkout used for comparison.

Reports are intended to be safe for private Git metadata commits. They must not
store operator-local absolute paths such as laptop home directories, temporary
directories, or case workdirs. Source arguments such as `--source-bundle`,
`--download-src`, `--community-src`, and `--current-src` are represented by
stable hashes, commits, placeholders, and module-relative paths instead.

The command fails when the Enterprise payload is not an exhaustive superset of
the pinned official Community source, or when the local Community checkout is
not at the pinned revision. Matching module names whose Enterprise source bundle copy
differs byte-for-byte from the pinned official Community source are reported as
Enterprise source bundle drift.

The normal safe Enterprise import workflow is to refresh the Community lock
first:

```bash
tools/lock-repos --refresh ./odoo
```

Then materialize/use that pinned Community source. The importer intentionally
trusts the Community source passed with `--community-src` as the source of
truth: every downloaded module absent from that Community checkout is treated
as Enterprise. No manual module-classification file is used.

The importer never asks interactive risk-confirmation questions. Risky states
fail with a clear error and require an explicit flag on the next run. Enterprise
source bundle drift aborts by default. If the operator has refreshed Community,
reviewed the listed modules, and accepts the drift, rerun with `--allow-drift`.

The tool still reads each Enterprise module manifest with `ast.literal_eval`
and reports the manifest license as useful metadata, but license is no longer
used to decide whether a module is Enterprise. Community membership decides.

If `--current-src` points to the current private/internal source repository,
the report also contains an `import_plan` with actions:

- `add`: Enterprise modules not present in the current Enterprise source;
- `update`: Enterprise modules present in both places but with different tree
  hashes;
- `remove`: current Enterprise source modules absent from the current Enterprise
  set;
- `unchanged`: Enterprise modules already identical in the current Enterprise
  source.

Default mode is review-only. To apply the plan, point `--current-src` at a
clean local checkout of the private Enterprise Git repo and pass `--apply`:

```bash
tools/odoo-enterprise-import \
  --source-bundle /path/to/odoo-enterprise-17.tar.gz \
  --community-src /path/to/materialized/src/odoo \
  --repos-lock repos.lock.yaml \
  --current-src /path/to/private/odoo-enterprise \
  --apply \
  --report-json workdir/enterprise-import-report.json
```

Apply mode creates:

- one commit per added Enterprise module;
- one commit per updated Enterprise module;
- one commit per removed Enterprise module;
- one final metadata commit under `.enterprise-imports/`.

Removals require the explicit `--apply-removals` flag. This prevents accidental
deletion when a stale or incomplete Enterprise download is reviewed too quickly.
The command refuses to apply if `--current-src` is not a clean Git worktree.

Enterprise source bundle drift requires the explicit `--allow-drift` flag. The
importer is an Enterprise tool, so the short flag name is enough; the error text
spells out that the drift is the source bundle's embedded Community copy differing
from the freshly pinned official Odoo Community source.

When drift appears, the first response is to refresh Community and rerun. If
drift remains, review the affected module as embedded-Community drift, not as a
candidate Enterprise module. A strong review pattern is:

1. compare the source bundle module against the refreshed Community module;
2. list the files that differ;
3. inspect the latest official Community commit(s) touching those files;
4. compare source bundle file hashes against the parent of the latest Community
   commit.

The 2026-05-14 `l10n_jo_edi` drift validated this model. The Enterprise source bundle
files for `models/account_edi_xml_ubl_21_jo.py` and three XML test fixtures
matched the parent of Community commit `1601de2198ed...`, while refreshed
Community contained the newer fix. Therefore the module remained Community and
the import continued with `--allow-drift`.

When Community source has Git history, drift errors include a per-module
diagnosis block. The diagnostic is informational only; it never accepts drift
automatically. Possible diagnosis values:

- `source_bundle_lag_confirmed`: the source bundle copy matches the Community state
  immediately before a newer Community commit touching the drifted file(s);
- `unexplained_drift`: the source bundle copy does not match the checked recent
  Community ancestors;
- `limited_context`: the Community source has no Git history available, so the
  tool can list files and timestamps but cannot inspect commits.

All diagnostic timestamps are UTC ISO 8601 values ending in `Z`. The JSON report
stores this information under `enterprise_drift_details`.

By default, the command prints a short human summary followed by the full JSON
report. Use `--json-only` when stdout must be machine-parseable JSON only.

The download/acquisition step belongs in `odoo-enterprise-download`. Keep that
step separate from Docker builds and from this classification/import
validation.

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
