# RFC — Platform Import/Export (swift-native contract)

**ID:** MIGR-05 · **Status:** in progress — swift-native path shipped + hardened (baseline 2026-07-16);
kea-import path deferred, see §8.
**Owner:** Dimitri · **Surface:** control-plane-backend (`import_export/`)
**Extends:** [`TASK-EVENT-STREAM-RFC.md`](TASK-EVENT-STREAM-RFC.md) (task/event infra).
**Backlog:** [`KEA-MIGRATION-BACKLOG.md`](../backlog/KEA-MIGRATION-BACKLOG.md) §0bis — migration
vocabulary (identity/data/metadata/products topics) is defined there; this RFC is the **metadata**
topic.
**History:** this file states the current contract only. Full design/implementation history
(architecture deviations, live-validation evidence, review threads) is in
`git log -p -- docs/swift/rfc/PLATFORM-IMPORT-RFC.md`, not inline here.

---

## 1. What this is

An admin-only, atomic export/import of a swift instance's configuration graph — agent instances,
tags, document metadata, team metadata, and (via a separate `users.json` bundle entry) declarative
team/platform role provisioning. Used to clone/restore an instance's configuration, and as the
swift side of the Kea→Swift migration's metadata step.

**Endpoints** (`/control-plane/v1/import-export/`, all `require_admin` + `CAN_MANAGE_PLATFORM`):
- `POST /import` — multipart zip → async task; atomic import.
- `GET /export` — download a swift-native snapshot (`source_platform=swift`), re-importable
  through the same endpoint.
- `POST /reset` — atomic wipe of agents+tags+metadata (enables export → reset → import test
  cycles; Keycloak / OpenFGA / object store untouched).
- `GET /stats` — platform overview (teams, members by role, agents, prompts) — powers the
  **Platform data** admin page.

**Module:** `control_plane_backend/import_export/{bundle,exporter,importer,agent_map,stats,schemas,api}.py`.

**Architecture:** a single atomic SQLAlchemy transaction inside a FastAPI `BackgroundTask` — not
Temporal. For a config-sized payload (one shared Postgres DB, sub-megabyte zip), this is simpler
and gives a stronger guarantee than per-activity retries: agents + tags + metadata commit together
or roll back together, idempotent by primary key. Revisit a Temporal-workflow design only if
binaries/embeddings ever enter this bundle (they currently never do — see §2).

## 2. Scope

**In scope — the config graph only:** agent instances, tags, document metadata, team metadata,
declarative team/platform role provisioning (`users.json`). OpenFGA tuple restore exists only on
the kea-import path today (§8).

**Conflict policy:** fresh-target only for Postgres rows — no upsert, no merge. Idempotent by
primary key (re-running a bundle over already-imported rows skips them). `users.json` role grants
are separately idempotent (`RebacEngine.add_relation(on_duplicate_writes=IGNORE)`).

**Explicitly and permanently out of scope — never transported by this bundle:**
- **Document binaries** (MinIO/S3) — moved separately, key-for-key, via `mc mirror` (MIGR-06).
- **Vector embeddings** (OpenSearch) — rebuilt on the target via re-vectorize (MIGR-07), never
  transported.
- **Conversations / sessions / message history.**
- **MCP server rows** — re-seeded by deployment, not carried in the bundle.

## 3. Bundle format (swift-native)

```
manifest.json                        # see §4
postgres/
  agent_instance.jsonl
  tag.jsonl
  metadata.jsonl
  team_metadata.jsonl
users.json                           # optional, top-level, sibling of manifest.json — see §6
```

(The kea-import path reads a different, wider set of `postgres/*.jsonl` tables plus
`openfga/tuples.json` — §8.)

## 4. Manifest contract — versioned, validated

`manifest.json` is parsed into `bundle.py::SnapshotManifest`, a Pydantic model.
`open_bundle()` **rejects** any bundle whose `format_version` or `users_schema_version` isn't in
the set this importer understands (today: `{1}` for both) — no silent default when a key is
absent or unrecognised.

Two version numbers, tracked independently because they evolve at different rates:
- **`format_version`** — the container's own shape: which top-level files/tables exist.
- **`users_schema_version`** — `BundleUserEntry`'s field set (`schemas.py`), which has already
  grown once (identity fields, §6) independent of any container change.

Fields: `format_version: int` (required) · `users_schema_version: int = 1` ·
`source_platform: str = "kea"` · `created_at: str` · `tables: dict[str, int]` ·
`tuple_count: int` · `realm_exported: bool` · `content_keys: list[str]`.

`source_platform` is the live discriminator: `"swift"` takes the swift-native branch (this
document); anything else takes the kea-import branch (§8).

## 5. Content honesty — track binaries/embeddings, never embed them

The bundle never carries document binaries or vector embeddings (§2) — but it must not silently
imply they're already handled on the target:

- **`content_keys`** — every exported document's `document_uid` (`exporter.py::run_export`). On
  import, a non-empty `content_keys` adds one `report.warnings` entry naming the count — a
  reminder that these documents need their binaries mirrored separately (MIGR-06), **not** a
  per-document presence check (there is no cross-backend call from control-plane into
  knowledge-flow's content store).
- **Stage reconciliation** — `importer.py::_reset_transported_stages` resets `VECTORIZED` and
  `SQL_INDEXED` to `NOT_STARTED` on every restored `metadata` row, since embeddings/SQL indexes
  are never transported. `PREVIEW_READY` is left untouched — trusted present, given the
  MIGR-06-before-MIGR-05 ordering guarantee. A re-vectorize pass (MIGR-07) is required after
  import to make search work again; it is not yet auto-triggered.

## 6. `users.json` — declarative team/platform role provisioning

A top-level `users.json` (sibling of `manifest.json`), a JSON array with one entry per identity
(`schemas.py::BundleUserEntry`):

```json
[{"username": "alice", "email": "alice@app.com", "first_name": "Alice", "last_name": "Watson",
  "password": "Azerty123_", "teams": [], "team_roles": {"team_admin": ["fredlab"]},
  "platform_roles": ["admin"]}]
```

- `username: str` required.
- `email` / `first_name` / `last_name` / `password: str | None = None` — identity-phase fields,
  all optional.
- `teams: list[str]` / `team_roles: dict[str, list[str]]` / `platform_roles: list[str]` —
  role-phase fields.

**Two phases** (`importer.py::_run_users_phase`), always in this order:

1. **Identity** (`_provision_bundle_identities`) — creates a Keycloak user via the existing
   `users/service.py::create_user` only if **both** hold: no existing identity resolves by
   username, **and** the entry carries a `password`. No `password` → assumed to already exist,
   never force-created. Requires Keycloak Admin M2M credentials configured; if not configured,
   fails loudly (no silent skip) for any entry that needs one.
2. **Role** — resolves `username` → Keycloak `sub` (read-only lookup), then grants:
   - **`platform_roles`** (`"admin"` → `platform_admin`, `"observer"` → `platform_observer`) via a
     private `_grant_platform_role` helper — the only path that can grant a platform role to a
     **third party** (every other path is self-promotion-only). Gated solely by the route's
     existing `CAN_MANAGE_PLATFORM` check; no second authorization check added.
   - **`team_roles`/`teams`** via `_grant_team_role_via_import`, a private reconciliation
     primitive (direct `RebacEngine.add_relation`) — deliberately bypasses the ordinary,
     `team_admin`-gated `grant_team_member_role` API, since the importer is never expected to
     already hold `team_admin` on every team a bundle touches. A brand-new team's *initial*
     `team_admin`(s) are instead seeded at `create_team` time. The ordinary team-membership APIs
     are unchanged and still `team_admin`-gated (regression-tested against this importer identity).
   - Semantics: multiple roles on the same team are cumulative (all persisted as direct tuples). A
     team with any explicit role never also gets a redundant direct `team_member` tuple —
     `schema.fga` already derives `team_member` as a union over the explicit roles.

**Fail-closed, not warn-and-succeed.** `BundleProvisioningError` aborts the whole users phase
(→ the import task fails, never a silently-partial `succeeded`) for: ReBAC disabled; an unknown
`team_roles`/`platform_roles` value; a username still unresolved after the identity phase; a team
referenced by the bundle that has no `team_admin` declared for it anywhere in the same bundle (so
it cannot be created). Idempotent: re-running an already-reconciled bundle re-writes the same
tuples with no error and no duplicate.

## 7. Observability

The terminal task event carries a structured `MigrationResult`
(`fred_core.tasks.models`, populated via `importer.py::to_migration_result`) — every counter
(`agents_imported`, `docs_imported`, `teams_provisioned`, `team_roles_granted`,
`platform_roles_granted`, …) plus `warnings`. A `succeeded` task with non-empty `warnings` is a
partial reconciliation, distinguishable from a clean success — durable across reload
(`GET /tasks` returns the same structured `detail`), not just visible on the terminal event.

## 8. Deferred — tracked separately, not part of this contract

- **Kea-import path** (`source_platform=kea`) — reads a wider `postgres/*.jsonl` set plus
  `openfga/tuples.json`, transforms kea agents via `agent_map.py`. OpenFGA tuple restore
  (**MIGR-05.04**) and agent prompt transfer (**MIGR-05.11**) remain open. Tracked in
  [`KEA-MIGRATION-BACKLOG.md` §0bis](../backlog/KEA-MIGRATION-BACKLOG.md).
- **Re-vectorize auto-trigger after import** (MIGR-07) — the stage reset in §5 is inert until
  something consumes it.
- **Per-document content-store presence verification** (§5) — currently a count-only reminder,
  not a real check.
