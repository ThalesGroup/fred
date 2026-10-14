# fred-manager

Fred's service for spaces, folders, documents and their authorization. Its design,
invariants and decisions are in the architecture dossier:
[docs/architecture](../../docs/architecture/README.md). This file says how to work on it.

## Develop

Same targets as the other apps (`make help` lists them). Building needs `protoc`;
`PROTOC` defaults to `~/bin/tools/protoc/bin/protoc`.

```
cp config/.env.template config/.env   # once: the three secrets
make run                              # http://localhost:8400/fred-manager/v1
make test                             # offline unit tests
make test-integration                 # throwaway Postgres and OpenFGA containers
make code-quality                     # clippy + rustfmt
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
