# Migration guide - v3.11.0

Upgrade from: `code/v3.10.0`
Operational impact: **minor** (minimum version: `3.11.0`).

Review these procedures together in the listed dependency order before deployment. Customer-specific values remain in their private repositories; Fred chart values are the production reference. Configuration files named configuration_prod.yaml are for local development only.

No-operation declarations describe ordinary deployment only. Conditional activation steps still require preparation. Validate combined upgrade and rollback in staging before production.

## Prepare and coordinate the Fred v3.11.0 rollout

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.11.0/docs/swift/ops/migrations/000-3521-prepare-v3-11-0-release.md)

### Applicability

Fred v3.11.0 preparation from code/v3.10.0. The covered dependency contribution
updates only Knowledge Flow's oauthlib lock entry from 4.0.0 to 4.0.1,
including artifact URLs and hashes; no configuration or application code changes.

### Prerequisites

Review the whole guide before starting. Record the previous runtime and
capability revision IDs and take coordinated database and object-store backups.
Plan a maintenance window: the in-thread message migration is incompatible with
old runtime replicas. Version 3.11.0 is the integrator's explicit selection;
it does not remove these operational constraints.

### Configuration

No additional configuration changes originate in this preparation.

### Upgrade

Apply this combined sequence, using the detailed procedures below for each
component. A procedure saying "deploy normally" describes only its own change;
it does not waive this release's coordinated maintenance window.

1. Before stopping old services, freeze PPT template edits, finish pending
   legacy analyses and ensure any successful platform replacement is promoted.
   Retain the legacy SQL rows and objects for backfill and rollback.
2. Block new user traffic, drain active turns and stop every old runtime
   replica. Warn users that unsent old queue or mailbox messages must be resent.
   Record migration revisions before applying the new ones.
3. Publish the new OpenFGA model before enabling analytics when schema sync is
   disabled; update any pinned model IDs. Adapt custom KPI, document-search
   and tabular clients as described below.
4. Apply the control-plane and runtime migrations with the new images. The
   control-plane adds preparation state and session activity; the runtime
   removes the old steering mailbox. Upgrade Knowledge Flow API/workers,
   agent serving pods, control-plane and frontend as one coordinated release
   before reopening traffic. Never restart an old runtime against the migrated
   runtime schema.
5. Keep PPT preparation flags disabled while validating the new worker and
   running the dry backfill and import. "Legacy reader" means the compatible
   reader in the new image, not restarting a pre-cutover runtime. Keep template
   edits frozen through reconciliation, then enable the new preparation flags
   and validate templates before allowing edits again.
6. Validate analytics permissions, document tools, cross-pod in-thread messages
   and PPT preparation. Reopen traffic only after those checks succeed.
   Azure model discovery, Zabbix monitoring, KPI history backfill and source
   re-ingestion are separate optional actions; none is required merely to
   reopen traffic.

Do not publish tags until the preparation PR is reviewed, merged and explicitly
approved. These instructions coordinate existing migrations; this preparation
does not add a new database revision.

### Validation

Validate migration coverage, the generated guide, package artifacts, stored
capability configuration compatibility and synchronized locks. Run root quality
checks and review PR CI before merge.

### Rollback

Reverting release metadata does not undo migrations in the release. Follow the
runtime cutover and PPT preparation rollback procedures and retain backups.

### Limitations

Package artifact validation is not a production migration rehearsal. Customer
overlays, real data backfills and multi-pod rollout checks require operator
validation. No tag or package publication is authorized by this PR.

## Fix writable-document downloads with Unicode titles

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.11.0/docs/swift/ops/migrations/3468-writable-document-unicode-downloads.md)

Existing documents and permissions are unchanged; Unicode downloads work after normal deployment.

See the source note for applicability, validation and rollback.

## Analytics can leave weekends and French public holidays out

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.11.0/docs/swift/ops/migrations/analytics-counted-days.md)

The new preset parameters default to counting every day, so existing API consumers see the same figures; no data migration.

See the source note for applicability, validation and rollback.

## Analytics tiles open their trend over the period

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.11.0/docs/swift/ops/migrations/analytics-kpi-trend.md)

The activity preset only gains two keys in its values map; existing data and consumers are unaffected.

See the source note for applicability, validation and rollback.

## Archive the weaver UI port and turn attachments OpenSpec changes

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.11.0/docs/swift/ops/migrations/archive-weaver-port-and-turn-attachments-openspec.md)

Documentation only; no code, data or API changes, so normal deployment is enough.

See the source note for applicability, validation and rollback.

## Authenticate model discovery through Azure APIM

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.11.0/docs/swift/ops/migrations/azure-apim-model-discovery-auth.md)

### Applicability

This applies to agent pods that discover chat models through Azure APIM. Existing static profiles and ordinary OpenAI discovery need no change.

### Prerequisites

An operator enabling the optional source must provide `AZURE_AD_CLIENT_SECRET` and `AZURE_APIM_SUBSCRIPTION_KEY` to the agent pod. The APIM product must allow its model-list endpoint for the configured Entra client and subscription.

### Configuration

No bundled configuration changes are required. To enable the feature, set the discovery source's `provider` to `azure-apim` and supply the six non-secret `azure_apim_settings` fields already used by static Azure APIM profiles. The discovery URL must stay within the configured APIM origin and resource path. Keep `include_model_ids` limited to verified chat models when the gateway omits chat capability metadata.

### Upgrade

Deploy an agent image containing this change before enabling the optional discovery source. Restart agent pods after changing their mounted model catalog; static profiles remain available during the rollout. Deployments without this source need no extra upgrade step or database migration.

### Validation

Refresh the configured source and confirm its model list succeeds with OAuth and the APIM subscription header. Confirm a discovered model can be selected for a managed turn, and that an existing model with a Responses API route retains that route. The source URL may be edited only within the configured HTTPS origin and APIM product path.

### Rollback

Remove or comment out the optional discovery source and restart agent pods. Keep the existing static Azure APIM profiles and their credentials.

### Limitations

Discovery does not grant access to new models automatically. If the gateway omits chat capability metadata, use `include_model_ids` to prevent embedding models from appearing as chat choices.

## Attachment chips with a file type icon and a color per status

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.11.0/docs/swift/ops/migrations/chat-attachment-chips.md)

The change ships with the normal deployment and stores no new data.

See the source note for applicability, validation and rollback.

## Show the chat and its side panels on separate cards, with the launcher rail outside them

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.11.0/docs/swift/ops/migrations/chat-cards-layout.md)

The change ships with the normal deployment and stores no new data.

See the source note for applicability, validation and rollback.

## Replace active-turn steering with in-thread messages

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.11.0/docs/swift/ops/migrations/chat-in-thread-message-cutover.md)

### Applicability

Release classification: the integrator explicitly selected v3.11.0 on
2026-11-12, overriding the original major version classification for this
cutover. This release-specific decision does not make the schema backward
compatible: the required drain, discarded pending messages and rollback
limitations below still apply.

Fred deployments upgrading from the browser queue and runtime steering mailbox
to in-thread messages during active ReAct and Deep turns.

### Prerequisites

Stop or drain old runtime replicas before applying the new fred-runtime Alembic
migration. Old replicas must not serve requests after the steering table is
removed. Coordinate the matching frontend rollout with the runtime rollout.

### Configuration

No configuration changes are required. The new message state lives in the
existing shared `session_history` table.

### Upgrade

The migration adds message identity and delivery state to `session_history` and
drops `runtime_turn_steering`. Apply it after draining old runtime replicas,
then start the new replicas and deploy the matching frontend. Messages still
pending in the old mailbox or browser queue are discarded. Ask users to resend
an old pending message if it did not appear in their conversation.

### Validation

With two runtime replicas, start a ReAct or Deep turn on one pod and submit
another text message through the other. Confirm its pending indicator, final
rank after the next model boundary, and order after a page reload. Repeat across
a human-input pause and a restart. The migration downgrade test also verifies
that the old steering table returns at its previous revision and disappears at
the current head without changing capability migration revisions.

### Rollback

Stop the new runtime replicas before downgrading the migration. The downgrade
recreates an empty steering mailbox; messages submitted under the new version
have no equivalent mailbox entry. Restore the old runtime and frontend together.

### Limitations

Immediate in-thread submission accepts plain text in active ReAct and Deep
turns. Graph execution, commands, attachments and human-input answers retain
their existing send paths. An unavailable model boundary leaves the new message
pending until a later eligible turn.

## Chat header with a foldable navigation panel

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.11.0/docs/swift/ops/migrations/chat-layout.md)

The change ships with the normal deployment and stores no new data.

See the source note for applicability, validation and rollback.

## Chat list scrollbar sits in the list's right padding

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.11.0/docs/swift/ops/migrations/chat-list-scrollbar-gutter.md)

Pure CSS change in the frontend; data, APIs and deployment order are unchanged.

See the source note for applicability, validation and rollback.

## Run PR quality and tests when ready for review

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.11.0/docs/swift/ops/migrations/defer-pr-checks-until-ready.md)

The PR validation schedule changes without altering Fred runtime behavior or deployment steps.

See the source note for applicability, validation and rollback.

## Build Docker images only when pull requests are ready for review

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.11.0/docs/swift/ops/migrations/defer-pr-docker-builds-until-ready.md)

Published images, application code and deployment behavior are unchanged.

See the source note for applicability, validation and rollback.

## Clarify Epic links and descriptive branch names

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.11.0/docs/swift/ops/migrations/descriptive-topic-branch-names.md)

Application code, published artifacts and deployment behavior are unchanged.

See the source note for applicability, validation and rollback.

## Standardize document references and remove NUL before document saves

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.11.0/docs/swift/ops/migrations/document-tool-reliability.md)

### Applicability

Fred deployments using native document reading, summarization or writable documents.

### Prerequisites

No additional prerequisites beyond the normal deployment procedure.

### Configuration

No configuration changes are required.

### Upgrade

Deploy the updated document capabilities together. Native search tool JSON now uses `hits[].document_uid` instead of `hits[].uid`; update custom consumers that parse that tool result. Backend search APIs and typed citation sources retain `uid`. No database migration, re-ingestion or stored-history rewrite is required.

### Validation

Inspect native search text and structured blocks for `document_uid`, with no duplicate `uid` key; copy that value into read/summary. A writable-document call containing U+0000 must succeed with NUL removed from stored/editor title and Markdown, and disclose removal counts. Reload its conversation: the successful call/result must remain paired and original NUL-bearing arguments must have attributed history notation.

### Rollback

Use the normal rollback procedure and revert custom tool-result consumers to `hits[].uid`. The earlier branch policy rejects NUL instead of removing it. Existing readers accept history metadata through their existing extra-field compatibility.

### Limitations

The parameter guidance is not a guarantee of model behavior. Existing corpus documents, UID values, permissions, retry policy and authentication are unchanged. Removal applies only to actual U+0000 in writable title/Markdown; literal marker text and valid Unicode remain intact. History notation is an attributed diagnostic representation rather than the original character. JSON object keys and identity fields are outside this text-value normalization contract.

## Isolate runtime context between Graph tests

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.11.0/docs/swift/ops/migrations/graph-test-runtime-context-isolation.md)

Production code, stored data, and APIs are unchanged; normal deployment needs no additional action.

See the source note for applicability, validation and rollback.

## Home agent suggestions without OpenSearch

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.11.0/docs/swift/ops/migrations/home-agent-suggestions.md)

### Applicability
Existing deployments, including those without OpenSearch KPI storage.

### Prerequisites
Normal control-plane database migration privileges.

### Configuration
No configuration changes are required.

### Upgrade
Use the normal deployment procedure and control-plane Alembic upgrade. Revision
`d7a2f591c034` adds nullable `session_metadata.last_activity_at` and its lookup
index. No new table or historical backfill is introduced.

### Validation
Open home without KPI storage: accessible default-team and personal agents
appear. Send a message to an accessible agent and return home: that instance
ranks first, with up to four other distinct agents. Rename alone must not
establish recent priority.

### Rollback
Roll back application code normally; old code ignores the additive column.
If explicitly downgrading the schema, stop the new application first, then
run the ordinary Alembic downgrade. Dedicated activity dates will be lost.

### Limitations
Older conversations have unknown activity until another activity PATCH.
Ranking uses the existing browser activity report, not proof of successful
runtime execution. Agents in non-default teams appear through known recent
activity; default-team and personal agents provide the alphabetical complement.

## Prevent invented HTML artifact links in chat responses

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.11.0/docs/swift/ops/migrations/html-artifact-link-guidance.md)

The existing preview and artifact payload are unchanged; normal deployment applies the new model guidance.

See the source note for applicability, validation and rollback.

## Separate cached React consumer integration coverage from unit tests

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.11.0/docs/swift/ops/migrations/isolate-react-consumer-test.md)

No shipped runtime code, APIs or stored data change.

See the source note for applicability, validation and rollback.

## KPI events carry the tool's capability and the API request's team, with an optional backfill

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.11.0/docs/swift/ops/migrations/kpi-analytics-dims.md)

### Applicability

Every deployment. The optional backfill only matters to deployments with KPI history in OpenSearch.

### Prerequisites

None. For the backfill: a control-plane pod that reaches OpenSearch and PostgreSQL, as at runtime.

### Configuration

No configuration changes are required.

### Upgrade

Deploy Fred normally. At startup the KPI store adds `dims.capability_id`, `quantities.cache_read_tokens` and `quantities.tool_count` to the existing index. No Prometheus label is added. No Alembic migration.

Optional activation: complete past events once, dry run first.

```bash
kubectl exec deploy/<control-plane> -- fred-control-plane-kpi-backfill --dry-run
kubectl exec deploy/<control-plane> -- fred-control-plane-kpi-backfill
```

`--since <ISO date>` limits the range; `--step reindex|teams|all` (default `all`). The team step is safe to rerun and skips events that already have a team. The reindex step rewrites every selected turn event on each run, so use `--step teams` when retrying team attribution alone.

### Validation

The backfill logs `updated N turn event(s)` and `updated N event(s) for M user(s)`. A second `--step teams` run reports 0 events. A second reindex run reports the selected turn events again.

### Rollback

Use the normal rollback procedure. The added fields and backfilled `dims.team_id` values are ignored by the previous release.

### Limitations

Backfilled team attribution is a per-UTC-day estimate. Tool calls recorded before the upgrade get no capability. Avoid running the backfill during user deletions; on large platforms the team step can take hours (`--since` helps).

## Generate local application image SBOMs

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.11.0/docs/swift/ops/migrations/local-image-sboms.md)

SBOM generation is a developer command; existing deployments, data and APIs upgrade normally.

See the source note for applicability, validation and rollback.

## Move PPT Builder preparation to the capability worker

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.11.0/docs/swift/ops/migrations/reusable-capability-preparation.md)

### Applicability

This migration moves Swift PPT Builder originals from `cap_ppt_builder_analysis`
into control-plane capability assets, and moves inventories and preview PDFs into
the runtime object store. It also imports the active platform template, a failed
or pending replacement, and the manager's pattern overrides. The old SQL rows
remain intact for the migration window.

### Prerequisites

Make the control-plane and runtime databases and object stores available to the
backfill command. For local storage, mount both storage roots at the same paths
as their services. For MinIO or GCS, supply the same bucket configuration and
credentials as the services. Keep the old PPT reader active until backfill and
worker readiness checks complete.

### Configuration

Set `vision_model` once on the Knowledge Flow API and its worker configuration.
The preparation worker calls Knowledge Flow's internal vision endpoint using
the workload identity named by `vision_worker_client_id`; the caller never
chooses a model. The PPT settings retain only `use_vision`. When Knowledge
Flow reports that no vision model is available, the form disables this switch
and preparation uses the slide labelling rules. If the availability lookup fails,
the form preserves the saved choice and reports that it could not be checked.

The Helm chart defines `applications.fred-agents-preparation-worker` as a
separate deployment using the same capability registry and runtime storage as
`applications.fred-agents`. The Fred chart starts this worker by default;
the cutover still requires explicit preparation flags after backfill. Give it
the same `ai.knowledge_flow_url`, service credentials, Temporal namespace and
object-store configuration as the serving pods. `preparation.max_concurrent_jobs`
bounds work per worker replica. `preparation.per_capability_concurrency` bounds
each installed capability's work within that replica. Set the control-plane
runtime catalog source's `preparation_enabled` and serving pod's
`preparation.enabled_capabilities` only after backfill and worker readiness
checks are complete.
The deployment command is `python -m fred_runtime preparation-worker`, also
available through `make run-worker` and `make run-worker-docker` in `fred-agents`.
Other agent pod images with `fred-runtime` installed use the same command; the
generic `agent-pod` chart exposes it with `preparationWorker.enabled: true`.
Temporal retries a worker activity after two minutes without a heartbeat.
Agent multipart saves accept at most 64 MiB across all capability assets.

### Upgrade

1. Deploy the additive control-plane migration, Knowledge Flow vision endpoint,
   and the separate `fred-agents` preparation worker. Keep
   `preparation.enabled_capabilities` empty on serving pods while backfilling.
2. Stop PPT template edits during the final pass. Let old analyses finish or
   repeat the pass until their status and hashes stop changing. Do not enable
   the new reader while a legacy `__platform_next__` row has succeeded but has
   not yet been promoted by the old job.
3. Run a dry pass and then the import. The command scans one legacy row at a
   time, verifies every template hash, writes immutable objects under stable
   keys, and commits one control-plane row at a time. Re-running it is safe.

```bash
python -m control_plane_backend.capability_preparations.backfill_cli \
  --control-plane-config /path/to/control-plane/configuration.yaml \
  --control-plane-env /path/to/control-plane/.env \
  --runtime-config /path/to/fred-agents/configuration.yaml \
  --rules-version 23 --dry-run

python -m control_plane_backend.capability_preparations.backfill_cli \
  --control-plane-config /path/to/control-plane/configuration.yaml \
  --control-plane-env /path/to/control-plane/.env \
  --runtime-config /path/to/fred-agents/configuration.yaml \
  --rules-version 23
```

Run from the control-plane application directory with an environment containing
`control_plane_backend`, `fred_core`, `fred_sdk`, `fred_pod`, SQLAlchemy, and the
configured object-store clients. Set `PPT_BACKFILL_RUNTIME_POSTGRES_PASSWORD` if
the runtime database has a different password from `FRED_POSTGRES_PASSWORD`.
The rules version must match PPT Builder's `PreparationSpec.rules_version` in
the serving image.

### Validation

The JSON result reports `total` and counts for `imported`, `imported_builtin`,
`existing`, and `skipped_*`. Check that their sum equals `total`. Deleted agents
can be skipped.
The import command exits with an error if any live agent with a selected PPT
template has no current preparation, including one skipped because its template
changed. It also refuses a successful legacy analysis made with older rules;
re-run that analysis on the old service, then repeat the import. Stop edits for
the final pass so this check remains valid until the flags are enabled.
Investigate changed or unconfigured agents before cutover, and check the active
platform default and replacement in the PPT admin panel. The dry pass never
writes to the control-plane database or either object store.

After reconciliation, enable `ppt_builder` in
`preparation.enabled_capabilities` on every `fred-agents` serving pod and set
the matching control-plane runtime catalog source to `preparation_enabled`.
Verify the already deployed worker uses the same capability registry, runtime
object store, and Temporal namespace. Existing agent configs retain their
historical fields in SQL, but the enabled reader uses the imported result. The
next save removes the legacy model selection. A failed imported preparation can
be retried without a new upload.

### Rollback

Before new template edits, rollback is a switch back to the old reader and
writer because the legacy SQL rows were not deleted. After new edits begin, do
not switch back without first reconciling those new assets into the legacy
store; the old SQL rows no longer contain the latest uploaded templates.

### Limitations

During the migration window, stop template edits for the final backfill pass.
After cutover, the legacy SQL rows no longer contain new template assets.

## Document SIEM log integration and detection scenarios

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.11.0/docs/swift/ops/migrations/siem-integration-guide.md)

Existing deployments and data are unchanged; the guide is available without a special upgrade or migration step.

See the source note for applicability, validation and rollback.

## Require exact targets for agent migration downgrades

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.11.0/docs/swift/ops/migrations/target-runtime-capability-downgrade.md)

### Applicability

Fred deployments that use the agent image's `fred_runtime downgrade` command
or the `apps/fred-agents` `db-downgrade` Make target for operator rollback.

### Prerequisites

Before a planned rollback, record the old revision of each runtime or installed
capability migration tree. Stop writers, review the crossed migrations and take
a coordinated backup as described in the Docker Compose rollback runbook.

### Configuration

No configuration changes are required. Select the intended database with the
existing `CONFIG_FILE` or `DATABASE_URL` before running a downgrade.

### Upgrade

Deploy Fred normally. The automatic `python -m fred_runtime migrate` command
still upgrades the runtime and installed capability trees to their heads.
Update any operator script that calls `fred_runtime downgrade <tree> -1` or
`make db-downgrade MIGRATION_TREE=<tree>` to supply the recorded old revision
or `base` as an explicit target. `base` applies only when the old release had
no revision in that selected tree.

### Validation

On an isolated database, upgrade the runtime and installed capability trees,
then run `python -m fred_runtime downgrade runtime <recorded-old-revision>`
and, if needed, `python -m fred_runtime downgrade capability:<id> base`.
Verify each selected version table and affected schema. Confirm other trees
retain their revisions and the normal `migrate` command still upgrades them.

### Rollback

Reverting this CLI change restores the old single-step `-1` argument. The
older image lacks migration scripts introduced by a newer release, so use the
newer image for any required schema downgrade before starting older services.
Review data loss before running a downgrade; reverting CLI code does not undo
a migration already executed.

### Limitations

This command only changes one selected migration tree. It does not restore
data removed by a downgrade or coordinate PostgreSQL with object storage and
external systems. Follow the release-specific rollback procedure.

## Team wiki remembers its tree and edits title, parent and deletion in edit mode

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.11.0/docs/swift/ops/migrations/team-wiki-tree-state-and-edit-mode.md)

Existing wiki data and APIs are unchanged; tree state lives in each browser and starts collapsed.

See the source note for applicability, validation and rollback.

## Show the attachments sent with each user message

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.11.0/docs/swift/ops/migrations/turn-attachments-on-user-messages.md)

The field is optional in both directions: older pods ignore it, and stored messages without it render as before, so no data migration or deployment order is needed.

See the source note for applicability, validation and rollback.

## Compact icon buttons and a tighter menu radius

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.11.0/docs/swift/ops/migrations/ui-compact-icon-buttons.md)

The change ships with the normal deployment and stores no new data.

See the source note for applicability, validation and rollback.

## Move focus into opened menus and panels and back to their trigger

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.11.0/docs/swift/ops/migrations/ui-focus-handoff.md)

Keyboard focus behavior of menus, popovers and drawers only; nothing to configure or migrate.

See the source note for applicability, validation and rollback.

## Blur overlay backdrops and tint the scrim with the theme

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.11.0/docs/swift/ops/migrations/ui-overlay-blur.md)

The change ships with the normal deployment and stores no new data.

See the source note for applicability, validation and rollback.

## Render pages in one surface card with input-device navigation

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.11.0/docs/swift/ops/migrations/ui-shell-surface-card.md)

Layout and styling of the application shell only; nothing to configure or migrate.

See the source note for applicability, validation and rollback.

## Use design tokens for remaining raw radii and font sizes

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.11.0/docs/swift/ops/migrations/ui-style-tokens.md)

Stylesheet values now come from existing design tokens and unused calendar styles are removed; nothing to configure or migrate. A few sizes change visibly, listed under Limitations.

See the source note for applicability, validation and rollback.

## Unsent chat attachments stay drafts of their conversation

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.11.0/docs/swift/ops/migrations/unsent-attachments-composer-drafts.md)

Attachment rows and APIs are unchanged; new user messages record an empty attachment list when no files are sent.

See the source note for applicability, validation and rollback.

## Optional Zabbix template for Prometheus metrics

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.11.0/docs/swift/ops/migrations/zabbix-prometheus-template.md)

### Applicability

Existing Fred deployments upgrading to this release, including deployments
without Zabbix monitoring.

### Prerequisites

No prerequisites for the Fred upgrade. Operators adopting the template need a
Zabbix 7.0 instance that can reach each selected `/metrics` endpoint.

### Configuration

No Fred configuration changes are required. For an optional Zabbix import, set
`{$FRED.METRICS.URL}` separately on each host as described in
`deploy/zabbix/README.md`.

### Upgrade

Deploy Fred normally. Import `deploy/zabbix/fred-prometheus-by-http.yaml` only
if Zabbix collection of Prometheus metrics is wanted.

### Validation

Existing deployments need no additional validation. After an optional import,
confirm the HTTP and parsed items are supported and a numeric metric is
discovered on each configured host.

### Rollback

Use the normal Fred rollback procedure. Remove the optional Zabbix template
from monitoring hosts if its collection must be stopped.

### Limitations

The template was not imported into a live Zabbix instance during development.
Each exporter can expose many series, so review the name filter and retention
before applying the template broadly.

## Compact tabular schemas, preserve dates and explain SQL failures

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.11.0/docs/swift/ops/migrations/3458-tabular-tool-diagnostics.md)

### Applicability

Deployments using tabular MCP tools, CSV/Excel ingestion and the chat trace drawer.

### Prerequisites

Adapt custom consumers: `categorical_values` replaces `is_categorical` and
`sample_values`; `has_two_values` is removed. Bounds appear only on numeric
columns. The updated frontend still reads historical trace responses.

### Configuration

No configuration or permission changes. Optional `table_names` selects exact
aliases or unambiguous sheet/title labels; omitted/empty describes all tables.
SQL aliases and document UIDs do not change.

### Upgrade

For v3.11.0, use the coordinated maintenance window required by the in-thread
message cutover. Stage the compatible frontend, then upgrade Knowledge Flow
API/ingestion workers and agent pods before reopening user traffic, so compact
responses and packaged instructions agree. Do not expose the new frontend to
old runtime replicas. Restart long-lived local
processes when testing without reload.

New Excel ingestion preserves temporal Parquet types. Existing files stay
unchanged and truthfully typed. Reprocessing an existing source is optional and
deliberate; there is no bulk migration. Development validation explicitly
reprocessed only the synthetic Orion workbook.

### Validation

Describe all tables and then selected tables; verify the complete catalog and
compact columns. Check a newly ingested date column has an actual temporal SQL
type. A failed column query must suggest only already referenced tables. The
trace drawer retains submitted arguments, including table selectors, and the
safe cause without recovery advice. Zero-row success keeps its explicit message.

### Rollback

Roll back API, frontend and agent/worker versions together. Stored classification
remains compatible; temporal Parquet was already supported by the prior dtype
vocabulary. Do not convert correctly typed data back to text. Explicit source
reprocessing is not reverted automatically.

### Limitations

Prompt guidance does not guarantee correct calculations or eliminate redundant
calls. No result cache, duplicate-call suppression, multi-statement execution,
automatic UID substitution or new legacy-date repair policy is added. Complex
SQL scopes retain bounded redacted diagnostics. Token refresh is unchanged.

## Admin analytics redesign: team-scoped KPI presets, euro costs and Excel export

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.11.0/docs/swift/ops/migrations/redesign-admin-analytics.md)

### Applicability

Every deployment. All deployments with `sync_schema_on_init: false` must publish the new model (see Upgrade), whether or not they pin an `authorization_model_id`.

### Prerequisites

No additional prerequisites beyond the normal deployment procedure.

### Configuration

No new configuration key is introduced. If a service pins the OpenFGA model ID,
update that value after publishing the new model as described below.

### Upgrade

Deploy Fred normally. The OpenFGA model gains `team#can_read_analytics` (team admins) and is written at startup by default; with `sync_schema_on_init: false`, publish `libs/fred-core/fred_core/security/rebac/schema.fga` first. If any service pins `authorization_model_id`, update it to the returned model ID. Restart affected services and verify analytics access; without the new model, team admins are refused. No Alembic migration.

Behaviour changes for API consumers: KPI presets take repeated `team_ids` instead of `team_id`; team-scoped reads need `can_read_analytics`; several presets are removed and costs are reported in euros (`cost_eur`, `estimated_cost_eur`). Full list: `CONTROL-PLANE-PRODUCT-CONTRACT.md` §74. Organization observers now also see storage by team and web research.

### Validation

Open Administration > Analytics as a platform observer: the seven tabs load and "Export" downloads an `.xlsx` workbook.

### Rollback

Use the normal rollback procedure; this change introduces no data migration. API consumers of the removed presets need the previous release.

### Limitations

Capability usage needs the KPI dims of the `kpi-analytics-dims` change and counts only tool calls recorded after it. The user filter covers only users seen since the access rule started recording an attribute.
