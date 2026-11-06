# Migration guide - v3.10.0

Upgrade from: `code/v3.9.2`
Operational impact: **minor** (minimum version: `3.10.0`).

Review these procedures together in the listed dependency order before deployment. Customer-specific values remain in their private repositories; Fred chart values are the production reference. Configuration files named configuration_prod.yaml are for local development only.

No-operation declarations describe ordinary deployment only. Conditional activation steps still require preparation. Validate combined upgrade and rollback in staging before production.

## Handle HITL resume conflicts and rejected cancellations

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/2337-hitl-resume-rejections.md)

The optional history availability field is additive; stored checkpoints and database schema are unchanged. Deploy runtime and frontend normally.

See the source note for applicability, validation and rollback.

## Preserve Knowledge Flow MCP failure diagnostics

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/3196-kf-mcp-failure-diagnostics.md)

Normal shared-core and Knowledge Flow image deployment enables the diagnostics. No data migration, re-ingestion, permission changes or client updates are required.

See the source note for applicability, validation and rollback.

## Allow editing and toggling the self-test harness agent

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/3198-self-test-agent-updates.md)

The self-test harness templates were already exempt from the template capability gate at enrollment; the update path now applies the same existing exemption, with no data, tuple or schema migration.

See the source note for applicability, validation and rollback.

## Sandbox inline raw-content document previews

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/3200-sandbox-raw-content-previews.md)

Stored documents, APIs and the PDF preview are unchanged; the stream gains Content-Security-Policy: sandbox and X-Content-Type-Options: nosniff with a normal deployment.

See the source note for applicability, validation and rollback.

## Stop reporting chat attachment vectors as corpus orphans

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/3201-corpus-audit-session-vectors.md)

The audit reads existing session-scope chunk metadata through the vector-store adapter at run time; no data, index or schema migration is needed.

See the source note for applicability, validation and rollback.

## Make deleted document vectors immediately invisible in OpenSearch

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/3202-opensearch-delete-refresh.md)

The index, mappings and stored vectors are unchanged; the deletion refresh takes effect with normal deployment.

See the source note for applicability, validation and rollback.

## Render Mermaid previews with the active Fred theme

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/3252-themed-mermaid-previews.md)

Existing Markdown source and APIs are unchanged; the new preview takes effect with normal frontend deployment.

See the source note for applicability, validation and rollback.

## Kill the whole LibreOffice process tree when an Office-to-PDF conversion times out

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/3294-soffice-timeout-process-group.md)

No data, API or deployment order changes; a conversion that times out now stops soffice.bin with it instead of leaving it running, which takes effect with the normal deployment.

See the source note for applicability, validation and rollback.

## Add Mistral Large 4 to the local text model catalog

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/3320-mistral-large-4-local-catalog.md)

Existing deployments keep their configured catalogs and defaults; this adds a selectable profile to the developer catalog without changing runtime code, permissions or data.

See the source note for applicability, validation and rollback.

## Restore structured MCP tabular results in agent runtimes

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/3325-mcp-structured-results.md)

Normal deployment of the agent runtime activates the fix for existing tabular documents without re-ingestion or data migration.

See the source note for applicability, validation and rollback.

## Validate DOCX during metadata extraction

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/3338-docx-validation.md)

Normal deployment applies the validation fix to subsequent uploads without changing stored documents or requiring reprocessing.

See the source note for applicability, validation and rollback.

## Disclose partial native skill reads

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/3339-partial-skill-load-visibility.md)

Normal deployment suffices. Existing history remains readable, and native pagination and pinning keep their current behavior.

See the source note for applicability, validation and rollback.

## Publish the shared Python libraries 4.5.10 with structured MCP result support

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/3349-publish-python-packages-4-5-10.md)

fred-runtime 4.5.10 includes the structured MCP result normalization from #3325/#3326. No data migration, configuration change or re-ingestion is required.

See the source note for applicability, validation and rollback.

## Run the frontend unit test suite on pull requests

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/3350-frontend-unit-tests-ci.md)

The change adds a CI check on pull requests; deployed Fred components are identical before and after.

See the source note for applicability, validation and rollback.

## Show one chat card per object in a message

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/3353-one-chat-card-per-object.md)

The frontend now hides earlier versions of an object already present in the same message; stored conversations and parts are unchanged.

See the source note for applicability, validation and rollback.

## Show the disabled state on the shared Select

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/3358-select-disabled-state.md)

A disabled Select now looks disabled, with the same state tokens as a disabled Button; its behavior and API are unchanged.

See the source note for applicability, validation and rollback.

## Use the authenticated user's name in exported Word document metadata

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/3421-docx-author-username.md)

New Word downloads use the existing authenticated name or username without changing stored documents, APIs, or permissions. Normal deployment is sufficient.

See the source note for applicability, validation and rollback.

## Centralize the exact Node baseline in .nvmrc

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/3424-frontend-task-node.md)

Node is used during frontend builds; the deployed nginx runtime requires no extra upgrade operation.

See the source note for applicability, validation and rollback.

## Prepare Fred v3.10.0 release inputs

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/3433-prepare-v3-10-0-release.md)

This contribution consolidates the release inputs and corrects unpublished migration guidance; operational actions remain in the corresponding feature notes.

See the source note for applicability, validation and rollback.

## Keep Trivy CVE reports when image SBOM generation takes longer

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/3469-trivy-sbom-timeout.md)

CI retains the vulnerability report before generating license and SBOM evidence; deployed Fred components are unchanged.

See the source note for applicability, validation and rollback.

## Announce a finished chat answer on every page, including admin and settings

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/answer-toast-on-every-page.md)

The runtime and its APIs are unchanged; the toast is raised by the browser, so normal deployment is enough.

See the source note for applicability, validation and rollback.

## Show the agent description on the chat welcome card

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/chat-welcome-agent-description.md)

The card reads the agent description already returned by the existing agent listing; no data, API or permission changes, so normal deployment is enough.

See the source note for applicability, validation and rollback.

## Discover chat models from an OpenAI-compatible gateway

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/discover-chat-models-from-gateway.md)

### Applicability

All deployments must follow the database migration and coordinated rollout order below. Gateway configuration and discovery activation apply only to operators who want to list chat models from an OpenAI-compatible gateway; existing static catalogs need no configuration change.

### Prerequisites

The gateway must serve an authenticated `GET /models` under its inference base URL and return a JSON `data` array. Selected model ids must be distinct and valid. The source must contain chat-capable models only, or the operator must select chat ids with `include_model_ids`.

### Configuration

Set `applications.fred-agents.models_catalog.discovery` in the Fred chart values to a list of sources. Each entry needs a stable `source_id` and the gateway's `base_url`, and may set `include_model_ids`. A one-endpoint deployment still uses a one-item list. Provide `OPENAI_API_KEY` in the agent pod environment through the deployment's secret mechanism. All discovery URLs on that pod share this key. A sole manual chat profile becomes the pod default automatically; with multiple manual profiles, set `default_profile_by_capability.chat` explicitly. In Features > Models > Model defaults > Agent pods, the administrator can replace that YAML default with a chat profile advertised by the pod whose model is enabled platform-wide. A discovery-only pod can leave the YAML default unset and require an administrator to select one. Each pod can also select an enabled manual chat profile as its fallback when a selected discovered profile disappears. The Platform tab retains the existing provider/name/settings form for a global override that forces one model across managed turns. Existing catalogs without `discovery` require no change.

### Upgrade

Back up the control-plane and runtime databases, then apply their complete Alembic migration chains once, before rolling out services (control-plane head `b8e1f4a2c6d9`, runtime head `f6a7b8c9d0e1`, and independent `capability:ppt_builder` head `r9d3f4a5b6c7`). Deploy the control plane first, then every runtime replica, then the frontend. Avoid agent writes while old and new control-plane replicas coexist. Keep `supports_vision` out of catalogues read by older runtimes, including new chart defaults; enable it only after all runtime replicas have been upgraded. The following notes describe the individual additive revisions; do not downgrade or re-run intermediate revisions between services. This database and rollout order is required even when model discovery is not enabled. The follow-up revision repairs a development database already stamped at the earlier PR revision before the pod-default table was added; fresh installations create that table in the original revision. The inferred sole-manual-model default needs no separate migration. Configure discovery and restart the agent pods once to load the YAML. Later, a feature manager can refresh the URL currently active in a pod, while only a platform administrator can override its URL in Features > Models; both take effect without restarting pods. After a pod restart with a saved override, a platform administrator can refresh it, or a managed turn can restore it before a feature manager refreshes. Confirm that all model-capable pods use consistent source ids and inventories before selecting a discovered profile as a team default. Enable intended discovered models for teams in the admin Models view. An administrator can enter a display name there after discovery; it is saved in the control-plane database and appears in chat without a pod restart. A deployment with no effective pod chat default and no global override opens a required-choice dialog whenever a platform administrator selects Models; its action opens the Agent pods tab. The Platform tab keeps the existing global override form. New models are not granted automatically. Without the optional discovery configuration, retain the static model catalog after the required database migrations and coordinated rollout.

### Validation

Check that each pod's `/agents/models-catalog` lists the selected ids and its YAML default, then use Refresh in Features > Models > Discovery to confirm the latest inventory without a restart. Open Model defaults > Agent pods and verify that each dropdown displays its YAML default when activated; an inactive current YAML or saved value appears as a separate status and cannot be saved again. Enable a model platform-wide before selecting it as a pod default or manual fallback. Save a discovered chat profile for one pod and confirm a managed turn without an explicit model uses it; other pods keep their own defaults. Reset the selection and confirm the YAML default returns. Select a manual fallback for that pod. The admin view shows optional upstream metadata and warns if an agent catalog cannot be checked, without marking models removed. After a successful refresh confirms a model is absent from `/models`, the model appears greyed out and cannot be activated in the discovery table or selected as a pod default. The compact absence button opens a scrolling list; its red removal action requires confirmation and hides that absence without changing existing grants or routing evidence. Absence from `/models` does not prove that chat requests fail. A managed turn selecting a confirmed-absent profile uses the pod's manual fallback, or its manual YAML default when no fallback override exists. Check that a granted available model can be selected and used by a team. Save a display name in the admin view and confirm that it appears in chat while inference still uses the gateway id; clear it to restore the gateway label or identifier. A missing gateway or invalid inventory logs a startup warning; static profiles remain available and a saved override can be restored on a managed turn.

### Rollback

Clear any admin URL, pod-default and pod-fallback overrides, remove the discovery block, restore the previous static chat default and profiles if changed, and restart the pods with the prior image or catalog. Keep the additive discovery, display-name and pod-default tables when rolling back application code; saved data remains dormant while its capability ids are absent. Grants to discovery-only capability ids also remain dormant until those ids are advertised again.

### Limitations

The standard OpenAI model-list response does not define chat capability or token limits; the admin view displays only metadata supplied by the endpoint. A pod must restart after its YAML changes, while admin refresh and URL overrides apply immediately. Upstream id or source-id changes create new grant identities. Separate pods are needed for endpoints that require different keys until per-source credentials are supported.

## Document Docker Compose rollback after database migrations

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/docker-compose-rollback-runbook.md)

Existing deployments and data are unchanged; the new runbook applies when planning a future upgrade or rollback.

See the source note for applicability, validation and rollback.

## Verify frontend package dependencies against retained candidate evidence

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/frontend-registry-candidate-graph.md)

Existing Fred deployments do not change; release maintainers can resume the retained frontend publication through the normal workflow.

See the source note for applicability, validation and rollback.

## Help Center wording: conversation privacy and no product name in pages

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/help-center-wording.md)

Documentation-only wording fix bundled in the frontend; data, APIs and access rules are unchanged.

See the source note for applicability, validation and rollback.

## Suggest team agents on the home page until the user has used one

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/home-suggested-agents.md)

The suggestions reuse the existing recent-agents preset and team agent listing; no data, API or permission changes, so normal deployment is enough.

See the source note for applicability, validation and rollback.

## Keep iframe host tests compatible with patched DOM tooling

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/iframe-host-test-environment.md)

This is a test-only compatibility fix and requires no operator or deployment action.

See the source note for applicability, validation and rollback.

## Keep a streamed chat answer running when the user navigates elsewhere in Fred

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/keep-chat-turn-on-navigation.md)

The runtime and its APIs are unchanged; the browser simply keeps the existing stream open, so normal deployment is enough.

See the source note for applicability, validation and rollback.

## Keep speaker notes and chart data in fast PPTX extraction

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/pptx-fast-notes-and-charts.md)

The extractor reads the uploaded file only; new attachments benefit after a normal Knowledge Flow deployment.

See the source note for applicability, validation and rollback.

## Preserve chat queues and clarify background conversation status

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/preserve-chat-queue-on-navigation.md)

Only browser-tab queue ownership and local sidebar indicators change; deployment, runtime and database contracts are unchanged.

See the source note for applicability, validation and rollback.

## Restore pure SQL built-ins and tabular trace panels

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/prism-168-tabular-builtins.md)

Existing tabular artifacts, permissions and API payloads are reused; normal Knowledge Flow and frontend deployment enables the correction.

See the source note for applicability, validation and rollback.

## Raise the per-turn tool call limit to 100

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/raise-tool-call-limit.md)

Existing data and APIs are unchanged; the higher limit takes effect with normal deployment.

See the source note for applicability, validation and rollback.

## Regroup the admin self-test into families and add checks across the platform

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/self-test-families.md)

No deployment or configuration action is required. The optional role campaign changes a dedicated test account only after explicit confirmation and keeps a credential-free recovery record in its browser.

See the source note for applicability, validation and rollback.

## Simplify frontend npm releases with shared Make commands

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/simplify-frontend-npm-releases.md)

Existing deployments and already published npm versions remain unchanged; release maintainers use the new commands only for future frontend package releases.

See the source note for applicability, validation and rollback.

## Require team membership to list a team's sessions

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/team-sessions-membership.md)

The ReBAC schema already defines can_read_conversations for team members; the stricter check takes effect with normal deployment and needs no data or tuple migration.

See the source note for applicability, validation and rollback.

## Upgrade the Temporal Python SDK to 1.35.0

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/temporalio-135-security.md)

Normal image rebuild and deployment install the updated SDK; existing workflows, storage and server configuration require no migration.

See the source note for applicability, validation and rollback.

## Reclaim abandoned chat steering turns

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/turn-steering-cleanup.md)

Only application lifecycle cleanup changes; the existing mailbox schema and temporary JSON format remain unchanged.

See the source note for applicability, validation and rollback.

## Show the deployment's site name instead of "Fred" in user-facing UI text

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/ui-platform-wording.md)

Deployments without siteDisplayName keep showing Fred; branded ones show their name with the normal frontend deployment.

See the source note for applicability, validation and rollback.

## Patch Vite in frontend tooling and isolated consumers

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/vite-security-patch.md)

The patched Vite version is installed by the normal locked build; deployments require no additional steps.

See the source note for applicability, validation and rollback.

## Persist user display preferences in PostgreSQL

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/users-display-preferences.md)

### Applicability

Existing Fred deployments upgrading to a release that includes personal display preferences.

### Prerequisites

Back up the Control Plane PostgreSQL database using the normal deployment procedure.

### Configuration

No configuration changes are required.

### Upgrade

Apply the Control Plane Alembic migration that creates `users_preferences` before
rolling out the new Control Plane and frontend images. No existing table is
renamed. Existing users start without a row and see the documented defaults.
They choose their durable display settings again after rollout. Browser values
from an older deployment are ignored and do not populate the new table.

### Validation

Sign in with a test account, change the theme, display mode, language and
sidebar state, then reload with browser storage cleared. Check that the same
choices return and that `users_preferences` has one row for the test subject.

### Rollback

Roll back the frontend and Control Plane images normally. Leave the new table in
place so a later rollout can reuse saved choices. Dropping it discards choices
saved after the migration.

### Limitations

Personal choices from old browser storage are not migrated. An absent row or
failed preference read uses defaults for that load; the next load retries the
database read. Resizable pane widths and trace expansion stay in localStorage
and return to their defaults if browser storage is cleared. Pane widths are
clamped to the current viewport when rendered.

## Name new conversations with a generated title and choose its model

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/3346-generated-conversation-title.md)

### Applicability

Existing Fred deployments upgrading to this release.

### Prerequisites

The control-plane database must accept the Alembic revision `b5d2e8f7c031`.

### Configuration

No configuration changes are required.

### Upgrade

Apply the control-plane Alembic migrations before starting the new control plane, as for any release that adds a revision. The revision adds one nullable column, `creation_assistant_settings.title_model_profile_id`. Existing rows keep NULL, which follows the platform chat model. The runtime contract gains one optional request field (`runtime_context.auto_title`) and one stream event (`session_title`).

### Validation

Start a new conversation and send a long first message. While the answer is streaming, the sidebar and the chat header switch to a short generated title (3 to 8 words) instead of the beginning of the message. Later messages do not change the title. Renaming the conversation by hand still works and is kept.

To choose the title model, open the features admin page, then Model defaults and the Platform tab. This needs the right to edit the platform prompt. Reload the page and check that the choice is kept. Start a new conversation as a plain team member: the title is generated, and the runtime log shows no `session_title_failed` event.

### Rollback

Restore the previous images. The extra column is ignored by earlier versions, and titles that were already generated stay as they are. Keep the additive column during application rollback. Downgrading to `f28c3e9ab641` from this release also removes the later global skill policy table and its saved opt-outs. Only consider that downgrade after following the skill-policy rollback precautions and stopping all new control-plane replicas.

### Limitations

Each new conversation makes one extra small call on the title model, or on the platform chat binding or pod default chat model when none is chosen. Its input is bounded to 600 characters and the title is short. If that call fails, or is still running 2 s after the answer ends, the conversation keeps the beginning of the first message as its title. A chosen model that a pod no longer offers falls back to that pod's default chat model, with a warning in the runtime log. Conversations created before the upgrade keep their current titles.

## Enable packaged skills and add global skill policy

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/platform-skills-evolution.md)

### Applicability

Deployments upgrading agent runtimes, control plane and frontend for platform skills.

### Prerequisites

Back up the control-plane database. Review whether each agent pod should use the
packaged catalog, an existing custom directory or explicit `skills: null`.

### Configuration

An absent `skills` key or `{}` now uses `directory: package`. Use `skills: null`
to preserve an intentionally disabled installation. Existing custom paths keep
their meaning. Charts omit the optional key by default and retain explicit null.
Packaged resources remain English; the frontend translates their titles and
descriptions using trusted packaged provenance. No translation files are needed
for custom skills.

The unified visualization skill is named `graph` (`/graph`), displayed as
Visualisation in French and Visualization in English. It selects a diagram,
data chart or table using the rendering formats available to the agent.
Mermaid syntax/examples are a packaged reference read only for Mermaid output.
The former packaged `mermaid` name is no longer advertised; stored
messages keep their original text and selections. Existing retired-skill
handling applies to old names. If an installation tested this branch with a
disabled `mermaid` policy, review the retired entry and disable `graph` after
the runtime rollout if that opt-out is still intended. Custom skill names are
unchanged.

The packaged catalog has seven skills. `analyze-data`, `compare-options`,
`grounded-research` and `summarize-document` are model-only: direct user
selections are rejected, but agents can load them for natural-language requests.
`meeting-minutes` and `grill-me` require explicit user selection for a new load.
`graph` retains both invocation routes. Summary guidance has a short core and a
conditional complex-summary reference.

The separate `data-visualization` and `verify-answer` skills are retired without
aliases. Remove retired or newly user-ineligible commands from drafts and
integrations before resubmitting. Existing messages and usage records keep their
canonical names; a preview of a retired skill can return unavailable.

`graph`'s policy now governs the combined diagram/data-visualization scope.
Before rollout, review its enabled state and any old `data-visualization` opt-out.
Retired opt-outs are not transferred or deleted automatically. If visualization
must stay disabled, disable `graph`; this also disables its diagram workflow.

### Upgrade

1. Apply the linear control-plane migration `d7b24ef08361` after `b5d2e8f7c031`.
   It creates a small global policy table; no existing data is rewritten.
2. Deploy the new control plane before new runtimes, so direct runtime execution
   can read `/platform/skills/policy`. Deploy all configured runtime replicas,
   then the frontend. Do not disable any skill until all runtime replicas have
   completed the rollout.
3. Open Administration > Features > Skills. Check all sources are available and
   policy-capable before setting global opt-outs. Absence of a policy row means
   enabled. Stored opt-outs can be re-enabled even when all sources are offline.
4. Confirm all runtime replicas publish the new seven-entry snapshot before
   treating command discovery as uniform. A stale selection reaching an updated
   replica is rejected through the existing unavailable/user-ineligible behavior.

New runtimes request managed bindings with `X-Fred-Skill-Policy: 1` and read the
shared policy for direct template execution. Catalog relays request metadata
version 1; runtimes retain version 0 responses for older control planes.

### Validation

Verify default skills and both locale labels, select `/grill-me`, and check its
load activity. Disable a packaged skill, start another turn in an existing
conversation and on another replica, and verify discovery and new loads reject
it. Re-enable it and verify the next turn can load it again. Custom directories
are outside this global policy.

Check `/graph` and `/meeting-minutes` remain selectable while the four
model-only skills stay absent from the menu. Submit natural analysis, comparison,
research and summary requests and inspect actual load activity. Mermaid output
should read the graph reference; other visualization formats use their tool contract.
Verify a historical retired-skill event stays readable and stale drafts keep
their text when a command is rejected.

### Rollback

Re-enable all disabled skills before rolling runtimes back. Older raw-template
runtimes cannot enforce this new policy. An older managed runtime is refused
when disabled names exist. Restore earlier configuration or explicitly set
`skills: null` if needed. The additive table can remain during application
rollback; downgrade it only after new control-plane replicas have stopped, since
downgrade deletes stored opt-outs.

Restoring the preceding runtime/frontend packages also restores their prior
catalog and invocation modes. Roll back every runtime replica and review the
`graph`/retired-name policies again; history and retained policy rows need no
reconstruction.

### Limitations

An inventory URL behind a load balancer cannot prove that every replica has
upgraded. The completed runtime rollout is an operator prerequisite. Policy
changes apply to the next turn, including resumes; they do not interrupt an
in-flight turn or erase instructions already in checkpointed context. A configured
control plane that cannot serve fresh policy causes direct execution to fail closed.

## Reserve packaged grounded research for autonomous model invocation

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/3402-grounded-research-model-only.md)

### Applicability

Deployments using the packaged platform skill catalog. Custom skill directories
retain their authored invocation metadata.

### Prerequisites

Review drafts and integrations that explicitly select `grounded-research`.

### Configuration

No configuration or permission changes are required. Existing global skill
enablement policy continues to apply.

### Upgrade

Deploy the updated runtime package to every runtime replica. Remove explicit
`grounded-research` selections from drafts or integrations before resubmitting;
ask the research question in natural language so the model can choose the skill.
Mixed runtime versions can advertise different invocation modes during rollout.

### Validation

Verify `grounded-research` is absent from user commands and explicit selections
are rejected before inference. Inspect an autonomous ReAct or Deep load to confirm
the research instructions remain available with agent-origin attribution.

### Rollback

Restore the preceding runtime package on every replica to restore both invocation
routes. No database migration or history rewrite is introduced.

### Limitations

Already-loaded instructions retain the existing conversation continuity behavior.
Autonomous model selection remains dependent on the request and available tools.

## Queue and send messages during active agent turns

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/chat-active-turn-steering.md)

### Applicability

Existing Fred deployments upgrading to this release.

### Prerequisites

The runtime's shared PostgreSQL database must be available, as for checkpoints and history.

### Configuration

No configuration changes are required.

### Upgrade

Run the fred-runtime Alembic migration before updating runtime replicas. The normal chart migration job performs this step. The runtime checks for `runtime_turn_steering` at startup and remains unready if the table is missing.

### Validation

With two `fred-agents` replicas, start an agent turn on one pod, submit Send through the other, and verify the message reaches the agent at the next model boundary. Repeat with a tool confirmation and resume on the other pod.

### Rollback

Roll back the runtime and frontend together. The older runtime ignores the new table; downgrade the migration only after no updated replicas remain.

### Limitations

The ordinary pending list still lives in the browser and is lost on page reload. A pod failure between injection and the delivery event can leave the outcome uncertain; the UI does not retry automatically. Paused steering rows expire after 30 days.

## Add the ppt_builder capability with background template analysis, agent readiness and a platform default template

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/ppt-builder-capability.md)

### Applicability

Fred deployments upgrading fred-agents, the control plane and the frontend. The
`ppt_builder` capability ships in the existing `fred-capability-ppt-filler`
package, so every agent-pod that installs that package registers it.

### Prerequisites

- fred-core, fred-sdk and fred-runtime 4.6.0. The ppt-filler package needs
  fred-core and fred-sdk 4.6.0 or later, the control plane fred-sdk 4.6.0, and
  fred-agents fred-runtime 4.6.0 (the readiness hook, the capability model port
  and the route team authorizer ship there).
- The fred-agents migration hook (`python -m fred_runtime migrate`) must run, as
  for any release: it now also creates `cap_ppt_builder_analysis` and
  `cap_ppt_builder_deck_plan` under their own version table
  `cap_ppt_builder_alembic_version`.
- Every agent-pod image that installs this package needs headless LibreOffice
  Impress for previews and template analysis, plus suitable fonts and
  Fontconfig aliases for its templates. The package README lists the Ubuntu
  packages used by `fred-agents`; these system dependencies do not come with
  the Python package.

### Configuration

- `supports_vision` (optional, default `false`) on a model catalogue profile
  declares that it accepts images. The chart values flag the bundled OpenAI,
  Azure and Mistral Medium profiles. Operators with a private catalogue overlay
  add `supports_vision: true` to their multimodal profiles; without it, template
  slides are labelled by rules only and the agent form says so.
- While any older runtime can read the catalogue, omit `supports_vision`
  entirely, including the keys supplied by the new chart and private overlays.
  Older pods reject unknown model profile keys and fail to boot. After all
  runtime replicas use the new image, enable the intended flags and restart
  those replicas. Without these flags, template analysis uses rules only.
- No new secret or permission: labelling goes through the agent's own routed
  chat model, within the team's usable models. The platform default template
  is labelled through the pod's default chat model, or the model a capability
  manager picks, with no team restriction.
- Optional activation: a platform admin or feature manager can replace the
  default template of agents without their own in Admin > Features, on the
  "Presentation builder" row. Nothing changes until someone does.

### Upgrade

1. Back up the databases and apply the complete release migration chains as
   described in the discovery note. The control-plane head is
   `b8e1f4a2c6d9`; its parent is `d7b24ef08361`. The runtime head remains
   `f6a7b8c9d0e1`, and the independent `capability:ppt_builder` tree advances
   from base to `r9d3f4a5b6c7`. Its migration creates the analysis and deck-plan
   tables under `cap_ppt_builder_alembic_version`.
2. Deploy the control plane before all runtime replicas, then the frontend,
   following the release's skill-policy rollout. Avoid agent writes while old
   and new control-plane replicas coexist: new replicas can persist
   `capability_pending`, which old replicas cannot read. The new control plane
   treats an older runtime's readiness endpoint returning 404 as ready; other
   readiness failures can leave an agent suspended until a successful check.
3. Cost: each template upload (or vision setting change) makes one vision call
   per example slide, at most four at a time, once per template hash. A
   20-slide template is about 20 calls. The built-in template ships analysed.
4. A platform default template takes up to two `cap_ppt_builder_analysis` rows
   (in use, and a replacement being analysed; bytes in Postgres, 50 MB at most
   each). A replacement applies once its analysis succeeds. Each fred-agents
   replica reads it at most every 30 s, so replicas may differ for that long.

### Validation

- `cap_ppt_builder_analysis`, `cap_ppt_builder_deck_plan` and
  `cap_ppt_builder_alembic_version` exist in the fred-agents database;
  `agent_instance.suspension_detail` exists in the control-plane database.
- Create an agent with the "Presentation builder" pack and upload a `.pptx`:
  the save returns at once, the form shows "analysis in progress", the agent is
  unavailable in chat until the analysis succeeds, then a request such as
  "prepare a 6-slide deck on our Q3 results" returns a preview and a download.
- Optional: as a platform admin, upload a `.pptx` in the "Presentation builder"
  settings of Admin > Features; once analysed, an agent without its own
  template builds on it, and "Reset" brings back the Fred template.

### Rollback

1. Follow the release's skill-policy rollback precautions. Keep the new control
   plane available while rolling back every runtime replica: new runtimes need
   its skill-policy endpoint for direct turns. Remove `supports_vision` from
   retained catalogue overlays before starting any old runtime.
2. Once all new runtimes have stopped, drain and stop every new control-plane
   replica before removing its mapped column. Using the new image and the
   deployment's database configuration, execute
   `alembic downgrade d7b24ef08361` for the control-plane tree. This reverts
   only the PPT revision, clears `capability_pending` suspensions and drops
   `agent_instance.suspension_detail`, preserving global skill policies.
   Verify that no agent retains `capability_pending`, then start the prior
   control-plane version and roll back the frontend. Do not run new replicas
   against the downgraded schema.
3. Keep the additive PPT analysis and deck-plan tables; older versions do not
   read them. If removal is required, stop all replicas that can analyse
   templates or save decks, then use the new image's migration tooling and the
   deployment's database configuration to downgrade the independent
   `capability:ppt_builder` tree to base. This permanently deletes stored
   templates, analyses and plans.

Agents configured with `ppt_builder` stop working on an older release, which
does not know the capability; their stored configs are kept.

### Limitations

- `cap_ppt_builder_deck_plan` rows are not deleted with their conversation;
  each is a few KB. They can be deleted at any time: a later edit of that
  conversation's deck then asks the model for the whole deck again.
- An analysis interrupted by a pod restart is resumed on the next save, chat
  turn or readiness check, from any replica, up to three attempts; a resumed
  analysis on a replica that did not take the save labels by rules.
- Until the control plane re-checks readiness (agent listing or form poll), a
  freshly analysed agent may stay unavailable for a short while.

## Keep vector chunk folders in sync when documents are linked, unlinked or refiled

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/3199-vector-folder-membership.md)

### Applicability

Deployments where users link an already indexed document to another folder,
remove it from one of several folders, or where library sync moves documents
between folders. Every vector store is concerned: OpenSearch, pgvector,
ClickHouse, Chroma and the in-memory development store.

Before this release a link changed only the document's stored membership. Its
indexed chunks kept the folder ids from ingestion, so corpus search never found
the document from a newly linked folder. From this release, link, unlink and
refile update the chunks first and fail the request if the vector store rejects
the update. No search request is slower.

### Prerequisites

The vector store must be reachable when users link or unlink documents: a link
now fails instead of silently leaving the index stale.

### Configuration

No configuration changes are required.

### Upgrade

Deploy Knowledge Flow normally. This is enough for every link, unlink and
refile made after the upgrade.

Optional remediation: documents whose folders changed after ingestion and
before this upgrade keep stale chunk folders, and stay unsearchable from the
folders they were added to. No automatic backfill is shipped. To list the most
likely candidates (vectorized documents in more than one folder), run on the
Knowledge Flow PostgreSQL database:

```sql
SELECT document_uid, tag_ids
FROM metadata
WHERE cardinality(tag_ids) > 1
  AND doc #>> '{processing,stages,vector}' = 'done';
```

To repair one document, link it to any additional folder and then remove it
from that folder again. Each step rewrites the folders on all of its chunks
from its current membership; nothing is re-embedded. Never remove a
document's only folder: that deletes the document. A document that was moved
(linked elsewhere, then removed from its original folder) has one folder and
is not listed by the query; repair it the same way if search in its folder
misses it.

### Validation

Link an indexed document from folder A to folder B, then search only folder B
in a conversation: the document is returned. Remove it from A: a search of A no
longer returns it and B still does. With the vector store stopped, a link
attempt fails and the document stays only in A.

### Rollback

Use the normal rollback procedure. Chunk folders written by this release remain
valid for the previous one; links made after a rollback are stale again.

### Limitations

ClickHouse updates the `tag_ids` column search filters on; the JSON metadata
copy shown by the raw chunk view keeps ingestion-time folders. A link made
while the document is still being vectorized can be overwritten by the chunks
that ingestion writes afterwards. Chroma now stores a non-empty folder list
as a native array, which requires the pinned chromadb 1.5.x. Verified offline
and with a live pgvector chunk update; live OpenSearch and a full live search
were not exercised.

## Make the document retrievability toggle effective on pgvector

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/3203-pgvector-retrievable-toggle.md)

### Applicability

Deployments whose Knowledge Flow vector store is pgvector. Before this release,
turning a document's retrievability off on pgvector was saved in its metadata
but never reached its indexed chunks, so the document stayed searchable.
OpenSearch, ClickHouse and Chroma deployments need no action.

### Prerequisites

No additional prerequisites beyond the normal deployment procedure.

### Configuration

No configuration changes are required.

### Upgrade

Deploy Fred normally. New toggles take effect on the chunks immediately.

Documents switched off **before** the upgrade are still searchable on pgvector
and must have the toggle re-applied once. List them in the Knowledge Flow
database:

```sql
SELECT document_uid, doc -> 'identity' ->> 'document_name' AS name
FROM metadata
WHERE (doc -> 'source' ->> 'retrievable')::boolean IS FALSE;
```

For each one, re-apply the toggle with a user allowed to update the document:
`PUT /knowledge-flow/v1/document/metadata/{document_uid}?retrievable=false`
(idempotent), or switch it on and off again in the document list.

The toggle now fails with HTTP 500 instead of reporting success when the
vector store cannot apply it; the metadata then keeps its previous value and
the request can be retried.

### Validation

Switch a vectorized document off, run a search that matched it, and check it
is no longer returned; switch it back on and check it is returned again. For a
re-applied document, its chunks carry `"retrievable": false`:

```sql
SELECT DISTINCT e.cmetadata ->> 'retrievable'
FROM langchain_pg_embedding e
WHERE e.cmetadata ->> 'document_uid' = '<document_uid>';
```

### Rollback

Use the normal rollback procedure; no data migration is involved. The previous
version already filters search on the chunks' `retrievable` field, so documents
switched off stay hidden, but new toggles stop reaching the chunks again.

### Limitations

pgvector filters retrievability after the nearest-neighbour query (on four
times the requested number of hits, capped at 200). A disabled document never
appears in results, but one whose chunks dominate the nearest neighbours can
reduce the number of hits returned for a query.

## Ingest Outlook .msg and .eml mail files

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/3306-email-file-ingestion.md)

### Applicability

Existing Fred deployments. Impact is **minor** only for overlays that replace the
processor lists: they must add the entries below. Deployments using the bundled
chart lists get mail support with a normal deployment.

### Prerequisites

None. `python-oxmsg` (MIT), `beautifulsoup4` and `markdownify` become direct
Knowledge Flow dependencies; they were already installed, so the image is unchanged.

### Configuration

Reference: [the Fred chart values](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/deploy/charts/fred/values.yaml).
Overlays that replace `processing.profiles.<profile>.input_processors` (every
profile, API and workers) add:

```yaml
- suffix: ".msg"
  class_path: knowledge_flow_backend.core.processors.input.email_processor.email_markdown_processor.EmailMarkdownProcessor
- suffix: ".eml"
  class_path: knowledge_flow_backend.core.processors.input.email_processor.email_markdown_processor.EmailMarkdownProcessor
```

Overlays that set `attachment_processors` explicitly add:

```yaml
- suffix: ".msg"
  class_path: knowledge_flow_backend.core.processors.input.fast_text_processor.fast_email_processor.FastEmailProcessor
- suffix: ".eml"
  class_path: knowledge_flow_backend.core.processors.input.fast_text_processor.fast_email_processor.FastEmailProcessor
```

Without them, `.msg` and `.eml` uploads stay refused as before.

### Upgrade

1. Reconcile the processor lists above in any overlay that overrides them.
2. Deploy Fred normally; the rolling restart applies the lists.

### Validation

Upload a `.msg` and an `.eml` into a team library: the preview shows a From / To /
Cc / Date / Subject header, the body and the attachment names, and the author is
the sender. An encrypted mail fails once, with a message saying so.

### Rollback

Normal rollback; no data migration. Ingested mails stay ordinary markdown
documents; new mail uploads are refused again.

### Limitations

Caps are fixed in code: 25 MB per mail, 10 document attachments read per mail.
Images and archives keep their names only. LibreOffice conversions now stop after
300 s. Recipients are stored but not filterable; Bcc is never stored.

## Require Node 24 for frontend builds and package consumers

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.10.0/docs/swift/ops/migrations/node24-frontend-toolchain.md)

### Applicability

Frontend source builds, development containers, CI and consumers of the shared frontend npm packages.

### Prerequisites

Install the exact Node version in `.nvmrc` (24.22.2 for this release) and npm 11.19.0. The supported Node range is >=24.21.0 <25; Node 22 and Node 25 or newer are unsupported. Release preparation retains exact Node/npm pins.

### Configuration

No deployment configuration changes are required. Custom build environments must use the supported tooling before installing dependencies.

### Upgrade

Upgrade custom builders and local Node installations, then reinstall with `npm ci` in the affected frontend workspace. Rebuild existing development containers. Official frontend images include the updated builder; their deployed nginx runtime is unchanged.

### Validation

Check `node --version` and `npm --version`, then run the normal frontend build/tests and package consumer validation. Unsupported Node versions must fail before installation or build, including with an existing dependency tree.

### Rollback

Revert the toolchain change together with its manifests, lock metadata and contracts. Node 22 cannot validate dependency updates that require newer Node APIs, so revert those updates as well if restoring the previous toolchain.

### Limitations

This change publishes no npm packages or release tags. Previously built browser assets and persisted data require no migration. Consumers install Node 24 before adopting packages with the new engine contract.
