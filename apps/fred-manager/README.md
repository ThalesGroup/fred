# fred-manager

Fred's service for spaces, folders, documents and their authorization. Its design,
invariants and decisions are in the architecture dossier:
[docs/architecture](../../docs/architecture/README.md). This file says how to work on it.

## Develop

Same targets as the other apps (`make help` lists them). Building needs `protoc`;
`PROTOC` defaults to `~/bin/tools/protoc/bin/protoc`.

```
cp config/.env.template config/.env   # once: the four secrets
make run                              # http://localhost:8400/fred-manager/v1
make test                             # offline unit tests
make test-integration                 # throwaway Postgres and OpenFGA containers
make code-quality                     # model parity + clippy + rustfmt
make -C ../../docs/architecture check # the dossier still matches the code
```

## From scratch (fred-deployment-factory)

**Host run, after `make docker-up` or `make k3d-up`:**

```
make run
make bootstrap-local BOOTSTRAP_USER=<you> BOOTSTRAP_PASSWORD=<pw>
make create-org ORG_NAME=TSN ORG_ADMIN=<your user_id, from GET /me>
```

**In the cluster, after `make k3d-up`**, from fred-deployment-factory:

```
make k3d-app DIR=../fred/apps/fred-manager            # build, import, sync
make k3d-app-validate DIR=../fred/apps/fred-manager   # lint and render only
make k3d-logs SVC=fred-manager
make k3d-app-uninstall DIR=../fred/apps/fred-manager
```

Then, from apps/fred-manager, bootstrap the pod with the cluster's secret, regenerated
by every new cluster, and a token issued at `keycloak:8080`:

```
make bootstrap-local BOOTSTRAP_USER=<you> BOOTSTRAP_PASSWORD=<pw> \
  FRED_MANAGER_BASE_URL=http://localhost:8088/fred-manager/v1 \
  KEYCLOAK_REALM_URL=http://keycloak:8080/realms/app \
  FRED_BOOTSTRAP_TOKEN="$(kubectl --context k3d-fred -n fred get secret fred-secrets \
    -o jsonpath='{.data.CONTROL_PLANE_BOOTSTRAP_TOKEN}' | base64 -d)"
```

## Changing it

A change described in the dossier updates its chapter in the same commit. A test that
proves an invariant carries `// Proves: I<n>` above it. Applied migrations are never
edited; add a new one.

## Platform and space roles

`GET /me` reports effective platform roles. Platform administrators list direct grants
with `GET /users/platform-roles`, and grant/revoke with
`PUT`/`DELETE /users/{subject}/platform-roles/{role}`. Only the bootstrap root changes
`platform_admin`; its own grant is protected. `platform_observer`, `team_manager`,
`feature_manager` and `prompt_editor` are also supported.

Space roles are `member`, `editor`, `analyst` and `admin`. They are cumulative;
admin alone does not read content. The last admin of a non-personal space cannot be
revoked. Capability checks and their contracts are in the
[runtime chapter](../../docs/architecture/04-runtime.md#platform-administration-and-self-checks).

Directory-backed platform grants require the manager's service client. The factory
consumes `deploy/k3d/identities.yaml` during `k3d-app`; copy its generated
`KEYCLOAK_FRED_MANAGER_CLIENT_SECRET` from `fred-secrets` to the host `.env` when
running locally against that realm. `docker-up` alone does not provision this client.
The [deployment chapter](../../docs/architecture/07-deployment.md) describes configuration.
