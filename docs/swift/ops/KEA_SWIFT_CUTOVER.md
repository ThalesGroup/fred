# Kea to Swift Cutover

**Status:** production runbook for the Kea → Swift cutover

**Tracking:** GitHub issue `#2133` (`swift-golive`)

**Canonical contract:** [`../design/CONTROL-PLANE-PRODUCT-CONTRACT.md`](../design/CONTROL-PLANE-PRODUCT-CONTRACT.md) §27 and §31

This runbook describes the current, deliberately narrow migration strategy. It
does not create, update, or delete Keycloak users.

## Target State and Inputs

Before the application import starts, Swift has:

- one root administrator in target Keycloak;
- empty control-plane Postgres application tables;
- empty OpenFGA application relations except the root bootstrap relation;
- document content already mirrored to the target object store;
- search/vector products prepared according to the separate corpus migration
  procedure.

The application import requires two files:

1. the Kea snapshot ZIP produced by the Kea migration export;
2. a reconciliation JSON extracted read-only from the Kea Keycloak Postgres
   database.

The second file is passed as multipart field `realm_file`. It replaces the
realm JSON inside the ZIP completely; the two documents are never merged.

> [!IMPORTANT]
> As of 2026-07-28, `open_bundle()` refuses the request outright when a
> `realm_file` is supplied without a non-empty `groups` **and** a non-empty
> `users` array — `UnsupportedBundleFormatError`, surfaced as the task's
> failure message on `POST /import`, as an HTTP error on `POST
> /kea-migration/dry-run`. Nothing is written in either case. This is
> deliberate: a hand-built `realm_file` (SQL extraction, not a real Keycloak
> export) missing one of these two keys is always a mistake for a cutover-scale
> Kea source, never an intentional shape — so the import stops instead of
> proceeding degraded. Fix the SQL/query output and retry; there is no partial
> or force-through option.
>
> This hard rule applies **only** to a `realm_file` uploaded independently —
> the zip's own bundled `keycloak/realm.json` (a genuine, official Keycloak
> partial export, which legitimately never carries `users[]`) keeps the older,
> degraded-but-tolerated behavior described in the table below. This runbook's
> procedure always uploads a `realm_file`, so that older behavior does not
> apply here.

## Source-Side Handoff Gate

This is the mandatory handoff checklist for the people extracting identity
evidence from the source Kea Keycloak database. Its output is always named
`kea-realm-reconciliation.json`; do not call it `users.json`, because users
alone are insufficient. The file also carries team identities, memberships,
and platform roles.

The source-side producer must:

1. freeze source identity and group mutations for the duration of the
   extraction;
2. confirm that the source realm is `app` and inspect the schema listed in
   [Read-Only Postgres Extraction](#read-only-postgres-extraction);
3. run the reviewed SQL from that section without hand-editing its JSON output;
4. run every command in [Validate Both Inputs](#validate-both-inputs);
5. compare the reported group, human-user, membership, and platform-role counts
   with independently measured source counts;
6. produce the checksum only after all validations pass:

   ```bash
   sha256sum kea-realm-reconciliation.json \
     > kea-realm-reconciliation.json.sha256
   ```

The handoff consists of exactly:

- `kea-realm-reconciliation.json`, transferred through the approved secure
  channel;
- `kea-realm-reconciliation.json.sha256`;
- the recorded count summary produced by the validation section;
- confirmation that all duplicate checks printed nothing.

The Swift-side receiver must verify the checksum and rerun the validation
commands locally before opening the migration page or calling its API:

```bash
sha256sum --check kea-realm-reconciliation.json.sha256
```

Do not hand-edit the JSON to repair a failed check. Correct or explicitly adapt
the source SQL, review the adaptation, and extract again. Do not proceed to
Swift if the checksum fails, a validation command fails, a duplicate command
prints anything, a membership names an unknown group, or a source count cannot
be reconciled.

## Required Reconciliation JSON — exact field contract

The root object has exactly two keys the importer reads: `groups` and `users`.
No other top-level key is read. Every field below has a fully specified
behavior for every case — present, absent, wrong type, empty. There is no
undefined behavior in this table.

**Root object**

| Key | Type | If absent, not an array, or empty |
| --- | --- | --- |
| `groups` | array | **Via `realm_file` (this runbook): the request is rejected outright, nothing written.** Via the zip's own `keycloak/realm.json` only: treated as `[]` — every team known only through `openfga/tuples.json` is dropped as an orphan reference. |
| `users` | array | **Via `realm_file` (this runbook): the request is rejected outright, nothing written.** Via the zip's own `keycloak/realm.json` only: treated as `[]` — every Kea `sub` referenced anywhere in the bundle resolves to PENDING for this run (deferred, applied automatically on a later re-run, nothing lost). |

**Each entry of `groups[]`**

| Field | Type | Required | Exact rule | If missing, empty, or wrong type |
| --- | --- | --- | --- | --- |
| `id` | string | Yes | Must equal the id already used as `team:<id>` in `openfga/tuples.json` and/or as `teammetadata.jsonl`'s own `id` — this is the join key, not an arbitrary label. | This group entry is invisible to the import — exactly as if it were not in the file. |
| `name` | string | Yes | Restores the team's display name; Kea's `teammetadata` table has no name column. | The team is still created (its `id` is still known), but named after its own id instead of a human name, and the report adds a warning line ("N team(s) have no name in the bundle"). |
| `subGroups` | array | No | Same 3-field shape, recursed. Real Kea teams are always root groups — this exists defensively, and should be `[]` for genuine Kea data. | Treated as `[]`. No effect. |

Only root groups (no parent) belong here — a Kea team is a root Keycloak
group by definition. A non-root group is not a Fred team and must not be
included.

**Personal spaces never belong in `groups[]`.** Every user has a personal
space on both Kea (the shared pseudo-team id `personal`) and Swift
(`personal-{uid}`, one per user). Neither is a real Keycloak group, neither
is ever included here, and neither needs to be — Kea's shared `personal`
team reference is dropped outright by the import (never translated), and
Swift's `personal-{uid}` space self-heals automatically on first use. Do not
add an entry for it; there is nothing to extract for it from Postgres.

**Each entry of `users[]`**

| Field | Type | Required | Exact rule | If missing, empty, or wrong type |
| --- | --- | --- | --- | --- |
| `id` | string | Yes | The Kea Keycloak `sub` (`user_entity.id`). Join key for every reference to this person elsewhere in the bundle. | — |
| `username` | string | Yes | Matched case-sensitively against the live target Swift Keycloak at import time to resolve the Swift `sub`. | — |
| `id` / `username` (either one) | — | — | — | The entire user entry is silently excluded from identity resolution. Every reference to this person's Kea `sub` anywhere else in the bundle resolves to PENDING — identical to that person simply not being in the file at all. |
| `groups` | array of strings | No | Each entry is a group path; a leading `/` is stripped if present but not required — `"team-name"` and `"/team-name"` are equivalent. The resulting string must match, byte-for-byte and case-sensitively, the corresponding `groups[].name` above — plain string equality, not lookup by id. | Treated as `[]`. That person gets zero plain `team_member` grants derived this run. A mismatched string (typo, case, stray whitespace) silently drops that one membership — no warning. |
| `realmRoles` | array of strings | No | Normalized output field populated from either source realm roles or source `clientRoles.app`. Exactly three case-sensitive values have any effect: `"admin"` → `platform_admin`, `"viewer"` → `platform_observer`, `"editor"` → dropped and reported as a warning. A user may hold both `"admin"` and `"viewer"` at once; both grants apply, nothing here enforces exclusivity. | Treated as `[]`. No platform-role grant for that person this run. Any string other than the three exact values above (including a different case, e.g. `"Admin"`) is silently ignored — no effect, no warning. |

Expected shape — every field in this example is read exactly as documented
above, nothing more, nothing less:

```json
{
  "groups": [
    {
      "id": "source-keycloak-group-id",
      "name": "team-name",
      "subGroups": []
    }
  ],
  "users": [
    {
      "id": "source-keycloak-user-id",
      "username": "login",
      "groups": ["/team-name"],
      "realmRoles": ["admin"]
    }
  ]
}
```

Kea teams are expected to be root Keycloak groups. Stop and inspect the source
before continuing if the groups used as Fred teams are nested or if two root
groups have the same name.

## Read-Only Postgres Extraction

Do not run `kc.sh export` or a wrapper that starts another Keycloak process
inside the live production pod. The extra process can contend for ports and
memory. Query the source Keycloak database read-only instead, after freezing
source mutations for a consistent capture.

First confirm the realm name and the expected Keycloak schema:

```sql
SELECT id, name FROM realm ORDER BY name;

\d realm
\d user_entity
\d keycloak_group
\d user_group_membership
\d user_role_mapping
\d group_role_mapping
\d keycloak_role
\d client
```

The following query includes:

- every root group with its stable source id and name;
- every non-service-account user with id and username;
- each user's root-group paths;
- direct and group-inherited Kea platform roles.

The representative Kea realm stores `admin`/`editor`/`viewer` as roles of the
Keycloak client whose `client_id` is `app`, while some older environments may
store them as realm roles. The query accepts both source representations and
normalizes them into `users[].realmRoles`, which is the single shape consumed
by the importer. Only those three legacy names are emitted.

```sql
WITH target_realm AS (
    SELECT id
    FROM realm
    WHERE name = 'app'
),
realm_groups AS (
    SELECT g.id, g.name
    FROM keycloak_group g
    JOIN target_realm r ON r.id = g.realm_id
    WHERE g.parent_group IS NULL
),
user_groups AS (
    SELECT
        ugm.user_id,
        jsonb_agg('/' || g.name ORDER BY g.name) AS groups
    FROM user_group_membership ugm
    JOIN realm_groups g ON g.id = ugm.group_id
    GROUP BY ugm.user_id
),
platform_roles AS (
    SELECT kr.id, kr.name
    FROM keycloak_role kr
    JOIN target_realm r ON r.id = kr.realm_id
    WHERE kr.client_role IS NOT TRUE
      AND kr.name IN ('admin', 'editor', 'viewer')

    UNION

    SELECT kr.id, kr.name
    FROM keycloak_role kr
    JOIN client c ON c.id = kr.client
    JOIN target_realm r ON r.id = c.realm_id
    WHERE kr.client_role IS TRUE
      AND c.client_id = 'app'
      AND kr.name IN ('admin', 'editor', 'viewer')
),
effective_user_roles AS (
    SELECT urm.user_id, pr.name
    FROM user_role_mapping urm
    JOIN platform_roles pr ON pr.id = urm.role_id

    UNION

    SELECT ugm.user_id, pr.name
    FROM user_group_membership ugm
    JOIN group_role_mapping grm ON grm.group_id = ugm.group_id
    JOIN platform_roles pr ON pr.id = grm.role_id
),
user_roles AS (
    SELECT
        user_id,
        jsonb_agg(name ORDER BY name) AS realm_roles
    FROM effective_user_roles
    GROUP BY user_id
)
SELECT jsonb_pretty(
    jsonb_build_object(
        'groups',
        COALESCE(
            (
                SELECT jsonb_agg(
                    jsonb_build_object(
                        'id', g.id,
                        'name', g.name,
                        'subGroups', '[]'::jsonb
                    )
                    ORDER BY g.name
                )
                FROM realm_groups g
            ),
            '[]'::jsonb
        ),
        'users',
        COALESCE(
            (
                SELECT jsonb_agg(
                    jsonb_build_object(
                        'id', u.id,
                        'username', u.username,
                        'groups', COALESCE(ug.groups, '[]'::jsonb),
                        'realmRoles', COALESCE(ur.realm_roles, '[]'::jsonb)
                    )
                    ORDER BY u.username
                )
                FROM user_entity u
                JOIN target_realm r ON r.id = u.realm_id
                LEFT JOIN user_groups ug ON ug.user_id = u.id
                LEFT JOIN user_roles ur ON ur.user_id = u.id
                WHERE u.service_account_client_link IS NULL
            ),
            '[]'::jsonb
        )
    )
);
```

If the installed Keycloak schema differs, stop and adapt the query explicitly;
do not remove a join merely to make the query run.

Produce a private file without `psql` headers:

```bash
umask 077
psql "$KEA_KEYCLOAK_DSN" -X -A -t -c "<query above>" > kea-realm-reconciliation.json
jq empty kea-realm-reconciliation.json
```

Delete this file securely after the cutover retention window. It contains
usernames and identity identifiers.

## Validate Both Inputs

Validate the reconciliation JSON before uploading it:

```bash
jq -e '
  def string_array:
    type == "array" and all(.[]; type == "string");
  def normalized_group:
    if startswith("/") then ltrimstr("/") else . end;

  type == "object" and
  (keys | sort) == ["groups", "users"] and
  (.groups | type == "array" and length > 0) and
  (.users | type == "array" and length > 0) and
  all(.groups[];
      (.id | type == "string" and length > 0) and
      (.name | type == "string" and length > 0) and
      (.subGroups | type == "array" and length == 0)) and
  all(.users[];
      (.id | type == "string" and length > 0) and
      (.username | type == "string" and length > 0) and
      (.groups | string_array) and
      (.realmRoles | string_array) and
      all(.realmRoles[]; IN("admin", "editor", "viewer")) and
      ((.groups | length) == (.groups | unique | length)) and
      ((.realmRoles | length) == (.realmRoles | unique | length))) and
  ([.groups[].id] | length == (unique | length)) and
  ([.groups[].name] | length == (unique | length)) and
  ([.users[].id] | length == (unique | length)) and
  ([.users[].username] | length == (unique | length)) and
  ([.groups[].name] as $known_groups |
    all(.users[].groups[]; (normalized_group | IN($known_groups[]))))
' kea-realm-reconciliation.json
```

The command must exit zero and print `true`. It deliberately rejects unknown
top-level keys, nested groups, non-string array entries, unknown platform
roles, duplicate identities, duplicate membership/role entries, and
memberships whose normalized name is absent from `groups[]`.

Record the source counts:

```bash
jq '{
  groups: (.groups | length),
  users: (.users | length),
  memberships: ([.users[].groups[]] | length),
  platform_admins: ([.users[] | select(.realmRoles | index("admin"))] | length),
  platform_viewers: ([.users[] | select(.realmRoles | index("viewer"))] | length)
}' kea-realm-reconciliation.json |
  tee kea-realm-reconciliation.counts.json
```

The production order of magnitude is approximately 50 teams and 1900 users.
Investigate any material difference from the independently measured source
counts.

Check duplicate identifiers and names; every command must print nothing:

```bash
jq -r '.groups[].id' kea-realm-reconciliation.json | sort | uniq -d
jq -r '.groups[].name' kea-realm-reconciliation.json | sort | uniq -d
jq -r '.users[].id' kea-realm-reconciliation.json | sort | uniq -d
jq -r '.users[].username' kea-realm-reconciliation.json | sort | uniq -d
```

Validate that the ZIP really carries its OpenFGA export:

```bash
unzip -p kea-snapshot.zip manifest.json |
  jq '{source_platform, tuple_count, tables}'

unzip -p kea-snapshot.zip openfga/tuples.json | jq 'length'
```

The manifest count and the array length must agree. If the source has
collaborative teams but the tuple count is zero, stop the cutover:

- the importer can still derive plain `team_member` relations from
  `users[].groups`;
- it can warn about an admin-less team already identified by `teammetadata`;
- it cannot recover `owner`/`manager` roles absent from OpenFGA;
- it cannot infer that every unrelated Keycloak/AD group is a Fred team.

## Dry Run

The API base path in production is `/control-plane/v1`:

```bash
curl --fail-with-body --silent --show-error \
  -X POST "https://<host>/control-plane/v1/kea-migration/dry-run" \
  -H "Authorization: Bearer <token>" \
  -F "file=@kea-snapshot.zip;type=application/zip" \
  -F "realm_file=@kea-realm-reconciliation.json;type=application/json" |
  tee kea-dry-run.json |
  jq .
```

The same operation is available on the **Kea migration** admin page.

Before trusting identity counts, verify that control-plane can read target
Keycloak through its M2M client. `GET /control-plane/v1/users` must at least
return the root user. A disabled M2M client currently returns an empty list,
which otherwise looks like a legitimately empty target realm.

### Go/no-go checks

Proceed only when:

- `source_platform` is `kea`;
- `teams_total` matches the independently measured number of Fred teams;
- `teams_orphan_dropped` is empty, or every entry has been investigated and
  proven stale;
- `agents_gap` is zero, or every gap has an explicit accepted disposition;
- `team_member_grants_pending` is coherent with the source membership count
  while target users are not yet present;
- every warning is understood.

On the initial run, with only root in target Keycloak:

- many users are expected to be `PENDING`;
- `platform_role_grants_ready` may be zero;
- many or all teams may appear in `teams_admin_less` because their source
  administrators do not yet have a target `sub`.

Those outcomes explain deferred reconciliation; they are not proof that the
source files are complete. In particular, `team_member_grants_pending == 0`
with non-zero source memberships is suspicious and must be investigated.

## Apply and Observe

Use the exact same two files for the real import:

```bash
curl --fail-with-body --silent --show-error \
  -X POST "https://<host>/control-plane/v1/import-export/import" \
  -H "Authorization: Bearer <token>" \
  -F "file=@kea-snapshot.zip;type=application/zip" \
  -F "realm_file=@kea-realm-reconciliation.json;type=application/json" |
  jq .
```

The endpoint returns an asynchronous migration task. Follow it in the shared
task UI or through the task-event API until terminal state. A `succeeded` task
may still contain reconciliation warnings; success without reviewing warnings
is not a cutover acceptance.

Do not start an import, reset, or teardown while another migration task is
active. The API rejects normal concurrent starts, but the operator remains
responsible for running one cutover action at a time.

## Identity Reconciliation and Replays

Kea and Swift Keycloak independently mint a `sub`. Username is the stable join:

- `MATCHED`: the source and target `sub` happen to be equal;
- `RELINKED`: the username exists under a different target `sub`;
- `PENDING`: the username has not yet logged in to Swift and has no target
  identity.

The importer snapshots target Keycloak users once at the start of each run. It
does not create identities and does not wait for users to log in. An immediate
second pass cannot resolve users who are still absent.

For the production pilot:

1. have the pilot user log in to Swift once;
2. run the dry-run and confirm `MATCHED` or `RELINKED` for that user;
3. run the real import with the same files;
4. verify their teams, agents, documents, and CSV/tabular corpus access.

For the full population, replay the same immutable inputs after users have
logged in. Relation writes and primary-key imports are idempotent; each replay
fills newly resolvable user-scoped data without duplicating already restored
state. Keep the original ZIP and reconciliation JSON unchanged between runs.

Automatic per-user reconciliation on first login is a possible future
improvement, but it is not implemented by this cutover code.

## Fixed Operational Order

1. Freeze source mutations.
2. Capture the Kea ZIP and reconciliation JSON.
3. Mirror/verify object-store content and prepare derived search products.
4. Validate both inputs and independently reconcile counts.
5. Verify target Keycloak M2M visibility.
6. Run dry-run and apply every go/no-go check.
7. Run the real import and review its terminal report and warnings.
8. Run the pilot validation.
9. Replay the immutable import inputs as target identities become available.
10. Validate documents, CSV/tabular access, agents, authorization, and search
    before directing all users to Swift.
11. Keep Kea frozen and available for rollback until acceptance is signed off.

## Non-Negotiables

- Fred never creates, updates, or deletes Keycloak users during this migration.
- No unresolved Kea `sub` is persisted as a Swift identity.
- Source Keycloak groups are migration evidence only. Target Swift teams are
  `team_metadata` rows plus OpenFGA relations; the current importer preserves
  the source group id as the migrated team id so tuples and metadata remain
  joined.
- `document_uid` remains unchanged across metadata, object storage, search
  products, and authorization tuples.
- The external `realm_file` replaces, rather than augments, the ZIP realm.
- The dry-run and real import use the same reconciliation-plan builder.
- A zero-tuple export is a stop condition when collaborative teams exist.
- Teardown tooling never touches Keycloak, object storage, or search products.
- Conversation and message-history migration is out of scope.

## Stop Conditions

Stop and investigate if any of the following is true:

- source mutations were not frozen for the capture;
- the realm name or Keycloak SQL schema differs from the reviewed query;
- source counts do not reconcile with the JSON or ZIP;
- duplicate group ids, group names, user ids, or usernames exist;
- collaborative teams exist but the OpenFGA tuple export is empty;
- `teams_orphan_dropped` contains an unexplained id;
- the expected target root user is invisible to control-plane;
- an identity, team, document, or agent template cannot be mapped;
- a task succeeds with unexplained warnings;
- imported metadata, object-store content, OpenSearch, or tabular products do
  not agree on their stable identifiers;
- pilot authorization or document/CSV access fails.

Do not compensate for a failed check by creating users in Keycloak, editing
OpenFGA manually, or changing the input files between dry-run and apply.
