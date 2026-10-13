# Migration guide — v3.4.0

Upgrade from: `code/v3.3.0`
Operational impact: **minor** (minimum version: `3.4.0`).

Review these procedures together in the listed dependency order before deployment. Customer-specific values remain in their private repositories; Fred chart values are the production reference. Configuration files named configuration_prod.yaml are for local development only.

No-operation declarations describe ordinary deployment only. Conditional activation steps still require preparation. Validate combined upgrade and rollback in staging before production.

## Staged v3.4.0 upgrade and rollback

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.4.0/docs/swift/ops/migrations/000-v3-4-0-release-preparation.md)

### Applicability

Upgrade from Fred v3.3.0 to v3.4.0 using the paired code and chart release.
This release-preparation contribution consolidates the operational changes below;
its minor impact comes from those existing procedures, not an additional migration.
Use this sequence once, then use the following feature sections for configuration,
validation and limitations. Their database revisions are applied together, not as
separate deployments. Python package publication is a separate maintainer workflow.

### Prerequisites

Back up the shared PostgreSQL database and retain the previous chart, values,
images and OpenFGA model identifier. Plan database migrations through the normal
deployment procedure; large installations may need a database migration window
for the agent-name backfill and unique index. Admission readers must use the same
PostgreSQL authority. Filtering will be activated later, after all readers are
updated, so no synchronized backend cutover is needed for that activation.
Prepare a verified administrator account and a recovery path before activation.
Review the agent-name collision query below before migration: duplicate names
will be renamed, and schema rollback does not restore their former names.

### Configuration

Reconcile private overlays against the new Fred chart values, including worker
values separately from API values. `configuration_prod.yaml` is for local Compose.
Prepare JSON log parsers for APIs, workers and frontend; review access and retention
for diagnostic identity references and native nginx text errors. Remove obsolete
admission or web-egress settings only if an earlier draft introduced them.

If using a custom `FRED_PLATFORM_PROMPT_FILE`, merge the shipped skill-use and
precedence guidance before restarting agents. Rename saved prompt commands named
`skill` if their slash shortcut must remain available. Neither step enables skills.

### Upgrade

#### Required staged deployment

1. Publish and select the compatible OpenFGA model containing
   `organization.suspended` before starting any updated reader, including on
   deployments without delegation. This can be prepared ahead of the application
   rollout. Keep ordinary authentication and resource authorization enabled.
2. Run the release's database migrations through the normal deployment process
   before starting updated applications. Chart migration hooks default to disabled:
   explicitly enable the deployment's migration jobs or run the equivalent documented migration command
   for each backend; API startup alone does not migrate the database. For the
   runtime, the command is `python -m fred_runtime migrate`. The control-plane
   chain from `aac66348e27b` is
   `f9a2c7d81e40` -> `a4d85307ea0e` -> `c82f6a91d043` -> `cb6f39c6d80c` ->
   `93427a5fe874`. It adds admission state, unique agent names, conversation name
   snapshots, patch-note history and creation-assistant settings. The runtime
   advances from `d4e5c6b7a8f9` to `e5f6a7b8c9d0` for web-research activity.
   Run the normal Knowledge Flow migration check as part of the release as well.
3. Roll out the updated control-plane API and verify it initialized the shared
   admission authority. Filtering remains disabled and saved policy survives
   restarts. Start updated runtime and Knowledge Flow readers only after the
   authority is available; this dependency does not require simultaneous rollout.
4. Roll out the Control Plane worker and all Knowledge Flow workers, including
   common and extraction workers, before the updated API submits new ingestion
   arguments. New workers accept old queued payloads, so the old API may continue
   submitting during worker rollout. Check the entire worker cohort before step 5.
5. Roll out the matching Knowledge Flow API, agent pods and frontend. The chart
   does not order Deployments across services: use staged upgrades to enforce the
   authority and worker dependencies. Verify all replicas use the expected
   settings and resources, then run the checks below.
6. Update saved logging queries for the fields documented below. Run the real
   collector/proxy and Temporal canaries; local checks do not establish production
   log parsing or multi-worker rollout compatibility.

#### Optional activation after the ordinary upgrade

- Platform admission filtering: activate it later, after the updated readers
  are in place. At that time, configure and test rules, import existing users if
  desired, review live user/team exceptions and the activation preview, then
  enable deliberately. Link access is separately managed by platform admins.
- Web research: configure the provider secret and approved direct/proxy egress,
  retention and quotas, then enable the team and agent capability. Run the built-in
  deployment checks. It remains disabled without activation.
- Shared skills: select packaged or trusted read-only resources, distribute the
  same files to every replica, drain turns and restart agent pods. Graph agents
  do not support these skills. Existing checkpoints retain already loaded text.
- Autoscaling: prepare metrics, resource requests and shared agent object storage
  before enabling any HPA. Reconcile existing HPA ownership first.
- Creation assistant: optionally select an allowed model, instructions and reasoning
  in platform administration. Defaults require no extra model configuration.

#### Conditional data operations

No document re-ingestion is required. Only deployments that already recorded skill
usage before installing its index mappings need the targeted skill-event reindex
shown in the skills section; a normal upgrade from v3.3.0 does not. Earlier draft
admission databases require the schema reconciliation described below, not a blind
stamp. Separately rebuilt external Knowledge Base pods must follow their own SDK
configuration and code compatibility note; publishing this Fred release does not
rebuild or publish those pods or Python packages.

### Validation

After the staged rollout, verify migration heads, initialized admission authority,
matching OpenFGA model selection and worker versions. Test sign-in, an ordinary
chat, an upload through extraction and output, and an ingestion retry. Check API,
worker and frontend log parsing and correlation through the real deployment.
Then validate renamed agents, read-only deleted-agent history, patch notes and
agent creation. Exercise each optionally enabled feature using its checks below.
Validate platform admission with direct and delegated requests and across replicas.

### Rollback

Pause new ingestion submissions. While updated workers are still available,
drain all tasks carrying new diagnostic envelopes. Disable optional admission
filtering deliberately before rollback, and disable web research and its capability.
For retained web-research activity, erase it first or keep the updated runtime
available for purge/erasure until expiry. Disabling admission widens access;
ordinary authentication and resource authorization must remain enforced.

Restore the previous API submission code before rolling back workers, keeping
new ingestion submissions paused throughout. Restore the matching application/chart
versions, prior logging parsers and fixed replica counts as appropriate. Prefer leaving additive
SQL tables/columns in place. The per-feature downgrade targets below are references,
not a sequence to execute: Alembic also downgrades every later revision, deleting
saved settings, patch notes, dismissals, activation history and admission state.
If a schema downgrade is necessary, stop all affected readers/writers and review
the complete chain against the database backup first. Agent renames persist after
downgrade. Restore the recorded prior OpenFGA model selection only with the old
readers; verify access before resuming normal operations.

### Limitations

This guide does not certify private overlays, identity providers, proxy destination
controls, GKE log collectors, live Temporal rollout or production load. Validate the
combined sequence in staging. Deleted agents without recoverable runtime snapshots
still lack readable history. Optional research retains restricted activity subject
to the documented expiry/erasure policy; skills retain loaded checkpoint context.

## Expose contact support in the Help Center

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.4.0/docs/swift/ops/migrations/3018-help-contact-support.md)

Only frontend rendering changes; existing configured support destinations appear after normal deployment, with no data or API changes.

See the source note for applicability, validation and rollback.

## Accept single and double brace PPT Filler markers

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.4.0/docs/swift/ops/migrations/3020-ppt-filler-brace-variants.md)

Valid double-brace templates, stored schemas, and tool inputs remain compatible; normal deployment enables single-brace authoring without data migration.

See the source note for applicability, validation and rollback.

## Refresh the agent question and tool approval cards

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.4.0/docs/swift/ops/migrations/3034-hitl-card-visual-refresh.md)

The runtime contract, answer semantics and stored history are unchanged; existing conversations render with the new cards after a normal deployment.

See the source note for applicability, validation and rollback.

## Make agents use the question tool and accept open questions

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.4.0/docs/swift/ops/migrations/3035-harden-ask-user-tool.md)

The human-input contract and stored history are unchanged; agents receive the new tool description on their next turn after a normal deployment.

See the source note for applicability, validation and rollback.

## Recall sent messages in the chat composer with the arrow keys

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.4.0/docs/swift/ops/migrations/3038-composer-message-recall.md)

The recall list is built from the conversation already loaded in the page; no API, stored data or runtime change.

See the source note for applicability, validation and rollback.

## Archive five completed OpenSpec changes

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.4.0/docs/swift/ops/migrations/archive-merged-openspec-2026-10-11.md)

The archived changes describe behaviour that is already deployed; moving them into the capability specs changes no runtime behaviour.

See the source note for applicability, validation and rollback.

## Keep the Python images' dependency layers cached across local and library changes

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.4.0/docs/swift/ops/migrations/docker-dependency-layer-cache.md)

The images install the same packages from the same locks, at the same paths, and start the same way; only the layer order and what enters the build context change.

See the source note for applicability, validation and rollback.

## Expose document metadata and filesystem tool details

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.4.0/docs/swift/ops/migrations/document-tree-metadata-details.md)

Normal deployment updates the renderer, capability and frontend. Existing metadata is reused, historical results remain readable, and no database or API schema migration is needed.

See the source note for applicability, validation and rollback.

## Renew the browser token before document uploads and recover one HTTP 401

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.4.0/docs/swift/ops/migrations/document-upload-token-refresh.md)

The frontend reuses its existing token renewal service. No API, permission, stored data or deployment order changes are required.

See the source note for applicability, validation and rollback.

## Build the production frontend without compiling test files

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.4.0/docs/swift/ops/migrations/frontend-prod-tsc-excludes-tests.md)

The shipped frontend bundle and runtime behavior are unchanged; only test files are excluded from the production type-check.

See the source note for applicability, validation and rollback.

## Show and configure the capabilities included with graph agents; enforce library binding on knowledge.search

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.4.0/docs/swift/ops/migrations/graph-agent-included-capabilities.md)

No data is migrated: existing agent instances keep running their included capabilities as before, and gain a stored configuration only when someone edits and saves them.

See the source note for applicability, validation and rollback.

## Knowledge Base pods name themselves and expose operational metrics

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.4.0/docs/swift/ops/migrations/knowledge-base-pod-metrics.md)

Fred deployments are unaffected. A Knowledge Base image is affected only once rebuilt against fred-sdk 4.4.3, and its own deployment then sets app.runtime_id.

See the source note for applicability, validation and rollback.

## Keep the requested page and session when an in-app page opens in a new tab

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.4.0/docs/swift/ops/migrations/oidc-new-tab-session.md)

The identity-provider client, its redirect URIs and stored data are unchanged; the fix takes effect with a normal frontend deployment.

See the source note for applicability, validation and rollback.

## Search every selected document on pgvector deployments

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.4.0/docs/swift/ops/migrations/pgvector-multi-value-metadata-filter.md)

Stored vectors and metadata are unchanged; multi-document filters now reach SQL as an IN clause as soon as Knowledge Flow is redeployed.

See the source note for applicability, validation and rollback.

## Prepare the coordinated FRED Python library 4.5.0 release

Impact: **none** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.4.0/docs/swift/ops/migrations/python-library-4-5-0-release-preparation.md)

This preparation builds and validates artifacts but does not publish packages or change a running deployment.

See the source note for applicability, validation and rollback.

## Activate configurable platform admission and live user/team exceptions

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.4.0/docs/swift/ops/migrations/2965-platform-access-planning.md)

### Applicability

Applies to authenticated deployments with enforced ReBAC and either the Keycloak or local user directory. Administration is available after migration; filtering starts inactive. Admission policy is separate from resource authorization.

### Prerequisites

The configurable identity-provider/local-directory support is included in this standalone change. Admission readers require authenticated users and workloads, a Keycloak or local user directory, enforced OpenFGA with a finite timeout, and the same shared PostgreSQL database in every participating backend. Publish and select an OpenFGA model carrying `organization.suspended` on every reader before rollout, including Keycloak deployments without delegation. Migrate control plane before starting readers. Standalone SQLite admission is unsupported.

### Configuration

There is no admission-specific deployment configuration. Remove `security.platform_access`, `global.platformAccess` and `FRED_PLATFORM_ACCESS` from earlier draft deployments; they no longer initialize, enable or override admission. Keep the existing `security.user_directory` choice and a finite `security.rebac.timeout_millisec` (the default is 5000). Configure support through the existing frontend `properties.contactSupportLink` and remove earlier draft `supportLink` fields. Keep actual identity values and support destinations outside public examples.

First-party backends using the shared ReBAC SDK must pass their shared PostgreSQL engine to `rebac_sdk_factory(platform_engine=...)`. They are readers and cannot initialize the authority. A legacy file whitelist can continue while SQL filtering is inactive; remove it before activating the new filter. Activation refuses concurrent gates, and readers fail closed if a conflicting legacy gate appears while filtering is active.

### Upgrade

1. Back up the shared database and apply control-plane Alembic head. This PR adds one revision, `f9a2c7d81e40`, following `aac66348e27b`. It adds selected internal identity evidence, versioned policy settings, individual exceptions and team enrollment state with independent links and aggregate authenticated opening counters. This revision is still part of this unreleased PR. If an isolated development database already applied an earlier draft of `f9a2c7d81e40`, recreate that disposable database from migrations; do not stamp it to conceal schema drift. Preserve a backup and use an explicit data-preserving migration for any database that must retain its data.
2. Deploy control plane first; it initializes the SQL authority once with filtering inactive. Deploy runtime and Knowledge Flow with the same shared database. An absent authority starts with no policy, revision zero and filtering inactive; restarts preserve saved settings. Missing or incompatible authority fails closed with 503.
Filtering is scheduled for later activation, after the updated readers are in place. Steps 3-6 below can be performed then; they are not required to complete the v3.4.0 upgrade.

3. In **Platform access**, use **Choose an account field** to select a root text attribute from your verified current session. Protocol metadata, arrays and nested paths are hidden by default; **Show advanced fields** restores the complete picker. Select nested or literal dotted keys through the advanced explorer; there is no manual path input. Current-value copying is explicit. Add up to 16 conditions, choose AND/OR and literal contains/not-contains/equals/not-equals or advanced whole-value regex. Literal comparison ignores case by default; the case toggle is explicit. Test against your own verified token, then save. Missing, empty or incompatible claims fail predicates too. Choose allow mode to admit matches or block mode to admit nonmatches; existing policies default to allow. Independent exceptions and authorized/Free memberships remain sufficient in either mode. Regex timeouts never derive admission. Upgrade all readers to the matching policy model before saving a policy with the mode field; older readers reject that field even when its value is allow. No observed-claims catalog is collected or exposed; the picker loads only the connected administrator's own token projection.
4. In **Platform access > Whitelist > Users**, explicitly **Import existing users**. Unknown existing classifications receive removable exceptions. This import completes once; retries never restore removed entries or include subsequent registrations.
5. Add independent user/team exceptions as needed, then enable filtering. Select any number of existing Fred users across searches/pages for an atomic manual grant. Whitelist this team derives access from current team membership instead of copying users into permanent exceptions; removing a member withdraws that source on their next direct or delegated request. Activation requires a saved rule or an individual/team exception. Use the filtering action at the top right of the page header to review the Allowed and Blocked lists before confirming. Unevaluable accounts appear separately under Verification unavailable; this is a preview-data limitation, not a third access state. Update rereads the current database snapshot, reference policy and import status without changing admission state; stale rows and confirmation remain unavailable until the refreshed review succeeds. If the initial import has not completed, choose Continue without importing to activate deliberately or Go to whitelist to open the import view without activating. An unavailable import status prevents UI activation confirmation until retry succeeds; disabling remains available. The preview uses the saved configuration, not unsaved edits, and checks the revision at confirmation. Unavailable evaluations require fresh evidence or an independent source; a missing field in an available verified token is evaluated normally; the dry run does not guarantee access or change policy. The acting administrator must retain a valid source; activation, active rule saves and access-policy self-lockout are refused. A stale save returns 409 and preserves the newer policy and the administrator's draft. If recovery is necessary, explicitly disable the persisted SQL filtering switch, then repair the saved rule or independent sources in the UI. An operator can recover a locked-out administrator with `UPDATE platform_access_settings SET filtering_enabled = false WHERE id = 1;`; this deliberately widens admission.
6. In platform administration **Teams**, enable **Link access** (the Free flag) on a non-personal team and use **Manage links** to generate its opaque link. Free/link controls are available only to platform administrators; independent user and team authorization remain in **Platform access > Whitelist**. Preserve team visibility/joining policy. Handle the link as a capability; share it only with intended participants. Generate multiple independent invitations with optional notes and expiration; previous invitations remain valid until revoked, expired or suspended. Removing Free suspends links and withdraws the team-derived access source; restoring Free resumes unrevoked, unexpired links. Revoke individual links in history to prevent future enrollment. Existing membership and independent sources remain. A valid link permits deliberate re-enrollment after member removal, so revoke it if re-enrollment must be prevented. History counts authenticated opening signals, not anonymous clicks, unique people or message delivery; repeated submitted signals count again. Administrators can reveal the original URL. Recoverable capability tokens are stored in SQL: protect the database and backups accordingly. Ordinary history excludes tokens; creation/reveal require own-human platform-management credentials and disable HTTP caching.

Manage links now opens history first, with a short Accesses counter and Copy URL, without last-access timestamps. Copy uses the shared chat action icon with temporary check feedback, keeping the modal layout stable. A separate Create link form places note above the KPI-style expiration popover, with one future date, Apply, 24-hour/7-day/30-day shortcuts and No expiration. Creation success shows a usable URL and Copy URL; clipboard failure retains manual copying without generating another invitation. These UI refinements require no additional operator action.

History can be filtered by lifecycle status. The confirmed cleanup action permanently removes all expired or revoked invitations for the selected team, including their notes and access counters, independently of the visible filter/page. Valid suspended links and team memberships remain. No additional migration or configuration is needed; restoring deleted history requires a database backup.

Platform access administration groups controls into Rules and Whitelist. Whitelist has Users and Teams sub-tabs: Users contains existing-user import and individual exceptions; a completed import becomes a discreet status line; Teams contains independent team authorization. Free enrollment and links live in platform administration Teams. The top-right header action enables/disables filtering across both tabs with explicit population-review confirmation; there is no Activation tab. Navigation preserves local drafts and selections. This presentation refinement requires no additional deployment setting, migration or operator action.

The own-claims picker requires the matching control-plane and generated frontend client. It adds no migration or deployment setting; the endpoint is administrator-only, uncached and does not persist its bounded payload. Admission errors reuse the shared Fred error presentation.

### Validation

Check a matching person, an imported person, a newly denied person and a valid Free enrollment. The denied, Free and profile screens must use the same `contactSupportLink` before protected bootstrap. Check direct and delegated calls, suspension, required CGU acceptance, and revocation with the same JWT through a different replica. Confirm missing/incompatible authority produces `platform_access_unavailable` (503), rather than the definitive denial (403).

### Rollback

Disable persisted filtering through the administrator UI to suspend policy enforcement while retaining exceptions and team state. If the UI is unavailable, explicitly disable the SQL filtering switch as above. Keep ordinary authentication, suspension and resource authorization enforced. This widens admission and is an explicit operator choice. Do not downgrade the additive migration while a participating backend is running. A schema downgrade removes admission state and selected attribute observations; restore the database backup to recover them.

### Limitations

Verified selected evidence used for delegated people expires with its human access token. A newly selected claim without a stored observation also requires a fresh direct human request; a predicate-only edit can reuse compatible unexpired evidence. Cached direct JWTs retain bounded internal facts and evaluate the current saved rule on every request. An independent live source remains sufficient. Admission revocation affects subsequent requests, not already authorized work. All participants must share the PostgreSQL policy authority; independent databases are unsupported. Mask `/platform-access/free/<token>` and `/join-free/<token>` in ingress/proxy logs as Fred does in its own access logs. Four-replica production load and private IdP/Helm overlays require operator validation.

## Enable internal web research with direct or proxy access

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.4.0/docs/swift/ops/migrations/2980-native-web-research.md)

### Applicability

Native `web_search` and `fetch_url` for ReAct, Deep and Graph.
The engine runs inside Fred Agents. No additional Fred process, MCP server,
listening port, local TLS certificate or egress service token is required.

### Prerequisites

Fred's usual local infrastructure and a configured model must be available.
Allow public DNS/HTTP(S) for direct mode; for proxy mode configure the operator's
proxy and final destination policy before activation.

### Configuration

#### Local activation

In the Fred Agents YAML selected by `config/.env`'s `CONFIG_FILE`, add at root:

```yaml
web_research:
  enabled: true
```

Start the usual local infrastructure and run Fred normally (`make run` from the
repository root). Its database-upgrade prerequisite applies the runtime migration,
including the restricted activity table. Its process must have
working DNS and public HTTP(S) access. Enable Web research for the team and select
it on the agent through the existing capability controls. Ask the agent to search
for a public topic and to read `https://www.python.org/`.

#### Production configuration

Helm fields live under `applications.fred-agents.configuration.web_research`:

```yaml
web_research:
  enabled: true
  provider: brave
  provider_key_env: WEB_RESEARCH_PROVIDER_KEY # Brave Search API key secret
  proxy_url: https://proxy.dmz.example:3128
  proxy_auth_env: WEB_RESEARCH_PROXY_AUTH # Optional Basic username:password secret
  proxy_ca_file: /run/secrets/proxy-ca.crt # Optional private HTTPS proxy CA
  cost_per_1000_searches: 5 # Contract price for the admin cost estimate
  max_results: 5 # Results sent to the model per search
  max_chars_per_page: 6000 # Text sent to the model per read page
  activity_retention_days: 30
  max_searches_per_user_per_day: 50 # Optional daily cap per user (UTC day); omit for no quota
  max_fetches_per_user_per_day: 200 # Optional daily cap on page reads per user
```

`provider` selects the search engine: `duckduckgo` (SDK default, keyless, no
SLA, local use), `fixture` (offline results from `fixture_file` or built-in
samples, for development and CI) or `brave` (Brave Search API key read from the
variable named by `provider_key_env`). The chart defaults to `brave`, so enabling
it without the key fails Fred Agents startup. Providers never fall back to one
another; an outage returns `provider_failed`. The key reaches only the provider
endpoint, never logs, activity or model arguments.

Set the secrets under `applications.fred-agents.dotenv`, which the chart
renders into the `fred-agents-env` Kubernetes Secret like the other Fred Agents
credentials (proxy entry only when `proxy_auth_env` is set):

```yaml
dotenv:
  WEB_RESEARCH_PROVIDER_KEY: "<Brave Search API key>"
  WEB_RESEARCH_PROXY_AUTH: "<username:password>"
```

Without `proxy_url`, research uses direct public access. With it, every provider,
page and redirect uses the configured HTTP(S) forward proxy; failures never fall
back to direct access. `HTTP_PROXY`, `HTTPS_PROXY` and `NO_PROXY` environment
variables do not select or bypass this route. Proxy secrets belong in the existing
Fred secret/environment mechanism, not URLs or model arguments. For an HTTP proxy,
omit `proxy_ca_file`; Basic credentials require a suitably protected network,
preferably an HTTPS proxy. Public origin TLS is always verified independently.
TLS interception and client certificates are not configured by this feature.

The operator owns the proxy deployment, firewall, DNS and monitoring. In proxy
mode, permit the Fred host only proxy connectivity for research egress. The proxy
MUST reject private/non-global and metadata destinations at connection time,
including mixed IPv4/IPv6 records, DNS rebinding and redirects. Fred resolves no
names in this mode, so the Fred host needs no external DNS: it refuses locally
non-public IP literals, numeric hosts and local names (single-label,
`localhost`, `.local`, `.internal`, `.svc`) and forwards other names to the
proxy, which therefore carries name-based SSRF protection. A 403 answer to an
HTTPS tunnel is reported as `proxy_refused` (counted as blocked); a 407 or 5xx
answer stays `unavailable`. A refused `http://` page appears as `http_error`. Test these controls on the actual DMZ.
No Fred-specific API or service executable belongs on the proxy host.

### Limitations

Default off; retention 30 days (1–365), purge every 60 seconds, four concurrent
operations and a 60-second operation deadline including queue/admission and
outbound I/O. Saturation returns `busy`; each activity write has its own 5-second
storage deadline. Defaults also bound pages to 5 MiB and ports 80/443. To limit
model context, at most `max_results` (default 5) results and `max_chars_per_page`
(default 6,000) characters per read page reach the model, whatever the tool
arguments request. For longer pages the model passes `focus` to get the relevant
passages, or reads without `focus` and continues with `offset` from the previous
`next_offset` (the two are mutually exclusive); each
continuation re-downloads the page and adds tokens, but is not billed by the provider. Optional per-user caps, `max_searches_per_user_per_day` and
`max_fetches_per_user_per_day` (unset by default: no quota), count the user's
requests per UTC calendar day from the activity table; any dispatched request
counts, whatever its outcome. Over a cap the tool returns `quota_exceeded`
before any network access, and each capped result shows the remaining count in
the trace detail. Erasing a user's activity also resets their quota for the day.
Configure these, `max_bytes`, `retries` and the `safesearch`
floor at deployment level. Direct access pins vetted public DNS addresses to connections.
In every mode, internal names (single-label such as `keycloak`, `localhost`,
`.local`, `.internal`, `.svc`) and numeric hosts are refused as
`unsafe_destination` before any DNS lookup.
All modes check redirects, refuse binary/compressed responses and isolate cookies.
Extraction/focus runs in bounded worker threads.

Before production enablement, approve raw-query storage and the chosen search
provider under deployment policy; DuckDuckGo HTML has no availability SLA and is
not intended for production load.
The restricted SQL sink must exist and SQL statement logging must be disabled.
Reads require `CAN_MANAGE_PLATFORM`. Account deletion keeps the activity until
expiry; to honour a right-to-erasure request, a user administrator
(`CAN_ADMINISTER_USERS`) calls
`DELETE /agents/web-research/activity/users/<opaque-id>` on Fred Agents, which
returns the number of deleted records.

### Validation

Platform admins see a "Web research" section on the Analytics page: tool calls
split into searches (billed) and page reads (not billed), estimated provider cost, blocked/saturated/failed requests by reason, p95 latency
and distinct users. Set `cost_per_1000_searches` to your provider contract price
(default 0) for the estimate; it counts successful searches only and excludes
retries, free tiers and LLM tokens. The section reads a content-free
`web_research.request` KPI event, so it requires the OpenSearch KPI store and
counts from the deployment of this version; restarts do not reset it.

In **Administration → Self-test**, run **Web research checks**: a deterministic
agent (no LLM) probes the deployment through the real port — refused URLs,
internal, metadata and encoded destinations, redirects, binary content,
SafeSearch floor, then a working search and page read — and reports each check.
It fails first when `web_research.enabled` is off. Probes needing an unreachable
third-party endpoint (httpbin.org, nip.io, example.com) are skipped, not passed;
in proxy mode they also show whether the proxy enforces the destination policy.
Each probe leaves a record in the restricted activity log.

Use Fred's existing Prometheus exporter and runtime dashboard: operation counts,
latency, failure/busy outcomes and activity-sink failures. Load the rules in
[deploy/web-research/alerts.yaml](https://github.com/ThalesGroup/fred/blob/code/v3.4.0/deploy/web-research/alerts.yaml).
Each failed request also logs one content-free line, for example
`event=web_research outcome=failed operation=fetch_url error_code=proxy_refused cause=ProxyError status=403 duration_ms=212 request_id=…`
(info for expected refusals, warning for outages and unexpected errors); the
`request_id` leads to the restricted activity row holding the target.
No extra `/health` or `/metrics` research server is exposed, and no periodic
public Internet probe runs; provider/proxy outages appear on attempted operations.

Using an authorized operator credential, inspect
`GET /agents/web-research/activity?user_id=<opaque-id>` after successful and failed
research. Check attribution/outcome, expiry and explicit erasure; no page bodies,
snippets, secrets or URL query/fragment are retained. Refuse private/metadata URLs
and redirects in both modes. Verify unavailable proxy returns a bounded failure
and there are no direct connections. Verify wrong HTTPS proxy trust is rejected.

### Upgrade

When upgrading from v3.3.0, apply runtime migration `e5f6a7b8c9d0`
(parent `d4e5c6b7a8f9`) through the deployment's enabled migration job or
`python -m fred_runtime migrate` before enabling research. API startup validates
the schema; it does not apply this migration. Chart migration hooks default off.

Only earlier draft adopters must remove `egress_url`, `token_env`, `ca_file`,
`client_certificate`, `client_key` and `WEB_RESEARCH_EGRESS_TOKEN`. Old YAML fields
fail validation. Stop the draft Fred egress process and retire its
Compose/Kubernetes deployment; use direct access or an operator-owned forward
proxy instead. Draft deployments already at the activity revision need no further
SQL migration for that egress replacement.

### Rollback

Disable `enabled` and deselect the capability before rollback. Keep the current
runtime available for purge/erasure until records expire, or erase them first.
Expiry is immediate for reads and physical deletion occurs on the next sweep.
Conversation-history retention remains governed by its existing separate policy.

## Optional Helm-managed Horizontal Pod Autoscalers

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.4.0/docs/swift/ops/migrations/2997-configurable-horizontal-pod-autoscalers.md)

### Applicability

Fred installations using the Helm chart, including deployments whose HPA resources
are currently managed manually. Autoscaling is disabled by default for every
application; ordinary upgrades require no activation steps.

### Prerequisites

For optional activation, the cluster must support `autoscaling/v2` and expose a
working Kubernetes resource metrics API. Set container resource requests for each
resource used by a utilization metric: CPU for the supplied examples, memory if
selecting a memory policy. Ensure cluster capacity supports the chosen limits.

When `fred-agents` can scale above one replica, its
`configuration.storage.object_store` must already use shared storage (`gcs` or
`minio`) with the required credentials and access to existing objects. The chart
rejects local object storage with an enabled HPA's `maxReplicas > 1`.

### Configuration

In the deployment's Helm values overlay, configure
`applications.<name>.autoscaling.enabled`, `minReplicas`, `maxReplicas`, `metrics`
and optional `behavior`. Set `applications.<name>.resources.requests` for the
selected metrics and ensure the target application and its Deployment are enabled.
The supplied policies are starting examples; review them for the actual workload.
See [the chart guidance](https://github.com/ThalesGroup/fred/blob/code/v3.4.0/deploy/charts/README.md#horizontal-pod-autoscaling).

### Upgrade

Deploy normally with autoscaling disabled to retain chart-managed replica counts.

For optional activation, prepare the prerequisites and render the chart with the
deployment's values before upgrading. If an HPA already targets the Deployment,
record its policy and arrange its replacement or Helm ownership transfer before
activation; avoid competing autoscalers and resource ownership conflicts. Enable
autoscaling in the overlay and upgrade the release. The chart then omits the
Deployment's `spec.replicas`, allowing the HPA to manage the replica count.

### Validation

With autoscaling disabled, confirm the rendered chart contains no HPA resources.
After activation, confirm the rendered HPA targets the intended Deployment with
the chosen limits and metrics, and that the Deployment omits `spec.replicas`.
In the cluster, use `kubectl describe hpa <application-name> -n <namespace>` to
check available metrics and scaling conditions; exercise representative load and
confirm replicas stay within the configured bounds.

### Rollback

Disable the application's autoscaling and set its intended fixed `replicaCount`
in the overlay before upgrading, or roll back to the previous Helm release.
Verify the Helm-managed HPA is removed and the fixed replica count is restored.
Restore any previous manually managed HPA if it was replaced during activation.
This feature introduces no data migration; retain any shared storage configured
for `fred-agents` and its existing objects.

### Limitations

Only chart-managed Deployments support these HPAs, with CPU or memory resource
utilization metrics. Missing resource requests or unavailable metrics prevent
effective scaling. The example limits and behavior are not workload sizing
guarantees; enabling a previously disabled worker is a separate deployment choice.

## Enable shared platform skills for managed ReAct and Deep agents

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.4.0/docs/swift/ops/migrations/platform-agent-skills.md)

### Applicability

Fred deployments upgrading the runtime, control plane and frontend together.
Without skills configuration, agents no longer receive the former automatically
injected Mermaid syntax rules. Mermaid rendering remains available in chat.
The `/skill` composer command is reserved on every deployment.

### Prerequisites

Use matching runtime/SDK/control-plane/frontend versions. For a project directory,
provide UTF-8 SKILL.md procedures with name/description YAML metadata and bounded
text references. Every replica must receive the same resources.

### Configuration

Optional activation: set `applications.fred-agents.configuration.skills.directory: package`
in chart values to use the English-written quality/reliability skills shipped
inside fred-runtime: `meeting-minutes` (meeting minutes), `grounded-research`,
`summarize-document`, `compare-options`, `verify-answer` and `mermaid` (diagrams). Responses follow
the requested language.
For custom skills, mount a trusted directory read-only and use its absolute pod
path. Relative paths resolve against the configuration file parent. Omit skills
(or leave chart `skills: null`) to disable. No IAM grants or secrets are added.
Application development configuration examples explicitly enable `package`.
For a custom directory, include a `mermaid/SKILL.md` if its diagram guidance is
needed; the removed SDK resource is no longer an automatic fallback.

### Upgrade

The shipped platform instructions now explain slash selection and permit applying
catalog-loaded skill procedures under the existing platform hierarchy. If a
deployment overrides `FRED_PLATFORM_PROMPT_FILE`, merge the matching skill-use
and precedence guidance from `apps/fred-agents/config/platform_prompt.json` into
its copy. Restart all agent replicas after updating this file. Arbitrary tool
results and documents remain data; skills grant no tools or permissions.
The runtime also exposes the selected skill names in the existing per-turn
system context. Deploy the runtime update for this reminder; it does not load
instructions, duplicate the catalog or force a native tool call.

Deploy the control plane, runtime and frontend with the normal procedure. Older
runtime catalog routes are shown as unsupported during a rolling upgrade.
To activate or change resources, drain active turns and restart all relevant
agent pod replicas. Avoid mixed snapshots: use identical config/resources on
all replicas before resuming traffic. Invalid entries are omitted with diagnostic
folder names. Existing checkpoints retain loaded procedure messages; the advertised
catalog and new loads use the current snapshot on their next turn, without
resetting conversations. Native Deep discovery metadata keeps its upstream per-thread cache. Deep reads
the physical configured folder through FilesystemBackend and native `skills=`;
web metadata, previews and ReAct explicit preload still use the startup snapshot.
Native file edits may become visible before restart. Keep all replicas on the
same read-only files and restart after deployment to refresh the web catalog.

Existing prompts using command `skill` remain library-readable and editable but
lose that slash shortcut. Rename the command to restore it; new assignments,
imports and promotions with `skill` return a reserved-command conflict.

The packaged meeting-minutes skill is named `meeting-minutes`, with its template
at `references/meeting-minutes-template.md`. Replace earlier `/compte-rendu`
invocations and hard-coded native paths with `/meeting-minutes` and
`/skills/meeting-minutes/`. Stored messages and historical usage retain their
original names. Native Deep threads may retain the earlier discovery index;
start a new conversation to discover the renamed directory.

### ReAct personal and team prompt commands (2026-10-09)

The frontend additionally offers commanded personal prompts alongside the chat
team's commands and platform skills for ReAct templates. It uses the existing
runtime-derived template category and authorized prompt routes; no operator
configuration or schema migration is required. Personal chats list one prompt
library; Deep and other execution families keep their current prompt sources.
Verify the three source labels in a ReAct team chat and select each of two
homonymous personal/team commands: the exact selected prompt text must run.
Without an explicit row, a typed prompt command prefers the chat team's match.
Prompt/skill homonyms remain independently selectable; `/skill` stays reserved.
Prompts share the platform skills' two-line menu layout, with a distinct icon
in a blue tile. Completed prompt commands use an inline blue icon/name;
hover reveals their title, source and description. Verify completion,
copying `/command`, editing and undo preserve the selected prompt's identity.

### Multiple selections and inline prompts

Deploy the regenerated runtime API client with the runtime/SDK update, then
restart the agent pods. New turns use name-only `runtime_context.skills`; legacy
singular input/history stays supported, while supplying both forms is rejected.
No SQL migration or new skill middleware is required. ReAct loads all selected
skills before inference; Deep retains native progressive loading.

Verify two different skills, repeated skill names, independent deletion and copy,
one personal or team prompt with both skills, and text before/after each token.
Reopen history and resume the same interrupted exchange; all selections must
remain. A fresh turn must not inherit them. Invalid ReAct selections fail the
whole request. Available prompt commands complete inline before or after skills
in every managed execution family; only ReAct adds a separate personal library
to team chats. Check keyboard and click completion in both themes, and verify
the blue prompt icon/name in both the draft and reopened history.

### Validation

Select a managed ReAct or Deep instance. Verify its `/skill` menu lists only its
runtime catalog and displays advisory `argument-hint` values when supplied.
Typing `/` also lists the skills directly; a prefix such as `/comp` filters their
names. Selecting one attaches it without sending or replacing existing notes.
There is no standalone `/skill` menu row; the typed command remains compatible.
Skills have a dedicated platform pictogram and an origin hint. Hover the selected
or sent name to see its current catalog description when available.
Send `/skill meeting-minutes` alone and verify the agent uses existing meeting
notes or asks for them. Hints never block submission. Then send the command plus notes containing a decision and
an action without a deadline: ReAct preloads the selected instructions and emits
a user-origin load step before inference. Deep receives the native catalog and
user request; only an actual successful instruction read emits a load step.
Check that absent fields remain unspecified in the requested language, and
record any model-following limitation rather than equating selection with loading. On an ordinary relevant request the
model can load the same skill automatically. Check that the
loaded context identifies the skill as procedural instructions, not a function,
and its hint as user-input guidance rather than tool parameters. Verify the agent
reads references through `read_skill_file` (ReAct) or `read_file` on the mounted
`/skills/<name>/` paths (Deep), rather than inventing a skill-named tool.
Deep mounts the physical configured folder at `/skills/`, preserving its
physical subdirectories. Use well-formed skills with matching folder/frontmatter
names; native discovery and file types are governed by DeepAgents. Deep no longer registers Fred
`load_skill` or `read_skill_file`; ReAct retains both. Explicit ReAct selections
still preload internally before inference. Deep selections stay ordinary user
text: native discovery and model-driven `read_file` calls load the instructions,
without Fred preload or snapshot body validation. Deep selection alone emits no
load event/KPI. Actual native instruction reads use user origin for the current
any explicitly selected name and agent origin for other skills, including child
reads. This records who requested the skill; read_file is still model-driven. Name-only
selection metadata preserves the badge and preview in reopened Deep history
without implying that the skill was loaded. Existing preloaded messages in old
conversation checkpoints are not removed; use a new conversation to inspect the
native path after restarting the runtime. The mount supports listing
and searching. Parent/child permissions and capability ports deny writes, including
at `/skills`; the deployed folder must be read-only on disk. The production image
protects its packaged runtime source tree with root ownership and read-only modes;
external skill mounts must provide equivalent read-only access. Native discovery
warnings omit file contents, including malformed YAML source text. The upstream backend
is used directly and script execution stays unavailable. Deep native reads see
current disk files; restart remains required to refresh web and ReAct snapshots.
Native reads of `SKILL.md` from offset zero count actual skill use, with user
origin for the current selected name and agent origin otherwise;
reference/pagination reads do not. Click a native reference trace row to inspect
its returned excerpt in the shared panel.
Reopen the chat and check the
compact origin step and the inline skill name in the user message remain.
The composer shows the full selected name inline with the request, without a
removal button; editing an invocation character removes its recognition without
deleting surrounding text. Removing only request text preserves an intact selected
skill, including when a prompt has the same name. Verify unknown ReAct selection fails before inference
and unavailable tools are explained without fabricated results.
Click the inline name in the composer and a stored user message: the right-hand
panel shows metadata and formatted instructions, leaving the request unchanged
and making no model call. Clicking the same skill again closes the panel. The
empty request uses the skill’s optional argument hint as a placeholder. Runtime
version details remain internal; reopened messages preview current instructions. Deploy matching
runtime, control-plane and frontend versions for the detail route; an older runtime
shows an unavailable preview while ordinary chat remains usable.

### Skill usage analytics (2026-10-07)

Deploy matching runtime, control-plane and frontend versions and restart serving
processes. The existing additive KPI index repair installs `skill_name` and
`skill_origin` keyword dimensions on startup; no SQL migration is needed.
Counts begin with instrumentation deployment; old conversations are not backfilled.
If skill events were already recorded before the mapping upgrade, their fields
can exist in `_source` while remaining unsearchable (`dynamic: false`). After
startup mapping repair, reindex only those existing events in place using
`POST <configured-kpi-index>/_update_by_query?refresh=true` with the body:

```json
{ "query": { "term": { "metric.name": "agent.skill_loaded_total" } } }
```

This preserves recorded names, origins, owners and timestamps, without reading
conversation history or creating additional load events. Verify the response
has no failures/version conflicts and that scoped skill totals match recorded
loads. This one-time operation is unnecessary if instrumentation and mappings
were deployed together.
Verify user-selected and model-selected successful loads in the selected team/date
range, in platform analytics and in the personal usage subsection. Personal
counts use the authenticated conversation owner across all teams. Each space
shows one matching skill subsection: personal, selected team or platform. Team
space must not also show the personal skill subsection. The
user/model columns identify who selected the skill. Reopening history, reference reads and HITL resume
must not increase counts. Actual reloads count again. Existing queue/storage loss
behavior makes these operational analytics best-effort.

Click a successful reference row: the same right panel must show the stored file,
retain its width, and close on a second activation without changing the draft.

### Rollback

Disable `skills`, then drain/restart the pods to remove the catalog and loading
tools. Use normal application rollback for a full revert; no database migration
is introduced. Disabling does not erase already-loaded checkpoint context or
stored history. Start a fresh conversation if older instructions must be excluded.

### Limitations

V1 supports a few dozen shared procedures and confined text references. Web/ReAct resources
refresh at restart while Deep native reads use current disk contents; skills do not install tools, execute scripts, or grant
permissions. Selection/following by the model is probabilistic. Graph agents and
a dedicated terminal CLI are outside this feature.

## Select structured JSON output for Fred APIs

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.4.0/docs/swift/ops/migrations/structured-logging-output.md)

### Applicability

Control Plane, Knowledge Flow and hosted Fred agent APIs. The following procedures in this guide cover request, delegated-call and worker correlation in the same release.

### Prerequisites

Use the matching code and chart release. Custom stdout parsers must accept the new JSON fields.

### Configuration

Set `app.log_format: json` in API configuration to emit one JSON object per stdout line. The chart reference selects JSON. Omitted values and local examples select `text`; selection is independent of the optional generic log store. Existing log-store DTOs remain compatible.

### Upgrade

Reconcile production overlays with the chart values and restart the APIs. Adapt stdout queries to `severity`, `message`, `timestamp`, `logger`, `service` and `service_role`. The timestamp contains event-creation epoch seconds and nanoseconds. The audit stream retains its existing isolated JSON representation.

Shared configuration startup events retain the selected file paths as structured `env_file` and `config_file` fields, rather than embedding them in the message. Environment-file contents are not logged.

Dependency warnings/errors retain their logger, severity and safe scoped context,
but use a fixed diagnostic message without upstream text, extras or tracebacks in
every delegation mode. They remain console-only to avoid recursive store emission.
Uvicorn warnings/errors and exception records likewise omit unrestricted server
text and tracebacks in every mode; request-correlated application diagnostics
provide the local support references.

### Validation

Emit an ordinary event and confirm that stdout has a complete single-line JSON object with normalized severity, event time, source and structured properties. Verify severity/timestamp promotion and field filtering in a GKE canary before declaring collector compatibility. Check readable local output without width-dependent wrapping.

### Rollback

Set `app.log_format: text` and restart if a parser needs the prior readable workflow, or roll back the paired code/chart. No data migration is introduced.

### Limitations

No GKE deployment or canary was performed during offline verification. Native processes outside Python do not use this formatter. Configuration-load statuses are buffered until the selected formatter is available; invalid/unavailable configuration can still produce bootstrap failure output before a valid logging setting exists. Request context, trusted downstream propagation and worker handoff are covered by the following procedures in this release. Dependency warning/error events are console-only to avoid recursive store emission.

## Make agent names unique within each team

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.4.0/docs/swift/ops/migrations/3042-unique-agent-names-per-team.md)

### Applicability

All Fred deployments. Only teams or personal spaces holding two or more agents
whose names differ at most by case or surrounding spaces are affected.

### Prerequisites

No additional prerequisites beyond the normal deployment procedure.

To know beforehand which agents will be renamed, run this read-only query on
the control-plane database:

```sql
SELECT team_id, lower(trim(display_name)) AS name, count(*) AS agents
FROM agent_instance
GROUP BY team_id, lower(trim(display_name))
HAVING count(*) > 1;
```

### Configuration

No configuration changes are required.

### Upgrade

Deploy Fred normally. The control-plane database migration of the deployment
(revision `a4d85307ea0e`) trims every agent name, keeps the name of the oldest
agent of each colliding group and renames the others `<name> (2)`,
`<name> (3)`… in creation order, then adds the unique index. No agent is
deleted.

### Validation

The query above returns no row. In a team, creating an agent with the name of
an existing one (in another case) is refused under the name field.

### Rollback

Use the normal rollback procedure. Downgrading the control-plane migration
drops the index; renamed agents keep their new names.

### Limitations

Renamed agents keep their new names; users rename them if they prefer another
one. Names are compared with ASCII and Unicode case folding by PostgreSQL.

## Use request and operation references in API diagnostics

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.4.0/docs/swift/ops/migrations/structured-logging-context.md)

### Applicability

The three Fred APIs, interactive agent execution/tools, conversation creation and attachments, and upload admission.

### Prerequisites

Deploy the shared output foundation first. Custom collectors should accept the new completion fields.

### Configuration

No new configuration. Keep the selected `app.log_format`; update collector queries and log access as described below.

### Upgrade

Deploy after the shared output foundation. Update access-log queries to the `http` logger's single completion event (`http_method`, safe `route`, `http_status` when sent, `outcome`, `duration_ms`). Uvicorn access and the earlier Knowledge Flow request/response lines are suppressed. Successful probes are omitted; failures remain visible.

The message summarizes `POST /sessions/{session_id}/runs → 403 | 8ms` instead of
`HTTP request completed`. Interrupted processing appends its outcome (for example,
`200 | 8ms | disconnected`); absent route/status displays `<unmatched>`/`no response`.
Filter access events by `logger=http` and structured fields rather than the old
message text. No Grafana dashboard change is required to display the summary.

Use fresh `X-Request-ID` and `X-Correlation-ID` response headers to find a request. Generic diagnostic logs can now include admitted opaque person and resolved business references; review deployment log access and retention accordingly. Metric labels and audit restrictions remain as documented in observability §6/§7.

Request logging and configured CORS surround FastAPI's unhandled-error response
boundary, so generic 500 responses retain the references and a completion with
their actual status. Session references bind only after ownership validation or
successful creation. Batch upload completions retain batch/workflow context;
per-document references remain scoped to each file's diagnostics.

### Validation

Check normal, failing and streaming requests, a chat resume, a tool invocation, and an upload. Completion must follow stream termination, cancellation must not invent status, and unrelated requests must keep separate context. The focused offline isolation check includes actual thread work and retained tasks. Collector/deployment verification remains a rollout step.

### Rollback

Roll back this layer to restore previous access logging. No database migration or new configuration is required. Downstream and worker propagation require subsequent layers.

### Limitations

No deployment or collector canary was performed. The following procedures cover cross-service propagation and persisted ingestion context, both included in this release.

## Read structured frontend access logs

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.4.0/docs/swift/ops/migrations/structured-logging-frontend.md)

### Applicability

Production nginx frontend container. Vite and browser JavaScript logging are outside this change.

### Prerequisites

Keep the existing nginx image/runtime and pod stdout/stderr collection. Review native-text retention and access policies before deployment.

### Configuration

No new variable or Helm setting is required. Access events use escaped JSON stdout with bounded route families; native errors/startup and entrypoint messages retain text on their existing streams.

### Upgrade

Deploy the updated frontend image. Update saved access-log queries/parsers to use `http_status`, `http_route`, `duration_s` and `severity`. The local nginx `request_id` is separate from API response references.

### Validation

Run the existing rendered-config smoke and container smoke with the updated image. Check 2xx/4xx/5xx JSON, event time, per-request IDs and omission of adversarial paths, queries, credentials, cookies and bodies. In GKE, separately verify severity/timestamp promotion and field filtering, then examine a native startup/upstream failure. A local container check does not establish managed-collector parsing.

### Rollback

Restore the previous frontend image and its access-log parser. No data migration or application configuration rollback is needed.

### Limitations

Native nginx errors can include raw request lines/queries and upstream/file details; entrypoint theme/configuration messages remain text. These are not sanitized by the JSON access format. Native collector parsing and GKE severity/timestamp promotion remain unverified rollout checks. No browser telemetry or extra JSON conversion container is added.

## Read-only conversations after managed agent deletion

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.4.0/docs/swift/ops/migrations/2992-deleted-agent-conversations.md)

### Applicability

Saved conversations keep their history and become read-only after agent deletion,
with a preserved agent name, a localized deletion suffix and visibly disabled chat composer.

### Prerequisites

Existing browser ingress routes to the runtime history endpoint must remain
available. Back up the Control Plane database before upgrading.

### Configuration

No local or production configuration changes.

### Upgrade

Run the normal Control Plane Alembic upgrade before deploying the updated backend
and frontend together. Revision `c82f6a91d043`, following `a4d85307ea0e`, adds nullable
`session_metadata.agent_display_name` and backfills names for agents still present
in the same team. The migration updates conversation metadata in place and leaves
activity timestamps unchanged. Its backfill runs once over existing sessions;
plan the usual database migration window for large installations.

The updated backend captures names at session creation and refreshes them to the
latest name in the same transaction as agent deletion. The frontend consumes the
additive name field and `SessionDetails.agent_deleted` / `messages_url`.

### Validation

Open a conversation, rename its agent, delete the agent, then reload the list and
conversation. Verify the latest name remains visible with the localized deletion suffix in both,
history is readable, and the disabled composer explains read-only mode. Hover or
focus the sidebar entry to read the deletion explanation. Confirm another live
agent conversation still accepts messages.

### Rollback

Roll back the application images together; the nullable column may remain in place.
If a schema downgrade is required, stop updated application readers/writers first
and follow the coordinated release rollback before considering
`a4d85307ea0e`. This revision itself drops only display-name snapshots; sessions
and runtime history remain. Downgrading from a later head also removes every
subsequent revision, including announcement data and creation-assistant settings. The previous deleted-agent
history limitation would return with older application images.

### Limitations

Names of agents already deleted before this migration cannot be reconstructed;
those conversations use a localized generic name with the same read-only state.
Legacy sessions without a runtime snapshot can use a still-existing instance.
After its deletion, routing cannot be recovered reliably and the UI explicitly
shows history as unavailable. No runtime is guessed.

## Correlate admitted delegated calls across Fred services

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.4.0/docs/swift/ops/migrations/structured-logging-propagation.md)

### Applicability

Delegated first-party runtime REST/MCP calls and Fred receivers accepting delegated grants.

### Prerequisites

Deploy the output and local-context layers first. Existing workload provisioning and delegated authentication must already be valid.

### Configuration

No new setting. Retain existing `security.delegation` activation. Proxies must permit the bounded `X-Fred-Log-Context` header where delegated calls pass; its schema and exact bounds are in observability §6.1.

### Upgrade

Upgrade sender and receiver in either order. An older receiver ignores metadata; an older sender simply supplies none. Updated delegated transports stop following redirects to keep context and authority at their configured destination.

### Validation

Follow a delegated request by correlation ID across runtime, tool mount and inner route. Request IDs must differ per receiver; admitted principal/grant identity must win. Invalid metadata must leave valid business responses unchanged. Check an ordinary bearer call and disabled delegation for absence of inherited fields. Focused offline tests cover real request building, MCP HTTP traffic, shared-client isolation and redirect confinement.

### Rollback

Roll back this layer on either side. The other side continues valid authentication and business calls without shared diagnostic context. No data migration is required.

### Limitations

Context is diagnostic metadata, never authority. Legacy bearer forwarding, external/no-token tools and token endpoints do not propagate it. Unsupported MCP transports remain unsupported. GKE/proxy and collector validation was not performed; run the severity/timestamp/field-filtering canary during rollout.

## Patch-note announcements and announcement activation history

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.4.0/docs/swift/ops/migrations/add-patch-note-announcements.md)

### Applicability

All Fred deployments upgrading the control-plane backend and frontend.

### Prerequisites

No additional prerequisites beyond the normal deployment procedure.

### Configuration

No configuration changes are required.

### Upgrade

Deploy the control-plane backend and the frontend together. The control-plane
Alembic revision `cb6f39c6d80c` (parent `c82f6a91d043`) runs with the normal
migration step:

- it adds the column `platform_announcement.kind`, with server default
  `'banner'`, so every existing announcement becomes a banner and renders as
  before;
- it adds a partial unique index allowing at most one enabled patch note;
- it creates `platform_announcement_dismissal` (per-user "Don't show again"
  choices, cleared whenever an admin enables the patch note again) and
  `platform_announcement_activation_event` (activation history).

No backfill or manual step is needed.

### Validation

As a platform admin, open **Administration → Announcements**, create a patch
note, preview it with **Preview as users see it**, then enable it: it appears
in the **History** view under your name. Reload the application as another
user: the patch-note dialog opens. Tick **Don't show again** and close it; it
does not open at the next load, and the profile menu's **What's new** entry
still reopens it. Existing banners still show as before.

### Rollback

Follow the coordinated release rollback first. With traffic paused and updated
readers stopped, a downgrade to `c82f6a91d043` also removes all later revisions,
including creation-assistant settings, before the previous images restart. The downgrade deletes every
patch note, then drops the new columns, the index, the dismissals and the
activation history.

### Limitations

- Announcements, dismissals and the activation history are not part of the
  platform export/import.
- A patch note enabled while a user has the application open is shown to that
  user at their next load, not immediately.
- The activation history page shows the 100 most recent events; older events
  stay in the database.

## Use scoped diagnostic context in ingestion workers

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.4.0/docs/swift/ops/migrations/structured-logging-workers.md)

### Applicability

Knowledge Flow and Control Plane worker entrypoints, durable ingestion submissions and metadata/extraction/output activities, including spawned extraction children.

### Prerequisites

Prepare the shared logging configuration and collectors first. Follow the coordinated release sequence: upgrade workers before API submissions, even though the API logging contracts are described earlier in this guide. Keep existing shared-storage, scheduler authorization and Temporal namespace/queue configuration. No database schema change is required.

### Configuration

Reference deployed worker configurations already select `app.log_format: json`; omitted local settings select text. Knowledge Flow worker/child generic logs remain stdout-only. Ensure the collector accepts role `worker`, bounded context fields and activity attempt metadata.

### Upgrade

Upgrade common and extraction workers before the API begins submitting new envelopes. New workers accept old queued payloads; old workers do not accept the new optional extraction arguments. Keep the worker cohort consistent before activating updated submission code. Workflow payloads only forward optional plain data; absent envelopes retain their original extraction activity arguments and replay behavior.

### Validation

Run one upload through durable delivery, metadata, extraction and output. Confirm correlation/person/team/document/task/workflow references; attempt must change on retry while operation identity remains. Inspect both worker and spawned child logs. Focused offline checks cover committed-outbox recovery, ambiguous delivery retries, legacy payloads, actual thread work and real spawned-child JSON/KPI output. No Temporal/GKE deployment canary was performed.

### Rollback

Stop updated submissions and drain jobs carrying envelopes before rolling workers back. Restore the earlier API submission code, then workers. Old payloads remain executable; logs lose inherited journey context. No data migration is needed.

### Limitations

This diagnostic envelope is not authorization and does not extend HTTP grants. Legacy jobs lack originating-request context; local activity references remain available. Temporal workflow logs retain their replay-aware logger and do not bind generic context inside replay. Collector severity/timestamp/field filtering and live multi-worker rollout must be validated during deployment.

## Creation assistant: draft an agent from a plain-language description

Impact: **minor** · [Source](https://github.com/ThalesGroup/fred/blob/code/v3.4.0/docs/swift/ops/migrations/add-agent-creation-assistant.md)

### Applicability

Existing Fred deployments upgrading to this release.

### Prerequisites

No additional prerequisites beyond the normal deployment procedure.

### Configuration

No configuration changes are required. The assistant's explicit model choices
now include only models enabled by the platform `default_on` switch and served
by every enabled pod. Team-only grants do not qualify. An existing saved choice
is kept when its model is disabled; it remains displayed but cannot be selected
again. The built-in meta-prompt now uses American English; admins with overrides
can inspect the revised default before deciding whether to adopt it.

Each draft calls one chat model once:
the profile a platform admin picks in **Platform prompts > Creation
assistant**, else the pod's default chat profile. Its reasoning follows
the admin **Reasoning** setting (Off by default): for a profile declaring
`supports_thinking`, any level but Off keeps the profile's own
`reasoning_effort` (else its single listed level; with neither, the admin page
shows reasoning as unavailable for it), unless the profile lists selectable
levels in the new optional `reasoning_efforts` field, which then picks the
nearest listed level for the assistant's call only. No action is needed: no shipped profile
declares levels, so every thinking profile keeps an on/off switch. To offer
levels, list only those the provider accepts (for example
`reasoning_efforts: [low, medium, high]` on a GPT-5.1 profile with
`supports_thinking: true`; Mistral accepts only `high`). A pod refuses to start
if the field is set without `supports_thinking`, is empty, or leaves out the
profile's own `reasoning_effort`. Agent chat ignores the field. When reasoning is on and the call fails fast or is still running
after 23 seconds, the same call without reasoning starts beside it and the first usable draft wins. Drafts do not appear in `llm.call_latency_ms`, which stays limited
to agent model calls.

Token usage: each draft emits a new KPI event,
`agent.creation_assistant_completed`, with the calling user, the team and
`input_tokens`/`output_tokens`. The existing token-usage presets and the
analytics views built on them (per user and per team; over time, by model and
by agent) now count these events too, so token totals rise by the drafts'
usage after the upgrade; message, conversation and activity counts do not.
Dashboards or exports that read `agent.turn_completed` directly are
unchanged.

Pods read the admin settings from the control plane at
`platform.control_plane_url` (already set for managed agents) with the
caller's token. A pod without it drafts with its own defaults.

### Upgrade

The control plane adds one Alembic migration (`93427a5fe874`), which creates
the empty `creation_assistant_settings` table. It holds the optional admin
settings of the assistant (instructions override, model, reasoning effort
defaulting to `off`); no existing data changes.

1. Apply the control-plane database migrations as for any release that ships
   one (`alembic upgrade head`, run by the usual migration job or start-up).
2. Deploy the control plane and agent pods normally. Until a pod is upgraded,
   only the creation assistant answers 501 for its agents, and the admin
   **Creation assistant** tab reports that the default text is unavailable.
   Until the control plane is upgraded, upgraded pods draft with their own
   defaults.

### Validation

As a team editor, call
`POST /control-plane/v1/teams/{team_id}/agent-templates/{template_id}/draft-agent`
with a short `description`: the answer contains a non-empty `system_prompt`
and short `name`, `role` and `description`.
In the UI, the agent form header shows **Assistant** once a template
is chosen; applying a draft fills the ticked fields.
As a platform admin, `GET /control-plane/v1/admin/platform/creation-assistant`
returns `is_default: true`, the pod's built-in text and the selectable
`model_options`, and the admin **Platform prompts** page shows a
**Creation assistant** tab.

### Rollback

Use the normal rollback procedure. The migration's downgrade drops
`creation_assistant_settings`, losing only the saved settings; leaving the
table in place is harmless for the previous release.

### Limitations

A draft, settings read included, must finish within 50 seconds on the pod.
With reasoning on, Mistral Medium took 22 to 47 seconds per draft in testing,
against 7 to 10 seconds without; turn reasoning off if drafts are too slow. Ingresses with a read
timeout below 60 seconds may cut slow drafts short. A model chosen by an admin
that a pod no longer serves falls back to that pod's default chat profile.
