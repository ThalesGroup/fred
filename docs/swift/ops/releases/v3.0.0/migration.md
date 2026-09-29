# Migration guide — v3.0.0

Upgrade from: `code/v2.2.3`
Operational impact: **major** (minimum version: `3.0.0`).

Review these procedures together in the listed dependency order before deployment. Customer-specific values remain in their private repositories; Fred chart values are the production reference. Configuration files named configuration_prod.yaml are for local development only.

No-operation declarations describe ordinary deployment only. Conditional activation steps still require preparation. Validate combined upgrade and rollback in staging before production.

## Delegated execution and renewable workload credentials

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.0.0/docs/swift/ops/migrations/2808-delegated-execution.md)

## Delegated execution: upgrade and optional activation

PR: [#2808](https://github.com/ThalesGroup/fred/pull/2808)

Operational impact: **minor** under the agreed migration policy, because optional
activation requires configuration, IAM and OpenFGA operations. The ordinary
upgrade with delegation disabled requires no new mandatory configuration fields.
This classification is input to release preparation, not a published version.
Evaluate the complete release range from the last deployed tag separately.

### Configuration

The production reference is [the Fred chart values](https://github.com/ThalesGroup/fred/blob/code/v3.0.0/deploy/charts/fred/values.yaml),
with its generated `values.schema.json`. DevOps reconcile those values with each
customer's deployment repository. Customer secrets and private values need not be
copied into Fred. `apps/*/config/configuration_prod.yaml` is for local developer
Docker Compose only.

### Applicability

- Missing `security.delegation` defaults to both switches being `false`. Existing
  configurations do not need new fields merely to keep the feature off.
- The chart now includes the switches for Control Plane, Knowledge Flow and Fred
  Agents. At `applications.<application>.configuration.security`, the optional
  explicit setting is:

  ```yaml
  delegation:
    act_for_people: false
    accept_delegated_calls: false
  ```

- Do not use `delegation.enabled`; that obsolete key is rejected. Do not deploy
  the local-development `FRED_LOCAL_DELEGATION_FILE` override in production.
- This PR adds no Alembic revision relative to `swift`. Check the full release
  range for other database changes before deployment.
- No delegation-specific IAM provisioning, OpenFGA upgrade or coordinated full
  shutdown is required merely to leave delegation disabled. Apply the normal
  deployment procedure and validate it in staging; mixed-version operation and
  zero downtime have not been established by this PR.

The switches do not disable all changes: service-token renewal and bounded 401
retry, authentication diagnostics, authorization responses and frontend contracts
also change. Deploy matching release components. Do not grant `delegation_caller`
to ordinary service identities as a preparation step: holders lose ordinary
service-role shortcuts even while delegation is off.

Before admitting production traffic, check ordinary login, document access, agent
execution and service-to-service cleanup. Exercise token renewal on a long-running
request. Confirm healthy startup and no unexpected 401/403 responses. Keep previous
chart/image versions and effective values available for rollback.

### Upgrade

1. Record previous effective values, image/chart versions, IAM role assignments
   and OpenFGA store/model identifiers. Preserve authorization tuples. Validate
   the procedure in staging before enabling production traffic.
2. Provision workload credentials and the configured caller role and audience
   (defaults: `delegation_caller` on `fred-delegation`). Verify issuer trust and
   login-client exclusions. See [Keycloak](https://github.com/ThalesGroup/fred/blob/code/v3.0.0/docs/swift/platform/KEYCLOAK.md).
3. Use OpenFGA 1.10 or later. Publish/select a compatible model with
   `suspended` on every participant; reconcile any pinned model identifiers.
   See [suspended accounts](https://github.com/ThalesGroup/fred/blob/code/v3.0.0/docs/swift/platform/REBAC.md#suspended-accounts--suspended).
4. Stop admission of new agent work and drain or explicitly cancel existing runs
   for this coordinated activation. Do not assume a mixed on/off rollout is safe.
5. Set `accept_delegated_calls: true` on Control Plane and restart it. Wait for
   successful startup: it validates the model. Leave its `act_for_people` false.
6. Enable `accept_delegated_calls` on Knowledge Flow and other receiving services;
   restart affected readers, including workers sharing their configuration, and
   verify readiness. Leave outgoing delegation false on non-agent backends.
7. Set `act_for_people: true` on Fred Agents. Also set `accept_delegated_calls:
   true` on agent runtimes receiving delegated calls; such runtimes require both
   switches. Reconcile custom MCP catalogs: servers used under delegation must
   declare `auth_mode: delegated` and support the grant transport. The chart's
   first-party catalog entries already use that mode. Restart affected runtimes.
8. Verify delegated access for an allowed person, refusal for a suspended or
   unauthorized person, token renewal and cleanup. Resume admission only after
   these checks pass. Failed readiness or authorization checks stop activation.

Configuration is read at startup. Adapt workload names and restart commands to
the customer's deployment. The local `make delegation` helper is not a production
provisioning procedure. For credential changes, follow
[workload secret rotation](https://github.com/ThalesGroup/fred/blob/code/v3.0.0/docs/swift/ops/WORKLOAD_SECRET_ROTATION.md).

### Rollback

Stop new delegated work and drain or cancel active runs. Disable outgoing
and incoming delegation on affected services, restart them and verify ordinary
access before resuming traffic. Disable delegation everywhere before selecting
an older OpenFGA model or rolling back to binaries without delegation support.

**Disabling delegation also stops the new account status enforcement.** Retained
suspension tuples alone no longer block access: establish the required fallback
access controls before admitting traffic. This is not a security-equivalent
rollback for deployments relying on suspension enforcement.

Restore prior chart/images and effective values as required. Restore IAM role
assignments separately, including removal of newly granted caller roles when
returning to ordinary service identities. A Helm rollback does not restore IAM,
OpenFGA tuples/model selection or database state. Retain compatible model/tuples
unless an explicitly verified recovery procedure requires changing them.

### Limitations

With a delegation switch on, a service checks account status on every
authenticated request, login bootstrap and profile included, so it serves only
while its OpenFGA store is reachable: during an OpenFGA outage every
authenticated request to it returns 503 `account_status_unavailable`.

With `act_for_people` on, a person whose identity-provider subject identifier
contains `*` or `#` cannot start an agent run: admission refuses it with 403.

Configuration defaults and chart changes were checked against the implementation.
Automated authentication/runtime tests and CI cover code behavior; a production
upgrade, coordinated activation and rollback have not been executed. Customer
operators must validate their deployment procedure in staging. No private customer
configuration is needed to understand this note.

### Prerequisites

For default-off upgrades, retain existing IAM configuration. Optional activation
requires compatible OpenFGA, workload credentials, caller roles and audiences as
listed in the ordered upgrade procedure. Save the previous effective values and
model identifiers before starting.

### Validation

Verify ordinary login, document access, agent execution, cleanup and token renewal
before admitting traffic. For activation also verify a permitted delegated call,
a suspended-person refusal and readiness of all participants. Validate coordinated
rollback in staging; automated tests are not evidence of a production rehearsal.

## Create theme S3 Secret only when the frontend theme is configured

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.0.0/docs/swift/ops/migrations/2823-frontend-theme-s3-secret.md)

Deployments with a configured frontend theme and both storage keys retain the Secret; deployments without a theme only lose an unused Secret during normal deployment.

See the source note for applicability, validation and rollback.

## Hide the team administrator charter when disabled

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.0.0/docs/swift/ops/migrations/2824-disabled-team-admin-charter.md)

### Applicability

All Fred deployments upgrading the control-plane backend and frontend. The staged
order below matters when `app.team_admin_charter_version` is configured.

### Prerequisites

Check whether the team administrator charter is enabled. Keep the previous
frontend image available for a staged upgrade. This change needs no database
migration or data backfill.

### Configuration

Keep `app.team_admin_charter_version` as configured. An unset value continues to
disable the charter; no new setting is needed.

### Upgrade

1. If the charter is enabled, deploy the updated control-plane backend while
   keeping the previous frontend. Wait for the backend to become ready and
   confirm authenticated `GET /control-plane/v1/frontend/bootstrap` returns
   `team_admin_charter_enabled: true`.
2. Deploy the updated frontend. When the charter is disabled, the normal paired
   Fred deployment is sufficient.

### Validation

With the charter disabled, sign in as a team administrator and verify that team
settings omit Responsibilities and that its direct URL redirects to Members.
With the charter enabled, verify that eligible administrators still see
Responsibilities and pending administrators can reach the Accept action.

### Rollback

If the charter is enabled, revert the frontend before the control-plane backend
so it never relies on an absent bootstrap field. There is no data migration to
reverse.

### Limitations

A new frontend served by an old control-plane backend cannot detect an enabled
charter and temporarily hides its entry points. Pending administrators cannot
accept until the backend is updated; this is why the backend deploys first.

## Centre the announcement banner title when its description wraps

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.0.0/docs/swift/ops/migrations/announcement-banner-title-alignment.md)

Presentation-only frontend change; stored announcements, APIs and per-browser dismissal state are untouched.

See the source note for applicability, validation and rollback.

## Delegation hardening: account status per request, renamed denial causes, bounded audit and logs

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.0.0/docs/swift/ops/migrations/delegation-account-status-and-logging.md)

### Applicability

Existing Fred deployments upgrading to this release, and external agent pods or first-party application backends built on the published Python libraries. With both delegation switches off, the operational change is limited to the `rebac_denied` audit event; everything else applies only with a delegation switch on.

The four Python libraries (`fred-pod`, `fred-core`, `fred-sdk`, `fred-runtime`) are prepared for coordinated publication as 4.4.0, with aligned internal dependency minimums. Publish in the documented order: pod, core, SDK, then runtime.

### Prerequisites

No additional prerequisites beyond the normal deployment procedure. Activating delegation still follows the delegated execution activation note.

### Configuration

No configuration changes are required. No key, default or chart value changes, and the authorization model keeps only the `suspended` relation.

### Upgrade

Deploy Fred normally, then:

- If a SIEM or log rule reads `user_id`, `team_id` or `agent_instance_id` from `rebac_denied`, update it: the event now carries only its outcome and reason.
- Upgrade external consumers of the Python libraries to 4.4.0 together. In `fred_core`, `StandingAuthorizationError` becomes `AccountStatusError`, and `resolve_request_principal` and `resolve_delegated_principal` are no longer exported; a subject is established through the shared user dependency. On `RebacEngine`, `enforces_standing`, `require_user_standing` and `validate_standing_model` become `requires_active_accounts`, `require_active_account` and `validate_account_status_model`, and `grant_default_standing`, `mark_standing_seed_ready`, `is_standing_seed_ready` and `remove_user_standing` are removed.

### Validation

With both delegation switches off:

- A managed agent run refused for a missing team permission returns 403 with `X-Fred-Denial-Cause: permission_refused` and writes one `rebac_denied` audit event carrying only outcome `rejected` and reason `permission_refused`.
- No request or tool call reads account status, and Knowledge Flow keeps its `http` request and response lines.

With a delegation switch on:

- Start a receiving service before the control plane and confirm it starts; a person deleted through the platform is refused on their next request.
- Each authenticated request, from a signed-in person, a person named by a grant or a service identity, makes one account status check before its route runs. A suspended subject receives 403 with `X-Fred-Denial-Cause: account_suspended` and one `authorization.account.refused` audit event with reason `account_suspended`. With OpenFGA unreachable, every authenticated request other than a tool mount's initialization and tool listing returns 503 with `X-Fred-Denial-Cause: account_status_unavailable` and the same event with reason `account_status_unavailable`.
- A managed run refused for a missing team permission writes the same bounded `rebac_denied` event; a refused or unavailable account status writes none.
- Each request produces one access line carrying only a neutral event, outcome, method and status; Knowledge Flow's own `http` logger writes nothing.
- A tool mount only authenticates: initializing and listing tools make no account status check, and each mounted tool call makes one, in the route that serves it.
- A delegated run checks account status before every tool call; a run without delegated credentials makes no per-tool account status check.
- A workload presenting a grant receives 403 `requires_own_credential` on agent-instance enrollment and update, with or without asset uploads, on session, bulk session and attachment deletion, and on knowledge-base instance creation and deletion. Managed execution preparation for a person named by a grant succeeds and returns no capability chat controls.
- A grant whose `person`, `run` or `agent` value contains `*` or `#` names nobody: the receiver audits `delegation.grant.rejected` with reason `invalid_parameters` and treats the caller as itself. With `act_for_people` on, admitting such a run returns 403 `delegation_unavailable` and keeps no run record.
- Each delegated onward request records one `fred_auth_m2m_acquire_seconds` sample, plus one per 401 renewal; the retry reuses the renewed token. A failed acquisition ends the run with `delegation_unavailable` and writes one log line naming only the error type.
- A team-wiki call refused under delegation ends the run with `authority_lost`, and a failed workload-token acquisition ends it with `delegation_unavailable`, instead of returning tool text or an unavailable-wiki prompt block.
- With delegated execution on, run the admin session-expiry self-test; it passes and reports that the agent held no person credential.

### Rollback

Use the normal rollback procedure; this change introduces no data migration.

### Limitations

- With a delegation switch on, a service serves authenticated requests only while its OpenFGA store answers: during an outage every authenticated request, login bootstrap and profile included, returns 503 `account_status_unavailable`, with no exemption for service identities; a tool mount still initializes and lists tools, and each tool call is refused. A first-party application backend gets this check's engine from the shared ReBAC SDK factory; without it, every authenticated request is answered the same way.
- The frontend has no specific handling for `account_suspended` or `account_status_unavailable`: it shows them as any other 403 or 503 response.
- A suspension applies from the person's next request. A request that has passed its check completes, and background work it admitted finishes; a delegated run rechecks account status before every tool call. A suspended person can still initialize a tool session and list tools; each tool call is refused.
- The denial causes `account_suspended` and `account_status_unavailable` and the audit event `authorization.account.refused` replace the names delegation used before its first release. This is a contract change for unreleased delegation: SIEM and log-pipeline rules prepared for delegation must match the new names.
- `rebac_denied` carries only its outcome and reason in either setting; unlike the last release, it names no user, team or agent instance.
- An application acting for a person through a grant cannot enroll or update agent instances, delete sessions or attachments, or create or delete knowledge-base instances: those operations require the person's own credential. Managed execution preparation for such a person returns no capability chat controls.
- With `act_for_people` on, a person whose identifier contains `*` or `#` cannot start an agent run.
- OpenFGA accepts no `:` inside an identifier, so with a delegation switch on, a person whose subject identifier contains one, such as a user federated without import, is refused on every authenticated request with 503 `account_status_unavailable`, although a grant may name them.
- A refused team-wiki call ends the whole delegated run instead of letting the model continue without the wiki. The team-wiki capability package requires `fred-sdk` 4.2.0 or later.
- With a delegation switch on, log queries built on Knowledge Flow's `http` logger find no lines; use the access line and the `api.request_latency_ms` KPI.

Automated tests cover this behaviour; it has not been exercised in a production deployment.

## Enable Mistral Medium reasoning in the agent model catalogs

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.0.0/docs/swift/ops/migrations/mistral-medium-reasoning.md)

### Applicability

Local Fred developers and deployments using the bundled fred-agents model
catalog. The Helm chart adds `chat.mistral.medium`; its default chat profile
remains `default.chat.openai.prod`.

### Prerequisites

To select Mistral Medium in a deployed agent pod, provide a Mistral API key as
`applications.fred-agents.dotenv.OPENAI_API_KEY`. The bundled GPT and Mistral profiles do not override `api_key`, so they
share `OPENAI_API_KEY` within a pod. A pod configured with a Mistral key cannot
also call the bundled GPT profiles; use a separate agent pod if both providers
are needed.

### Configuration

The bundled local and Helm profiles declare `supports_thinking: true` and send
`reasoning_effort: high` when the platform admin enables reasoning for this
model. Both set `top_p: 1.0` because the shared `temperature: 0.0` setting uses
greedy sampling. Keep Mistral Medium unselected on pods with an OpenAI key.

### Upgrade

Deploy the updated chart normally. To activate Medium, configure the Mistral
credential on its agent pod, select the `chat.mistral.medium` profile for the
intended agent or team, and enable reasoning for the model in platform admin.
Existing selection and reasoning settings do not change automatically.

### Validation

Confirm the rendered `models_catalog.yaml` contains the Medium profile with
`supports_thinking: true`, `reasoning_effort: high`, and `top_p: 1.0`. Complete
a short chat turn with reasoning enabled and confirm no model API error occurs.

### Rollback

Select the previous model and disable Medium reasoning in platform admin, or
restore the prior chart/catalog. No data migration is involved.

### Limitations

The bundled GPT and Mistral profiles share `OPENAI_API_KEY`, so they cannot
use different credentials in one pod without custom credential handling.
Deployments overriding the bundled model catalog must add this profile to
their own values to receive the fix.

## Replace the legacy Graph executor with native LangGraph execution

Impact: **major** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.0.0/docs/swift/ops/migrations/native-graph-runtime.md)

### Applicability

Deployments and external agent pods upgrading to the native Graph runtime.
Graph, ReAct and Deep now share capability tool authorization, observability
and approval handling. This change does not enable token delegation.

The four Python libraries (`fred-pod`, `fred-core`, `fred-sdk`, `fred-runtime`)
are prepared for coordinated publication as 4.4.0, with aligned internal
dependency minimums. This package version does not remove the incompatible
SDK and checkpoint changes below. Publish in the documented order: pod,
core, SDK, then runtime.

### Prerequisites

Review external SDK consumers before upgrading:

- `GraphWorkflow.parallel` and `GraphDefinition.parallel_groups` are removed.
  The legacy implementation supported concurrent branches. Adapt affected
  agents before upgrading; a sequential rewrite requires a review of its
  behavior and performance and is not an equivalent automatic migration.
- `ThoughtRecord` and `GraphExecutionOutput.thought_trace` are removed.
  Consumers needing authored thought events must use the existing streamed events.
- Graph approval clients must use `interrupt_id` and, when supplied,
  `occurrence_id`, instead of `checkpoint_id`. Old request/history keys may
  still parse, but this does not make old Graph pauses resumable.
- Custom session IDs must not contain `:`; the runtime rejects them with 422.

### Configuration

No production configuration activation is required. The bundled test mock
model is optional and intended only for Test Assistant checks. Local settings
are not a production model or observability recommendation.

### Upgrade

1. Stop admitting new Graph runs and finish or explicitly abandon pending
   Graph approvals on the old deployment. Record any business work to restart.
2. Back up runtime checkpoint and session-history storage using the deployment's
   normal backup procedure. Do not delete old checkpoints as part of this upgrade.
3. Upgrade the SDK, runtime, agent pods, frontend and custom approval clients
   together. Avoid mixed runtime versions serving the same Graph session.
4. Start fresh Graph sessions. Legacy Graph checkpoints use a different layout
   and are not migrated: old paused runs cannot resume, and their business state
   is not automatically restored on a new turn. Reconstruct required business
   state explicitly and check previous side effects before rerunning work.

PostgreSQL checkpoint initialization also installs two session lookup indexes on
existing tables. Their equality lookup covers both ReAct/Deep session threads
and every `session:agent` Graph thread, including dynamic children, under
non-C collations and generic prepared plans. SQLite keeps its existing lookup.

For large live checkpoint tables, prebuild these indexes **before rollout** to
avoid the write-blocking build during the first checkpoint request. Run each
statement outside a transaction; adjust `v2_` if using a custom table prefix:

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS v2_langgraph_checkpoint_session_idx
    ON v2_langgraph_checkpoint (split_part(thread_id, ':', 1));
CREATE INDEX CONCURRENTLY IF NOT EXISTS v2_langgraph_checkpoint_write_session_idx
    ON v2_langgraph_checkpoint_write (split_part(thread_id, ':', 1));
```

Confirm both indexes are valid before upgrading; a failed concurrent build can
leave an invalid index that must be dropped and rebuilt. Otherwise, allow the
runtime to create them during a maintenance window. Existing indexes and data
are retained; rollback can leave these additional indexes in place.

### Validation

Verify pod template discovery and external agent imports. In a new Graph session,
exercise a capability approval, reload while paused, accept and confirm one tool
execution and a terminal response. In a separate session, reject and confirm
zero execution. Check ReAct and Deep approval/refusal behavior as well.

### Rollback

Stop new runs before reverting pods and clients together. The old Graph runtime
cannot consume the new native checkpoints. Restore a consistent pre-upgrade
backup only through the normal recovery procedure; this can discard intervening
history. Neither rollback nor checkpoint restoration reverses external tool
effects. Reconcile those effects before restarting business work.

### Limitations

No automatic legacy Graph checkpoint conversion is provided. Native parallel
authoring, per-node retry/timeout configuration, automatic node progress and
model-native reasoning visibility remain outside this change. Node error routes
use the Fred wrapper because the native LangGraph 1.2.12 error handler does not
recover correctly with the required custom stream mode.

The upgrade procedure is an operational requirement, not evidence that legacy
checkpoints can be resumed. Existing ReAct/Deep source aggregation may attach
retrieved documents to an abstention; relevance filtering is a separate follow-up.

## Replace configured info banners with admin-managed announcements

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.0.0/docs/swift/ops/migrations/platform-announcements.md)

### Applicability

All deployments require the new control-plane database migration. Deployments
using the old info banner also need to recreate their message. Existing documents
do not need re-ingestion.

### Prerequisites

Back up the control-plane database and retain the previous banner configuration.
A platform administrator with can_manage_platform is needed to create announcements.

### Configuration

Remove platform.frontend.info_banner from control-plane configuration and the
corresponding applications.control-plane-backend.configuration.platform.frontend.info_banner
Helm overlay. Keep upload_warning unchanged. No replacement configuration key
is required: announcements are managed at /admin/annonces.

### Upgrade

1. Apply control-plane migrations through b88202b8451e before starting the updated
   backend and frontend. Use your existing database migration procedure; the Helm
   migration hook is disabled by default.
2. Deploy the matching Fred backend and frontend. The new announcement table is
   initially empty; old banners are not imported automatically. Newly created
   announcements are disabled by default.
3. If a banner is needed, recreate its localized text and links in /admin/annonces,
   choose its severity and dismissal behavior, then enable it.

### Validation

Confirm the database migration succeeded and the admin page loads. Enable an
announcement and check that a signed-in user sees it after refreshing the page.
Check its translations, links and dismissal behavior before leaving it enabled.

### Rollback

Restore the previous Fred version and its saved info_banner configuration.
Announcements created in the new UI are not converted back. Back up their content
before any database downgrade: downgrading this revision drops the announcement
table and its data.

### Limitations

Announcements appear only in the authenticated application, not on login,
terms-acceptance or bootstrap screens. The old custom color and automatic hiding
options have no direct equivalent; severity controls color and users can dismiss
announcements when allowed. An existing open session refreshes announcements
every 60 seconds or on window focus.

## Clarify runtime cleanup and resolve Python quality findings

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.0.0/docs/swift/ops/migrations/python-codeql-quality-findings.md)

Runtime APIs, persisted data, permissions, and deployment order are unchanged; normal deployment is sufficient.

See the source note for applicability, validation and rollback.

## Tracked ingestion relaunch with duplicate protection

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.0.0/docs/swift/ops/migrations/relaunch-ingestion.md)

### Applicability

Knowledge Flow deployments using document ingestion, including source synchronization.

### Prerequisites

Pause new uploads, source synchronization and processing requests. Let existing
Temporal ingestion workflows finish, including their queued and retrying children.
Allow task reconciliation to complete. Investigate remaining active tasks or
workflows; do not mark running work failed just to unblock the upgrade.

### Configuration

No configuration changes. Keep the common and fast/medium/rich workers configured
as before.

### Upgrade

After draining ingestion, stop the old Knowledge Flow API and workers, run the
normal Knowledge Flow Alembic migration, then start the new API and workers and
resume submissions. Avoid mixing old and new ingestion submitters during rollout.
The migration rejects duplicate active tasks for one document; resolve their real
workflow outcomes before retrying it.

No bulk re-ingestion is required. When a user relaunches an older document whose
profile was never recorded, the UI asks them to choose a profile.

### Validation

Relaunch a failed document. Check that one task appears in Resources/Activity,
survives a page reload and reaches a terminal state. A second concurrent request
must not start another ingestion. Confirm that rich/medium documents still use
their respective extraction workers.

### Rollback

Pause submissions again and drain both pending deliveries and running ingestions
before reverting Knowledge Flow. Do not drop the pending-submission table while
it contains accepted work. The added index/table may remain when rolling back
application code; an Alembic downgrade is only safe after the drain.

### Limitations

An unavailable worker or a Temporal retry is still active work, not permission to
relaunch. Historical tasks without a known workflow need investigation, not an
automatic timeout-based failure. The profile cannot be reconstructed for old
documents. Memory scheduling remains a single-process local-development mode.

## Required migration declarations and release guides

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.0.0/docs/swift/ops/migrations/release-migration-policy.md)

### Applicability

This change affects Fred contributors and release operators. Applications do not
need new runtime configuration. New release publications require a validated
migration guide and sufficient paired code/chart version numbers.

### Prerequisites

Release tooling needs Python 3.12, uv and full Git history and tags. It reuses
fred-pod's pyproject.toml and committed uv.lock for its existing PyYAML dependency. Repository administration is needed to activate the required
PR status after this workflow lands. Existing private customer repositories stay
under DevOps ownership.

### Configuration

No application values change. After merge and a successful run, add `Migration
notes` to the effective required GitHub checks without replacing existing checks
or changing bypass policy. See the migration workflow guide for rollout verification.

### Upgrade

1. Merge the validated tooling PR and verify its PR check is available on the base.
2. Activate the required status in GitHub and verify it is enforced.
3. Before the first release, audit the changes between the previous stable code
   tag and the policy activation boundary. Add a note with the exact legacy_range
   metadata; do not assume older unclassified changes need no operations.
4. Prepare a release note, generate the guide, review combined ordering and rollback,
   and approve a version meeting the maximum operational impact before tagging.

### Validation

Run the offline migration helper tests and the `check-pr` command. Dry-run `plan`
against the intended release baseline. An incomplete legacy audit must block
release generation, and a missing or stale guide must block publication.

### Rollback

Use a reviewed tooling change to revert enforcement if necessary, preserving
published guides and source notes. Do not silently disable checks to publish a
release. No runtime or customer database rollback is required for this tooling.

### Limitations

Structural checks cannot judge the correctness of migration instructions. Reviewers
must verify the classification, combined operations and rollback. GitHub protection
activation is a separate post-merge step and is not complete merely because this
workflow exists. No release or production migration is executed by this change.

## Release v3.0.0 preparation and pre-policy contribution audit

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.0.0/docs/swift/ops/migrations/release-v3.0.0-preparation.md)

The release documents themselves need no deployment action; the audited contributions below add no operator step beyond their own notes.

See the source note for applicability, validation and rollback.

## Fix categorical values and numeric bounds in tabular descriptions

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.0.0/docs/swift/ops/migrations/tabular-description-call-time-values.md)

Existing CSV and Excel Parquet artifacts can be read by the description tool; no re-ingestion, metadata migration, client update, or special deployment order is needed.

See the source note for applicability, validation and rollback.

## Combined tabular descriptions and richer column metadata

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.0.0/docs/swift/ops/migrations/tabular-document-description.md)

### Applicability

Deployments using Excel or CSV documents through the tabular tools.

### Prerequisites

Keep the original files available if re-ingestion is needed.

### Configuration

No configuration changes are required for the bundled Fred integration.

### Upgrade

Deploy Fred normally. Category values and numeric bounds are computed when
the description is requested, so existing files gain them without re-ingestion.
Re-ingest an existing Excel file only to type its native boolean columns as
booleans; this is applied during ingestion, without automatic backfill.

### Validation

After ingestion completes, describe and query a document through an agent.
Check that its tables and column types are returned correctly.

### Rollback

Redeploy the previous Fred release. This does not undo regenerated document
artifacts.

### Limitations

Custom integrations using get_tabular_documents_schemas or
get_tabular_document_markdown must switch to describe_tabular_documents.
The /tabular/documents/{document_uid}/markdown endpoint is removed.
Excel descriptions require a successfully generated preview.
