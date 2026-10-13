# fred-manager

Draft. Owns spaces, folders and documents, answers every access question with one
OpenFGA check, and submits ingestion work to the Python workers through Temporal.

## Model

- **Spaces**: organization > team > project. A personal space is a team with
  `personal_owner` set, one member, no project. Placement never changes.
- **Rights**: OpenFGA type `space` with direct roles `member`, `editor`, `admin`
  and no parent relation, plus `platform:root` for platform roles
  (`openfga/model.fga`). A role on a space requires read access to its parent;
  fred-manager refuses writes that would break this.
- **Folders**: classification only, no rights. `folder.path` is a chain of ids.
- **Documents**: one space, one folder, both immutable. Renames are free; a move is
  a re-import.
- **Derived artefacts** have no authorization identity of their own. Storage keys
  live under `<space_id>/<document_id>/`; every chunk carries `space_id`,
  `document_id` and `folder_path`, never a name.

| Question | OpenFGA call | Then |
| --- | --- | --- |
| Can Bob read document D? | `can_read` on D's space | none |
| Bob's agent searches from a BID conversation | `can_read` on BID | filter `space_id ∈ path(BID)` |
| Search within a folder | same | add `folder_path` prefix |

## Configuration

As in the Python backends: `config/configuration.yaml` (named by `CONFIG_FILE`) holds
the settings with the same sections and names (`app`, `security`, `storage.postgres`,
`scheduler.temporal`), and `config/.env` (named by `ENV_FILE`) holds the secrets only,
`FRED_POSTGRES_PASSWORD`, `OPENFGA_API_TOKEN` and `FRED_BOOTSTRAP_TOKEN`. Variables already set in the process
win over `.env`. The `FRED_STRICT_*` and `FRED_JWT_*` toggles keep their fred-core
meaning. The tables live in the shared `fred` database; none of fred's tables shares
their names.

At startup, as fred-core's OpenFGA engine does, fred-manager finds the store named
`security.rebac.store_name` (default `fred-manager`, never fred's own), creates it if
`create_store_if_needed`, and writes the model if `sync_schema_on_init`.

## Run

Same targets as the other apps (`make help` lists them):

```
cp config/.env.template config/.env   # fill the three secrets
make run                              # http://localhost:8400/fred-manager/v1
make create-org ORG_NAME=TSN ORG_ADMIN=<keycloak sub>
make test                             # offline unit tests
make code-quality                     # clippy + rustfmt
```

Building needs `protoc`; `PROTOC` defaults to `~/bin/tools/protoc/bin/protoc`. The
Makefile fragments are `scripts/makefiles/rust-*.mk`, mirroring the `python-*.mk` ones.
`GET /fred-manager/v1/healthz` is the only route without a bearer token.

## Two local stories (fred-deployment-factory)

- **`make docker-up`**: run fred-manager on the host with `make run`, `config/.env` and
  `config/configuration.yaml`. Postgres, Keycloak, OpenFGA and Temporal answer on the
  same localhost ports as with k3d, so the same files serve `make k3d-up` too.
- **`make k3d-up`**: deploy into the cluster from the factory, next to fred-app:

  ```
  make k3d-app DIR=../fred/apps/fred-manager            # build, import, sync
  make k3d-app-validate DIR=../fred/apps/fred-manager   # lint and render only
  make k3d-app-uninstall DIR=../fred/apps/fred-manager
  make k3d-logs SVC=fred-manager
  ```

  `deploy/k3d/` follows the factory's application contract: `helmfile.yaml.gotmpl`,
  `values.yaml` and `build`. The release `fred-manager` uses fred's chart with every
  other application disabled, both secrets from `fred-secrets`, and Traefik routing
  `http://localhost:8088/fred-manager`. `deploy/k3d/chart` is fred's chart through
  symlinks without `values.schema.json`, whose closed application list `helm lint`
  enforces even with `--skip-schema-validation`. It goes away when fred-manager joins
  the chart and its schema.

## Root platform admin

Same contract and same commands as the control-plane's root bootstrap. A fresh
deployment has no platform admin; the first one promotes themselves once, with two
independent proofs: their own verified bearer and the deploy-time secret.

```
make bootstrap-local BOOTSTRAP_USER=<you> BOOTSTRAP_PASSWORD=<pw>   # FRED_BOOTSTRAP_TOKEN from config/.env
```

`POST /fred-manager/v1/bootstrap/platform-admin {"token": ...}` grants `admin` on
`platform:root` to the caller only, then writes a durable marker in
`platform_bootstrap`: 403 for a wrong or unconfigured secret, 409 once completed (even
if every admin is later removed), 503 when authentication is disabled. The secret is a
secret like the others, read from the variable `app.bootstrap_token_env_var` names
(`FRED_BOOTSTRAP_TOKEN`): `config/.env` locally, and on k3d the control-plane's
`CONTROL_PLANE_BOOTSTRAP_TOKEN` from `fred-secrets`. Each service keeps its own marker,
so bootstrapping one never consumes the other.
`GET /fred-manager/v1/me` returns the caller's `platform_roles`. Platform roles grant no
access to any space's content.

## Authentication

Ported from fred-core `security/oidc.py`: every route requires
`Authorization: Bearer <access token>` from the UI's Keycloak client, verified
RS256 against the realm JWKS, with the same claims mapping (`sub` is the OpenFGA
user id, roles from `resource_access.<client_id>.roles`), the same 401 details, the
same lifetime ceiling and the same `security:` settings (`profile: c3`, `user`,
`m2m.realm_url`, `authorized_origins`).

Not ported yet, each needs its own decision: GCU acceptance, local identity
snapshot, account status, platform access rules, whitelist and delegated callers.
Deliberate differences: no token cache (verification is cheap here), `exp` is
required, and an empty subject is refused for every provider.

## Worker contract

fred-manager starts two workflows on `scheduler.temporal.task_queue`, JSON payloads,
workflow id `ingest-<document_id>` / `delete-<document_id>`:

- `IngestDocument { document_id, space_id, folder_path, storage_prefix, source_key, mime, profile, requested_by }`
- `DeleteDocument { document_id, space_id, storage_prefix }`

No Python worker implements them yet.

## Not in this draft

Uploading the source object, space deletion and search itself are out of scope.
