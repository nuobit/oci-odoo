# Odoo Kubernetes Deployment Scaffold

This scaffold is the starting point for a client deployment repository such as
`k8s-odoo-<client-key>`.

It is not part of the OCI image build. It describes how an already-built Odoo
image is executed: per-instance `odoo.conf`, Deployments, Services, Ingresses,
PVCs, Jobs, ConfigMaps, and references to Kubernetes Secrets.

## Runtime Config Boundary

The image repository owns immutable runtime artifacts:

```text
/opt/odoo/src
/opt/odoo/venv
/etc/odoo/addons_path
```

The deployment repository owns per-instance runtime configuration:

```text
instances/<instance>/odoo.conf
```

That `odoo.conf` must contain only non-secret execution settings. It must not
contain:

```text
addons_path
db_password
admin_passwd
```

At runtime, `odoo-run` merges:

```text
deployment odoo.conf via ODOO_BASE_CONFIG_FILE
  + image /etc/odoo/addons_path
  + Secret-file values
  = /run/odoo/odoo-runtime.conf
```

The generated `/run/odoo/odoo-runtime.conf` is temporary container state. It may
contain secrets because Odoo needs them while running, but it must not be stored
in Git, baked into images, persisted on a PV, logged, or passed on the command
line.

`/run/odoo` must be private to the `odoo` user (`0700`) and the generated config
must be `0600`. For a strict Kubernetes runtime, mount `/run/odoo` as a
memory-backed `emptyDir` while preserving that permission contract.

## Example Instance

Use `instances/instance1.example/odoo.conf` as the non-secret starting point
for each real Odoo instance. The directory name marks the sample as an example,
while the file name matches the real deployment shape:
`instances/<instance>/odoo.conf`.

In a real deployment repo, copy it to a concrete instance path, for example:

```text
instances/production/odoo.conf
instances/staging/odoo.conf
instances/test/odoo.conf
```

Then pass it to the container with `ODOO_BASE_CONFIG_FILE`.

## Kubernetes Wiring Example

`manifests/patterns/runtime-config-wiring.example.yaml` shows the generic
wiring pattern that is already decided:

- mount `odoo.conf` from a ConfigMap;
- mount `db_password` and `admin_passwd` from projected Secret files;
- mount `/run/odoo` as memory-backed `emptyDir`;
- prepare `/run/odoo` as `0700`, owned by UID/GID `1000`, before `odoo-run`
  writes the generated runtime config.

It is intentionally not a complete production manifest and should not be copied
verbatim into a concrete repo. Services, Ingresses, PVC names, probes,
resources, backup Jobs, and instance-specific labels belong to each concrete
deployment repository.

Replace `ghcr.io/<owner>/<image-repo>:...` with the concrete deployable image
tag. For a client-owned image repo, `<image-repo>` may simply be `oci-odoo`
inside that client's GitHub organization.

Concrete invented example:

```text
ghcr.io/examplecorp/oci-odoo:17.0-py310-trixie-r0001
```

Before deploying a private image, verify its GHCR package settings:

```text
Repository link:
  package is linked to the image source repository

Inherited access:
  "Inherit access from source repository" is enabled

Visibility:
  private client image packages stay Private
  public foundation image packages are Public if anonymous pulls are expected
```

If inherited access shows `0 members`, that only means there are no direct
package-level member grants; inherited access still comes from the linked
source repository.

If the deployable image package is private, Kubernetes needs a namespace-scoped
`imagePullSecret` with read access to that package. This is independent from the
operator's local Git credentials and from Odoo/PostgreSQL runtime secrets.

The Secret-name/key contract is documented in:

```text
manifests/secrets/README.md
```

`admin_passwd` is Odoo's master password / database-manager password. Keep the
canonical Odoo config name `admin_passwd`; do not create a separate
`master_password` key for the same value.
