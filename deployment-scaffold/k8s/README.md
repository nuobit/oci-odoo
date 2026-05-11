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

Use `instances/example/odoo.conf.example` as the non-secret starting point for
each real Odoo instance. In a real deployment repo, copy it to a concrete
instance path and name it `odoo.conf`, for example:

```text
instances/production/odoo.conf
instances/staging/odoo.conf
instances/test/odoo.conf
```

Then pass it to the container with `ODOO_BASE_CONFIG_FILE`.

## Kubernetes Wiring Example

`manifests/runtime-config-wiring.example.yaml` shows the generic wiring that is
already decided:

- mount `odoo.conf` from a ConfigMap;
- mount `db_password` and `admin_passwd` from a Secret;
- mount `/run/odoo` as memory-backed `emptyDir`;
- prepare `/run/odoo` as `0700`, owned by UID/GID `1000`, before `odoo-run`
  writes the generated runtime config.

It is intentionally not a complete production manifest. Services, Ingresses,
PVC names, probes, resources, backup Jobs, and instance-specific labels belong
to each concrete deployment repository.

Replace `ghcr.io/<owner>/<image-repo>:...` with the concrete deployable image
tag. For a client-owned image repo, `<image-repo>` may simply be `oci-odoo`
inside that client's GitHub organization.

Concrete invented example:

```text
ghcr.io/examplecorp/oci-odoo:17.0-py310-trixie-r0001
```
