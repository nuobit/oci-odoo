# Secret Contracts

This directory documents the Secret names and keys that Odoo Deployments expect.
It must not contain Secret values.

Do not commit Kubernetes `Secret` manifests with `data` or `stringData` here.
For now, create real Secret values through the agreed vault/operator workflow.
Later, if the platform adopts a sealed/encrypted secret mechanism, document that
new workflow here before committing encrypted Secret material.

## Runtime Files

Each Odoo Pod receives two secret files:

```text
/run/secrets/odoo/db_password
/run/secrets/odoo/admin_passwd
```

`odoo-run` reads those files and generates `/run/odoo/odoo-runtime.conf` inside
the container. The generated runtime config is temporary Pod state and may
contain secrets, so it must never be stored in Git, baked into an image, logged,
or persisted on a PV.

## PostgreSQL Password Secrets

The database password comes from the PostgreSQL app-role Secret. These Secrets
are owned by the PostgreSQL bootstrap/restore workflow, not by the Odoo
Deployment manifests.

| Instance | Secret | Key | Mounted file |
|---|---|---|---|
| `<instance>` | `pg16-odoo17-<instance>` | `POSTGRES_PASSWORD` | `db_password` |

The matching `POSTGRES_USER` key may exist in those Secrets, but Odoo reads the
database user from the non-secret ConfigMap (`db_user = odoo17_<instance>`).
The Pod mounts only `POSTGRES_PASSWORD` as `db_password`.

## Odoo Admin Password Secrets

`admin_passwd` is Odoo's master password, also called the database-manager
password. It is not a normal Odoo user password.

Use the canonical Odoo config name `admin_passwd` for the Kubernetes key and the
mounted file. Do not create a separate `master_password` key for the same value.

| Instance | Secret | Key | Mounted file |
|---|---|---|---|
| `<instance>` | `odoo17-<instance>-admin` | `admin_passwd` | `admin_passwd` |

Create one independent value per business instance unless there is an explicit
operational reason to share it.

## Projected Volume Pattern

Deployments should project both Secret sources into one read-only mount:

```yaml
volumes:
  - name: odoo-secrets
    projected:
      defaultMode: 0440
      sources:
        - secret:
            name: pg16-odoo17-<instance>
            items:
              - key: POSTGRES_PASSWORD
                path: db_password
        - secret:
            name: odoo17-<instance>-admin
            items:
              - key: admin_passwd
                path: admin_passwd
```

Use `fsGroup: 1000` for the Pod so the `odoo` user can read the mounted Secret
files without running the main container as root.

## Operator Creation Example

Example shape only. The file path must point to a temporary file created from
the vault or a hidden prompt, with restrictive permissions, and removed after
`kubectl` consumes it.

```bash
kubectl -n <namespace> create secret generic odoo17-<instance>-admin \
  --from-file=admin_passwd=/path/to/temp/admin_passwd
```

Do not use shell history with literal passwords. Do not paste the value into a
committed file.

## Registry Pull Secrets

If the deployable image package is private, Kubernetes needs an
`imagePullSecret` in the same namespace as the Pods.

This is still a Kubernetes `Secret`, but it is not the same type as the generic
application password Secrets:

```text
PostgreSQL/Odoo password Secrets -> generic/Opaque application secrets
Private registry pull Secret     -> kubernetes.io/dockerconfigjson
```

For private registry pulls, use `kubernetes.io/dockerconfigjson`. It contains a
`.dockerconfigjson` key following the `~/.docker/config.json` registry
credential format. The older `kubernetes.io/dockercfg` format is legacy; do not
choose it for new work. A plain `Opaque` Secret is correct for application
passwords, but not the native `imagePullSecrets` registry format.

Use a client-controlled or operations-controlled technical actor for production
pull credentials, not a personal operator account.

For GHCR registry-client authentication (`docker login`, Kubernetes/containerd
image pulls), GitHub documents personal access token **classic** authentication
for GitHub Packages/GHCR. Start with:

```text
token type: classic PAT
scopes: read:packages
expiration: no expiration if policy allows; otherwise document rotation
```

If `read:packages` alone fails with a pull authorization error for a private
package, first verify package visibility, repository link, inherited access,
and account permissions. Add broader scopes such as `repo` only after a
reproduced failure and explicit approval.

Example shape:

```bash
read -rsp "GHCR pull token: " GHCR_TOKEN
echo
kubectl -n <namespace> create secret docker-registry ghcr-<owner>-pull \
  --docker-server=ghcr.io \
  --docker-username=<technical-github-username> \
  --docker-password="$GHCR_TOKEN"
unset GHCR_TOKEN
```

Verify only metadata:

```bash
kubectl -n <namespace> get secret ghcr-<owner>-pull \
  -o jsonpath='{.type}{" data="}{.data | length}{"\n"}'
```

Expected shape:

```text
kubernetes.io/dockerconfigjson data=1
```
