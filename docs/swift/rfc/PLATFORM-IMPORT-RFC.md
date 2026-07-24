# RFC — Platform Import/Export (swift-native contract)

**ID:** MIGR-05 · **Status:** in progress — swift-native path shipped + hardened (baseline 2026-07-16);
kea-import path implemented 2026-07-24 (agent prompt/tuning transfer, chat-context→prompt
migration, OpenFGA tuple restore with role transformation), see §8.
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

Fields: `format_version: int` (required) · `users_schema_version: int` (required) ·
`source_platform: str = "kea"` · `created_at: str` · `tables: dict[str, int]` ·
`tuple_count: int` · `realm_exported: bool` · `content_keys: list[str]`. Both version fields are
required on **every swift-produced** bundle, whether or not it carries a `users.json` — a swift
bundle producer that omits either fails loudly at `open_bundle()`, never silently assumed to be
`v1`. **Kea exception (2026-07-24):** kea's exporter (main branch, `migration/snapshot.py`)
predates `users_schema_version` and never emits it — and kea bundles never carry a `users.json` —
so `open_bundle()` defaults the field to `1` when `source_platform != "swift"` only. Verified
against a real kea dump (2026-07-22), which was rejected before this exception existed.

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

## 8. Kea-import path (`source_platform=kea`) — implemented 2026-07-24 (#1954)

Reads main's `postgres/*.jsonl` set (table file names = main's
`migration/snapshot.py::EXPORT_TABLES`, e.g. `teammetadata`, not `team_metadata`) plus
`openfga/tuples.json`. Validated end-to-end against a real kea dump (2026-07-22). Behaviour:

- **Agents** (`agent_map.py` + MIGR-05.11): classified MAPPED/IGNORED/GAP as before; legacy
  `type=leader` rows skipped. A MAPPED agent now carries its real kea tuning — `role`,
  `description`, `tags`, and the customized system prompt (`system_prompt_template` (v2) or
  `prompts.system` (v1) from `payload_json.tuning.fields[].default`) written to
  `tuning.values["prompts.system"]`, the key the runtime overlays onto the template's system
  prompt (`fred_runtime/app/agent_app.py`). `prompt_refs_json` is deliberately left unset — it has
  no consumer today, and kea agent prompts were never library entries. v1 secondary per-node
  prompts (`prompts.grade_*`, …) have no swift field → warned, not silently dropped.
  `created_by` comes from the agent's `user:… owner` tuple (personal agents).
- **Chat contexts → prompts:** kea `resource` rows with `resource_type="chat-context"` become
  `prompt` rows in the author's personal space (`personal-{author}`), decision 2026-07-24:
  personal space only, kea library sharing dropped. YAML front-matter is stripped from
  `doc.content` (only the body is the prompt text); `prompt_id` = kea `resource_id` (idempotent);
  `(team_id, name)` collisions get a short id suffix. Other kea resource kinds
  (`prompt`, `template`) are skipped with a warning. Kea library **tags**
  (`type ∈ {chat-context, prompt, template}`) are filtered out of the tag phase.
- **OpenFGA tuple restore (MIGR-05.04)** — `importer.py::transform_kea_tuples` replaces the
  former "ops bulk-copy" plan, which would have pushed relation names the swift model rejects.
  Role mapping (approved 2026-07-24): `owner → team_admin + team_editor` (kea owner was
  hierarchical; swift roles are orthogonal), `manager → team_editor`, `member → team_member`
  (only when the user holds no elevated role — `team_member` is union-derived). `team_analyst`
  is never synthesized. Dropped (counted + warned): tuples touching kea's shared `team:personal`
  (swift self-heals per-user `personal-{uid}` spaces), `resource#parent` (resources became prompt
  rows, no OpenFGA object), non-UUID user subjects (pre-MIGR-04 username tuples), unknown shapes.
  `agent`/`tag`/`document` ownership and `team#organization`/`team#public` replay 1:1. Writes go
  through `RebacEngine.add_relation` (idempotent, audited), outside the DB transaction.
- **Teams from the realm export:** kea materialises a `teammetadata` row only for customized
  teams, and the row has no `name` (kea team names live in Keycloak groups). The importer now
  creates a swift `teammetadata` row for **every** tuple-referenced team: name ← the bundled
  `keycloak/realm.json` groups (`_realm_group_names`), customization merged from the kea row when
  present, `joining_mode` defaulted. Bundle without a realm export → teams are named by their id,
  with a warning naming them. Ops fallback when the kea realm export is unavailable: extract
  `keycloak_group(id, name)` straight from the Keycloak DB.
- **Platform roles from the realm export:** kea platform roles are per-user Keycloak realm roles
  (`admin`/`editor`/`viewer`), never tuples. When the bundle carries a FULL realm export
  (`kc export --users`, i.e. `users[]` with `realmRoles`), the importer grants
  `admin → platform_admin` and `viewer → platform_observer` (`editor` dropped with a warning).
  A partial-export has no `users[]` → grants must then come from `users.json` (§6) or bootstrap.
- **Manifest:** kea bundles get `users_schema_version` defaulted (§4).
- **Still skipped:** `mcp-server` rows (re-seeded by deployment; per-agent MCP activation via
  capabilities is a follow-up), `users` rows (GCU acceptance state — product decision pending),
  `keycloak/realm.json` (identity = MIGR-04, ops), `content/` banners (kea teammetadata carried
  none in the validated dump — revisit if a prod bundle ships banners).

Open follow-ups: kea-side realm-export 403 (`manage-realm` alone is not enough for
`exportClients=true` — grant `view-clients` or export without clients) so prod bundles actually
carry `realm.json`; tuple/prompt counters surfaced only via the summary line and `warnings`, not
yet promoted to `MigrationResult` (OpenAPI + generated-client regen); `react_profile_id`-aware
template mapping refinement in `agent_map.py`; GCU `users` rows import (product decision).

## 9. Deferred — tracked separately, not part of this contract

- **Re-vectorize auto-trigger after import** (MIGR-07) — the stage reset in §5 is inert until
  something consumes it.
- **Per-document content-store presence verification** (§5) — currently a count-only reminder,
  not a real check.
- **Full-team export zip for the platform team** — #1954 task 2, untouched by the kea path work.
