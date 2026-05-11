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
