# Migration guide — v3.1.0

Upgrade from: `code/v3.0.1`
Operational impact: **minor** (minimum version: `3.1.0`).

Review these procedures together in the listed dependency order before deployment. Customer-specific values remain in their private repositories; Fred chart values are the production reference. Configuration files named configuration_prod.yaml are for local development only.

No-operation declarations describe ordinary deployment only. Conditional activation steps still require preparation. Validate combined upgrade and rollback in staging before production.

## k3d deployment moves to fred-deployment-factory; self-sufficient migration hook

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.1.0/docs/swift/ops/migrations/2849-k3d-moves-to-deployment-factory.md)

### Applicability

Deployments that enable a migration Job (`applications.<app>.migration.enabled: true`), and developers who deployed Fred on k3d with this repository's `make k3d-deploy`.

### Prerequisites

Before upgrading an enabled migration Job, inspect how it receives FRED_POSTGRES_PASSWORD and any other required environment values. A Secret referenced by migration.extraEnvVars must exist before the Helm pre-upgrade hook. For k3d, have a checkout of fred-deployment-factory next to this repository.

### Configuration

The bundled chart values need no change. If a migration Job relied on the application's `env` or `envFrom`, put its required variables in `applications.<app>.migration.extraEnvVars` before upgrading. Supply `FRED_POSTGRES_PASSWORD` there when it is not in `dotenv.FRED_POSTGRES_PASSWORD`; any referenced Secret must already exist. The Job no longer inherits application volumes; review custom migration commands that expected those mounts.

### Upgrade

Apply any needed migration Job value changes before the chart upgrade, then deploy Fred. Deployments with disabled migration Jobs, or Jobs that already have all required inputs through `dotenv.FRED_POSTGRES_PASSWORD` and chart values, need no extra configuration. On k3d, deploy from fred-deployment-factory: `make k3d-up`, then `make k3d-fred FRED_DIR=<this checkout>`; the walkthrough is its `docs/LOCAL-DEVELOPMENT.md`, "k3d: the full stack in Kubernetes".

### Validation

Render the chart with `migration.enabled: true`: the Job carries `DATABASE_URL` and any configured `migration.extraEnvVars`, without application ConfigMap or Secret mounts. With `dotenv.FRED_POSTGRES_PASSWORD` set, the `<app>-migration-db` hook Secret has the `hook-succeeded` and `hook-failed` delete policies. Confirm the pre-upgrade Job completes before application rollout.

### Rollback

Restore the previous chart and its previous migration Job values if this chart change must be rolled back. Follow the separate database migration rollback guidance for this release.

### Limitations

Migration Jobs cannot use application ConfigMaps or Secret mounts that Helm creates after pre-upgrade hooks. Custom migration commands needing additional environment or files require a pre-existing source that the Job can access.

## Skip migration notes CI for Dependabot and stop commit-tagged dev images

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.1.0/docs/swift/ops/migrations/2852-deps-pr-migration-check.md)

The workflow changes do not alter deployed code, data or APIs.

See the source note for applicability, validation and rollback.

## Enable agent-initiated human questions

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.1.0/docs/swift/ops/migrations/agent-initiated-human-questions.md)

### Applicability

Fred deployments upgrading the control plane, agent runtime, SDK and frontend.

### Prerequisites

Use a release containing the SDK, runtime, control plane and frontend changes.

### Configuration

No configuration or data migration is required. Existing HITL history remains readable.

### Upgrade

Deploy the SDK and agent runtime first, then the control plane and frontend. The
control plane then offers the question control, enabled by default. Older clients
that omit `ask_user` continue without the tool.

### Validation

In managed chat, verify that the tune menu offers agent questions, the agent can
ask one question, answer and skip both continue the turn, and a skipped answer
remains visible after reload.

### Rollback

Withdraw the control plane and frontend exposure first. Let already-pending
agent questions finish on the new runtime before rolling back the runtime and
SDK; an older runtime cannot resume those checkpointed tool calls. No database
migration must be reversed.

### Limitations

The platform tool is available on interactive ReAct and Deep parent turns. Graph
agents and Deep child agents do not gain a model-facing question tool.

## Compact table pagination bar

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.1.0/docs/swift/ops/migrations/compact-table-pagination.md)

Layout-only frontend change; it applies with the normal frontend deployment.

See the source note for applicability, validation and rollback.

## Restore Deep agent task lists

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.1.0/docs/swift/ops/migrations/deep-agent-todo-middleware.md)

Normal deployment restores the write_todos tool; no data or API migration is needed.

See the source note for applicability, validation and rollback.

## Refresh vulnerable Python and npm dependencies

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.1.0/docs/swift/ops/migrations/dependabot-security-refresh.md)

Existing data, APIs, and deployment order are unchanged; rebuilt images and frontend assets take effect through normal deployment.

See the source note for applicability, validation and rollback.

## Audit the five Dependabot dependency updates

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.1.0/docs/swift/ops/migrations/dependabot-update-audit.md)

These dependency updates change packaged libraries only; existing data, public APIs and deployment order are unchanged.

See the source note for applicability, validation and rollback.

## Explain empty and unreadable document uploads

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.1.0/docs/swift/ops/migrations/explicit-upload-validation-errors.md)

Existing validation outcomes and progress event fields remain unchanged; normal deployment is sufficient.

See the source note for applicability, validation and rollback.

## Clear the Resources drop overlay after dropping into a folder

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.1.0/docs/swift/ops/migrations/import-drop-overlay-reset.md)

The frontend clears its overlay after a file is dropped on a folder row; data and APIs are unchanged.

See the source note for applicability, validation and rollback.

## Imports are followed in a panel, and survive the dialog closing

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.1.0/docs/swift/ops/migrations/import-progress-panel.md)

No backend, database, API or permission change. The behaviour is unconditional and comes with the frontend bundle.

See the source note for applicability, validation and rollback.

## Show queued imports as waiting in the import panel

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.1.0/docs/swift/ops/migrations/import-stepper-waiting-state.md)

Display-only frontend change; it applies with the normal frontend deployment.

See the source note for applicability, validation and rollback.

## Offer only teams the caller can actually write to when importing a marketplace prompt

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.1.0/docs/swift/ops/migrations/marketplace-import-editor-only.md)

Runtime APIs, persisted data, permissions, and deployment order are unchanged; normal deployment is sufficient.

See the source note for applicability, validation and rollback.

## Recover Mistral tool calls from mixed content fragments

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.1.0/docs/swift/ops/migrations/mistral-mixed-tool-call-fragments.md)

Existing data and APIs are unchanged; the fix takes effect when the updated runtime is deployed normally.

See the source note for applicability, validation and rollback.

## Start a new conversation from the managed chat header

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.1.0/docs/swift/ops/migrations/new-chat-from-conversation.md)

Existing sessions and APIs are unchanged; the action appears with normal frontend deployment.

See the source note for applicability, validation and rollback.

## Keep Knowledge Flow responsive while an upload is written to the content store

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.1.0/docs/swift/ops/migrations/offload-upload-save-input.md)

Upload endpoints, stored data and write order are unchanged; the fix takes effect with a normal deployment.

See the source note for applicability, validation and rollback.

## Prepare the Fred 3.1.0 release documents

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.1.0/docs/swift/ops/migrations/release-3-1-0-preparation.md)

Release documentation introduces no runtime or data change; operational changes are covered by their source notes.

See the source note for applicability, validation and rollback.

## Show the import count badge in the Resources panel

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.1.0/docs/swift/ops/migrations/resources-import-count-badge.md)

The badge layout changes with the normal frontend deployment; data and APIs are unchanged.

See the source note for applicability, validation and rollback.

## Keep document names visible beside the import panel

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.1.0/docs/swift/ops/migrations/resources-name-column-floor.md)

Layout-only frontend change; it applies with the normal frontend deployment.

See the source note for applicability, validation and rollback.

## Constrain runtime execution URLs and tabular queries

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.1.0/docs/swift/ops/migrations/runtime-url-and-tabular-query-safety.md)

### Applicability

Fred deployments with configured runtime catalog sources or tabular query access.

### Prerequisites

Inspect every `platform.runtime_catalog_sources[].ingress_prefix` value in the
active deployment configuration before upgrading.

### Configuration

Each `ingress_prefix` must be a canonical path beginning with one `/`, such as
`/fred/agents/v2`. Replace absolute URLs, network-path references, encoded
characters, dot segments, and trailing slashes with the gateway's root-relative
runtime path. The bundled Helm value needs no edit. No new secrets or permissions
are required.

### Upgrade

Update invalid runtime prefixes in the deployment values before restarting the
control plane. Deploy the control plane, frontend, and Knowledge Flow backend
through the normal release procedure. No data migration or re-ingestion is
required.

### Validation

Start a managed-agent turn and confirm its stream opens through the configured
runtime ingress path. Run an authorized tabular query and confirm it returns
results; confirm an external file or metadata query is rejected.

### Rollback

Restore the previous Fred release and its previous values together. Previously
accepted noncanonical prefixes may resume working after rollback; they should
still be corrected before a later upgrade.

### Limitations

Pure built-in DuckDB analytical functions remain available in tabular queries. Queries that inspect runtime configuration, use side-effecting functions, or use external table sources are rejected. DuckDB settings are defense in depth and do not replace process or container isolation for untrusted SQL.

## Make team avatars cacheable and stop shipping oversized images

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.1.0/docs/swift/ops/migrations/team-avatar-loading.md)

Browser-cache and image-size optimisation only; stored avatars, the team API contract and the object-storage layout are untouched.

See the source note for applicability, validation and rollback.

## Align the UI package glyph count test with the bundled icons

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.1.0/docs/swift/ops/migrations/ui-archive-glyph-count.md)

No runtime change; the UI package already ships these icons.

See the source note for applicability, validation and rollback.

## Imports ask before replacing a document of the same name

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.1.0/docs/swift/ops/migrations/import-name-conflict-resolution.md)

### Applicability

Existing Fred deployments upgrading to this release.

### Prerequisites

No additional prerequisites beyond the normal deployment procedure. The new
code answers correctly with or without this revision's index; without it, the
question it answers costs a scan of the `metadata` table per imported file,
which is what the index removes.

### Configuration

No configuration changes are required.

### Upgrade

Deploy Fred normally. The knowledge-flow Alembic upgrade adds one index,
`idx_metadata_document_name`, on the document name inside the `metadata` table's
`doc` column. It is built without `CONCURRENTLY`, so that table is held against
writes while it is built — a few seconds on a large corpus, during which
ingestion waits rather than fails. No existing document is read, rewritten or
re-ingested.

Behaviour change for users, requiring no operator action: uploading a file whose
name a destination folder already holds now asks the uploader to replace the
existing document or keep it. Previously the upload silently created a second
document marked as an alternate version, and a third upload of that name failed
outright.

Any non-UI client of `POST /knowledge-flow/v1/upload-documents` or
`/upload-process-documents` is affected: a conflicting file carrying no decision
is now reported on the response stream with status `conflict` and is not
imported, instead of being versioned silently. Such a client sends its answer as
`conflict_decisions` in `metadata_json` — a map of file name to `overwrite` or
`skip` — or asks `POST /knowledge-flow/v1/documents/name-check` first. The
repository's own ingestion load-test script is the only such client and needs no
change beyond pointing each run at a fresh folder.

Two files of one import can no longer land in the same folder under the same
name. The import dialog refuses the selection and names the collision.

### Validation

Upload a file into a team folder that already holds a document of that name: the
upload dialog lists it and offers **Replace** / **Skip** before anything is sent.
Choosing **Replace** leaves one document in the folder, keeping its identifier,
with the new content.

### Rollback

Downgrading this knowledge-flow Alembic revision drops the index without
changing document data. Release rollback does not undo the later document
renames; follow the alternate-version migration rollback guidance.

### Limitations

The alternate-version migration in this release gives hidden alternates
their own names. Concurrent imports or adding an existing document to a folder
can still create duplicate names; the import then asks the user to rename or
delete one.

## Hidden alternate document versions are retired and renamed

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.1.0/docs/swift/ops/migrations/retire-document-versioning.md)

### Applicability

Existing Fred deployments upgrading to this release. Only deployments whose
corpus contains alternate versions are affected by the data migration; the code
removal applies everywhere.

### Prerequisites

No additional prerequisites beyond the normal deployment procedure. The
same-name import question and this migration ship together. When enabled, the
chart migration Job runs before the new application code is rolled out.

Before upgrading, you can see exactly which documents the migration will rename:

```sql
SELECT document_uid,
       doc->'identity'->>'document_name' AS name,
       tag_ids
FROM metadata
WHERE jsonb_typeof(doc->'identity'->'version') = 'number'
  AND (doc->'identity'->'version') > '0'::jsonb;
```

That is the migration's own test for an alternate, deliberately: comparing the
JSON number rather than casting it to `int` cannot fail on a value too large for
`int`, or on a hand-edited one that is not a number at all.

### Configuration

No configuration changes are required.

### Upgrade

Deploy Fred normally. The knowledge-flow Alembic upgrade runs migration
`02d556a6f182`, a **data migration** over the `metadata` table.

Each document that carried a hidden alternate version becomes an ordinary
document. Where its folder already holds another document of that name, it is
renamed — `report.pdf` becomes `report (1).pdf`, with the number increasing past
any name a third document already holds, checked in every folder the document
belongs to. A document whose base was already deleted collides with nothing and
keeps the name it has.

Nothing is deleted, no `document_uid` changes, no folder membership changes, no
document is re-ingested or re-embedded, and a title a user typed is kept.

**Only those documents are written.** Every other document keeps the
`canonical_name` and `version` keys it already had in its stored JSON. They are
inert — the application's document model no longer declares either field and
ignores both on read — and each document drops them the next time anything saves
it. Clearing them for the whole corpus up front was measured at 20 seconds and
1.1 GB of WAL at 500,000 documents, against a 30-second statement timeout, and
would have failed the upgrade on a large platform to tidy data nothing reads.

Cost is therefore proportional to the number of alternate versions, not to corpus
size: one indexed lookup per candidate name. A corpus with none does no work.

The whole migration runs in one transaction, as every Alembic migration on this
platform does. An interrupted upgrade leaves the database exactly as it was and
is safe to retry from the start; a completed one finds nothing left to do if run
again.

Two behaviour changes needing no operator action:

- Deleting a document no longer promotes a hidden replacement in its place. There
  are none left to promote.
- `canonical_name` and `version` are gone from the document identity returned by
  the Knowledge Flow API. No Fred UI code read them. A non-UI client that reads
  either field must stop; a client that *writes* them is unaffected, as they were
  already ignored on input.

### Validation

In a team folder that held a base document and its alternate version, both now
appear under distinct names — the second as `<name> (1).<ext>` — and both open.
Deleting the first leaves the second exactly where it is, under its own name.

Re-running the SQL from **Prerequisites** after the upgrade returns no rows.
Documents still carrying `version: 0` in their stored JSON are expected and
harmless — see **Upgrade**.

### Rollback

Use the normal rollback procedure for code and chart. The Alembic downgrade for
this revision is deliberately empty and **the rename is not reversible**: once
two documents carry names of their own, nothing records which of them used to be
the hidden one, so restoring that distinction would mean inventing it.

Rolling the code back is still safe. The renamed documents are ordinary
documents, valid on the previous release, which simply treats them as two
unrelated files — which is what they now are.

If a specific name must be restored, rename the document in the UI.

### Limitations

The import name-conflict note's limitation is narrowed, not closed. Alternate
versions are gone, so they are no longer how a folder ends up holding two
documents of one name - but two other paths still are: two concurrent imports of the same name
(the pre-upload name check is not repeated at write time), and adding an existing
document to a folder that already holds its name, which is unguarded unlike a
rename (#2877). In that state the import still refuses the name and now tells the
user to rename or delete one of the two, an instruction they can actually act on;
previously it told them to promote an alternate version, which was never an
action the product offered.

Two consequences of a rename, for the few documents the migration renames:

- **A renamed spreadsheet's SQL alias changes.** `build_default_query_alias`
  derives the DuckDB relation name from the document name, so `sales.csv` renamed
  to `sales (1).csv` moves from `d_<uid>_sales` to `d_<uid>_sales_1`. A saved
  query or client naming the old alias is rejected after the upgrade and has to
  be pointed at the new one.
- **A renamed document keeps the title a user typed for it**, deliberately: a
  migration carries none of the intent that makes a hand-driven rename supersede
  it. Where such a title exists, the Resources table shows it with the
  "Embedded title" hint, as it does for any document whose title and file name
  differ.

Vector chunks keep their own copy of the document name for citation display, and
the migration does not rewrite it — the same best-effort treatment the in-app
rename already gives it. A renamed document may therefore be cited under its old
name until it is re-vectorized. Re-vectorizing it from the corpus admin page
updates the copy; nothing else is affected.
