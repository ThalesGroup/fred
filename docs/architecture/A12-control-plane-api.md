# Control Plane REST inventory

One row per registered operation, grouped by URL prefix, to review naming and API
consistency. Routes are generated from the same OpenAPI contract as the frontend
client. Authentication does not grant content access: see the [SSI matrices](A7-action-role-matrix.md).

Full request/response types and status codes remain in OpenAPI. Generate the contract
with `make -C apps/control-plane generate-openapi` (`apps/control-plane/openapi.json`);
the [generated TypeScript client](../../apps/frontend/src/slices/controlPlane/controlPlaneOpenApi.ts)
provides a versioned view. Regenerate this inventory with `make -C docs/architecture generate-models`.

<!-- generated: openapi-index apps/control-plane/openapi.json -->
Paths are relative to `/control-plane/v1`.

Operations: [`/admin`](#admin-routes) · [`/agents`](#agents-routes) · [`/analytics`](#analytics-routes) · [`/authorize`](#authorize-routes) · [`/bootstrap`](#bootstrap-routes) · [`/capability-preparations`](#capability-preparations-routes) · [`/deletions`](#deletions-routes) · [`/document-processing`](#document-processing-routes) · [`/document-uploads`](#document-uploads-routes) · [`/documents`](#documents-routes) · [`/folders`](#folders-routes) · [`/frontend`](#frontend-routes) · [`/gcu`](#gcu-routes) · [`/healthz`](#healthz-routes) · [`/import-export`](#import-export-routes) · [`/me`](#me-routes) · [`/organizations`](#organizations-routes) · [`/powerpoint-uploads`](#powerpoint-uploads-routes) · [`/skills`](#skills-routes) · [`/spaces`](#spaces-routes) · [`/users`](#users-routes).

## /admin routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| GET | `/admin/organizations` | `organization_registry` | Required |
| POST | `/admin/organizations` | `create_organization` | Required |
| GET | `/admin/organizations/candidates` | `search_organization_candidates` | Required |
| GET | `/admin/organizations/{id}` | `get_organization` | Required |
| PATCH | `/admin/organizations/{id}` | `update_organization` | Required |
| GET | `/admin/teams` | `team_registry` | Required |

## /agents routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| POST | `/agents/execute/stream` | `execute_stream` | Required |
| GET | `/agents/sessions/{session_id}/messages` | `messages` | Required |

## /analytics routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| POST | `/analytics/query` | `query_analytics` | Required |

## /authorize routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| POST | `/authorize/document` | `authorize_document` | Required |
| POST | `/authorize/platform` | `authorize_platform` | Required |
| POST | `/authorize/scope` | `authorize_scope` | Required |
| POST | `/authorize/space` | `authorize_space` | Required |

## /bootstrap routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| POST | `/bootstrap/platform-admin` | `bootstrap_platform_admin` | Required |

## /capability-preparations routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| GET | `/capability-preparations/cleanup` | `capability_preparation_cleanup` | Required |
| GET | `/capability-preparations/worker` | `capability_preparation_worker` | Required |
| GET | `/capability-preparations/{id}` | `capability_preparation_context` | Required |
| POST | `/capability-preparations/{id}/cleaned` | `capability_preparation_cleaned` | Required |
| POST | `/capability-preparations/{id}/confirm` | `capability_preparation_confirm` | Required |
| GET | `/capability-preparations/{id}/content` | `capability_preparation_content` | Required |

## /deletions routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| GET | `/deletions/{operation_id}` | `deletion_status` | Required |

## /document-processing routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| GET | `/document-processing/cleanup` | `cleanup` | Required |
| POST | `/document-processing/cleanup` | `cleaned` | Required |
| GET | `/document-processing/retrievable/{id}` | `retrieval_work` | Required |
| POST | `/document-processing/retrievable/{id}` | `confirm_retrievable` | Required |
| POST | `/document-processing/{id}/abandon` | `abandon` | Required |
| POST | `/document-processing/{id}/claim` | `claim` | Required |
| POST | `/document-processing/{id}/commit` | `commit` | Required |
| GET | `/document-processing/{id}/original` | `original` | Required |
| POST | `/document-processing/{id}/vectors` | `vectors` | Required |
| GET | `/document-processing/{id}/work` | `work` | Required |
| POST | `/document-processing/{id}/writes` | `writes` | Required |

## /document-uploads routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| GET | `/document-uploads/{id}` | `receipt` | Required |
| PUT | `/document-uploads/{id}/acknowledgment` | `acknowledge` | Required |

## /documents routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| DELETE | `/documents/{id}` | `delete_document` | Required |
| GET | `/documents/{id}/content` | `content` | Required |
| GET | `/documents/{id}/preview` | `preview` | Required |
| GET | `/documents/{id}/processing` | `history` | Required |
| POST | `/documents/{id}/processing` | `start` | Required |
| PUT | `/documents/{id}/retrievable` | `set_retrievable` | Required |

## /folders routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| POST | `/folders` | `create_folder` | Required |
| PATCH | `/folders/{id}` | `rename_folder` | Required |
| DELETE | `/folders/{id}` | `delete_folder` | Required |
| POST | `/folders/{id}/documents` | `upload` | Required |
| POST | `/folders/{id}/documents/preflight` | `preflight` | Required |

## /frontend routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| GET | `/frontend/config` | `frontend_config` | Public |

## /gcu routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| POST | `/gcu` | `accept_terms` | Required |

## /healthz routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| GET | `/healthz` | `health` | Public |

## /import-export routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| POST | `/import-export/import` | `import_blueprint` | Required |

## /me routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| GET | `/me` | `me` | Required |
| GET | `/me/marketplace-proposal-spaces` | `marketplace_proposal_spaces` | Required |
| GET | `/me/marketplaces` | `marketplaces` | Required |
| GET | `/me/onboarding` | `onboarding_status` | Required |
| POST | `/me/personal-space` | `create_personal_space` | Required |
| GET | `/me/spaces` | `my_spaces` | Required |

## /organizations routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| GET | `/organizations/{organization_id}/agents` | `organization_agents` | Required |
| PUT | `/organizations/{organization_id}/agents/{agent_id}/default-on` | `set_organization_agent_default` | Required |
| GET | `/organizations/{organization_id}/capabilities` | `organization_capabilities` | Required |
| POST | `/organizations/{organization_id}/capabilities/{source_id}/refresh` | `refresh_organization_capabilities` | Required |
| PUT | `/organizations/{organization_id}/capabilities/{source_id}/{capability_id}/default-on` | `set_organization_capability_default` | Required |
| GET | `/organizations/{organization_id}/capabilities/{source_id}/{capability_id}/revoke-impact` | `organization_capability_revoke_impact` | Required |
| GET | `/organizations/{organization_id}/model-policy` | `organization_model_policy` | Required |
| PUT | `/organizations/{organization_id}/model-policy` | `replace_organization_model_policy` | Required |
| POST | `/organizations/{organization_id}/model-sources/{source_id}/refresh` | `refresh_model_source` | Required |
| GET | `/organizations/{organization_id}/models` | `organization_models` | Required |
| GET | `/organizations/{organization_id}/supervision` | `organization_supervision` | Required |
| GET | `/organizations/{organization_id}/supervision/teams/{team_id}` | `team_supervision` | Required |

## /powerpoint-uploads routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| GET | `/powerpoint-uploads/{request_key}` | `powerpoint_upload_receipt` | Required |

## /skills routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| GET | `/skills/defaults` | `default_skills` | Required |

## /spaces routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| POST | `/spaces` | `create_space` | Required |
| DELETE | `/spaces/{id}` | `delete_space` | Required |
| GET | `/spaces/{id}/deletion` | `project_deletion_status` | Required |
| GET | `/spaces/{id}/document-uploads` | `receipts` | Required |
| GET | `/spaces/{id}/entries` | `entries` | Required |
| GET | `/spaces/{id}/member-candidates` | `space_member_candidates` | Required |
| GET | `/spaces/{id}/members` | `space_members` | Required |
| PUT | `/spaces/{id}/roles/{role}/{user}` | `grant` | Required |
| DELETE | `/spaces/{id}/roles/{role}/{user}` | `revoke` | Required |
| GET | `/spaces/{id}/storage` | `summary` | Required |
| GET | `/spaces/{marketplace_space_id}/marketplace/entries` | `marketplace_entries` | Required |
| GET | `/spaces/{marketplace_space_id}/marketplace/entries/{entry_id}` | `marketplace_entry` | Required |
| POST | `/spaces/{marketplace_space_id}/marketplace/entries/{entry_id}/installations` | `install_marketplace_entry` | Required |
| PUT | `/spaces/{marketplace_space_id}/marketplace/entries/{entry_id}/withdrawal` | `withdraw_marketplace_entry` | Required |
| GET | `/spaces/{marketplace_space_id}/marketplace/proposals` | `marketplace_proposals` | Required |
| POST | `/spaces/{marketplace_space_id}/marketplace/proposals` | `submit_marketplace_proposal` | Required |
| GET | `/spaces/{marketplace_space_id}/marketplace/proposals/{proposal_id}` | `marketplace_proposal` | Required |
| PUT | `/spaces/{marketplace_space_id}/marketplace/proposals/{proposal_id}/cancellation` | `cancel_marketplace_proposal` | Required |
| PUT | `/spaces/{marketplace_space_id}/marketplace/proposals/{proposal_id}/decision` | `decide_marketplace_proposal` | Required |
| GET | `/spaces/{space_id}/agent-instances` | `list_agent_instances` | Required |
| POST | `/spaces/{space_id}/agent-instances` | `create_agent_instance` | Required |
| GET | `/spaces/{space_id}/agent-instances/{agent_instance_id}` | `get_agent_instance` | Required |
| PATCH | `/spaces/{space_id}/agent-instances/{agent_instance_id}` | `update_agent_instance` | Required |
| DELETE | `/spaces/{space_id}/agent-instances/{agent_instance_id}` | `delete_agent_instance` | Required |
| POST | `/spaces/{space_id}/agent-instances/{agent_instance_id}/prepare-execution` | `prepare_execution` | Required |
| GET | `/spaces/{space_id}/agent-instances/{agent_instance_id}/runtime` | `resolve_runtime` | Required |
| POST | `/spaces/{space_id}/agent-instances/{agent_instance_id}/runtime` | `admit_runtime` | Required |
| GET | `/spaces/{space_id}/agent-templates` | `space_agent_templates` | Required |
| GET | `/spaces/{space_id}/capability-policies` | `space_capability_policies` | Required |
| PUT | `/spaces/{space_id}/capability-policies/{source_id}` | `replace_space_capability_policy` | Required |
| GET | `/spaces/{space_id}/marketplace-installations/{installation_id}` | `marketplace_installation` | Required |
| GET | `/spaces/{space_id}/mcp-connections` | `mcp_connections` | Required |
| POST | `/spaces/{space_id}/mcp-connections` | `create_mcp_connection` | Required |
| PUT | `/spaces/{space_id}/mcp-connections/{id}` | `update_mcp_connection` | Required |
| POST | `/spaces/{space_id}/mcp-connections/{id}/publish` | `publish_mcp_connection` | Required |
| POST | `/spaces/{space_id}/mcp-connections/{id}/test` | `test_mcp_connection` | Required |
| GET | `/spaces/{space_id}/mcp-credentials` | `mcp_credentials` | Required |
| GET | `/spaces/{space_id}/powerpoint-template` | `resolve_powerpoint_template` | Required |
| PUT | `/spaces/{space_id}/powerpoint-template` | `upload_powerpoint_template` | Required |
| DELETE | `/spaces/{space_id}/powerpoint-template` | `remove_powerpoint_template` | Required |
| POST | `/spaces/{space_id}/powerpoint-template/prepare` | `rerun_powerpoint_template` | Required |
| GET | `/spaces/{space_id}/powerpoint-template/settings` | `get_powerpoint_settings` | Required |
| PUT | `/spaces/{space_id}/powerpoint-template/settings` | `put_powerpoint_settings` | Required |
| GET | `/spaces/{space_id}/powerpoint-template/{file_id}/content` | `download_powerpoint_template` | Required |
| GET | `/spaces/{space_id}/prompt-categories` | `list_prompt_categories` | Required |
| POST | `/spaces/{space_id}/prompt-categories` | `create_prompt_category` | Required |
| PATCH | `/spaces/{space_id}/prompt-categories/{category_id}` | `rename_prompt_category` | Required |
| DELETE | `/spaces/{space_id}/prompt-categories/{category_id}` | `delete_prompt_category` | Required |
| GET | `/spaces/{space_id}/prompts` | `list_prompts` | Required |
| POST | `/spaces/{space_id}/prompts` | `create_prompt` | Required |
| GET | `/spaces/{space_id}/prompts/{prompt_id}` | `get_prompt` | Required |
| PATCH | `/spaces/{space_id}/prompts/{prompt_id}` | `update_prompt` | Required |
| DELETE | `/spaces/{space_id}/prompts/{prompt_id}` | `delete_prompt` | Required |
| PUT | `/spaces/{space_id}/prompts/{prompt_id}/favorite` | `add_prompt_favorite` | Required |
| DELETE | `/spaces/{space_id}/prompts/{prompt_id}/favorite` | `remove_prompt_favorite` | Required |
| GET | `/spaces/{space_id}/sessions` | `list_sessions` | Required |
| POST | `/spaces/{space_id}/sessions` | `create_session` | Required |
| GET | `/spaces/{space_id}/sessions/{session_id}` | `get_session` | Required |
| PATCH | `/spaces/{space_id}/sessions/{session_id}` | `update_session` | Required |
| DELETE | `/spaces/{space_id}/sessions/{session_id}` | `delete_session` | Required |
| GET | `/spaces/{space_id}/sessions/{session_id}/attachments` | `list_attachments` | Required |
| POST | `/spaces/{space_id}/sessions/{session_id}/attachments` | `upload_attachment` | Required |
| DELETE | `/spaces/{space_id}/sessions/{session_id}/attachments/{document_id}` | `delete_attachment` | Required |
| GET | `/spaces/{space_id}/sessions/{session_id}/attachments/{document_id}/content` | `download_attachment` | Required |
| POST | `/spaces/{space_id}/sessions/{session_id}/exchanges/{exchange_id}/usage` | `record_usage` | Required |
| GET | `/spaces/{space_id}/sessions/{session_id}/files` | `list_conversation_files` | Required |
| POST | `/spaces/{space_id}/sessions/{session_id}/files` | `write_conversation_file` | Required |
| GET | `/spaces/{space_id}/sessions/{session_id}/files/write-target` | `file_write_target` | Required |
| GET | `/spaces/{space_id}/sessions/{session_id}/files/{document_id}/content` | `download_conversation_file` | Required |
| GET | `/spaces/{space_id}/sessions/{session_id}/files/{document_id}/preview` | `preview_conversation_file` | Required |
| POST | `/spaces/{space_id}/sessions/{session_id}/generated-title` | `record_title` | Required |
| GET | `/spaces/{space_id}/skills` | `list_skills` | Required |
| POST | `/spaces/{space_id}/skills` | `create_skill` | Required |
| POST | `/spaces/{space_id}/skills/packages/{name}/install` | `install_skill` | Required |
| GET | `/spaces/{space_id}/skills/scope` | `skill_scope` | Required |
| GET | `/spaces/{space_id}/skills/scope/{skill_id}` | `preview_skill` | Required |
| GET | `/spaces/{space_id}/skills/{skill_id}` | `get_skill` | Required |
| PUT | `/spaces/{space_id}/skills/{skill_id}` | `put_skill` | Required |
| DELETE | `/spaces/{space_id}/skills/{skill_id}` | `delete_skill` | Required |
| GET | `/spaces/{space_id}/wiki/availability` | `wiki_availability` | Required |
| GET | `/spaces/{space_id}/wiki/pages` | `wiki_pages` | Required |
| POST | `/spaces/{space_id}/wiki/pages` | `create_wiki_page` | Required |
| GET | `/spaces/{space_id}/wiki/pages/{page_id}` | `wiki_page` | Required |
| PATCH | `/spaces/{space_id}/wiki/pages/{page_id}` | `patch_wiki_page` | Required |
| DELETE | `/spaces/{space_id}/wiki/pages/{page_id}` | `delete_wiki_page` | Required |
| PUT | `/spaces/{space_id}/wiki/pages/{page_id}/content` | `write_wiki_page` | Required |
| POST | `/spaces/{space_id}/wiki/pages/{page_id}/review` | `set_wiki_review_mark` | Required |
| GET | `/spaces/{space_id}/wiki/pages/{page_id}/revisions` | `wiki_revisions` | Required |
| POST | `/spaces/{space_id}/wiki/pages/{page_id}/revisions/{revision_id}/restore` | `restore_wiki_revision` | Required |
| POST | `/spaces/{space_id}/wiki/proposals/edit` | `propose_wiki_edit` | Required |
| POST | `/spaces/{space_id}/wiki/proposals/page` | `propose_wiki_page` | Required |
| GET | `/spaces/{space_id}/wiki/proposals/{proposal_id}` | `wiki_proposal` | Required |
| POST | `/spaces/{space_id}/wiki/proposals/{proposal_id}/publish` | `publish_wiki_proposal` | Required |
| GET | `/spaces/{space_id}/wiki/rules` | `wiki_rules` | Required |
| PUT | `/spaces/{space_id}/wiki/rules` | `write_wiki_rules` | Required |

## /users routes

| Method | Path | Operation | Authentication |
| --- | --- | --- | --- |
| GET | `/users/me/avatar` | `get_my_avatar` | Required |
| PUT | `/users/me/avatar` | `put_my_avatar` | Required |
| DELETE | `/users/me/avatar` | `delete_my_avatar` | Required |
| GET | `/users/me/preferences` | `get_my_preferences` | Required |
| PATCH | `/users/me/preferences` | `patch_my_preferences` | Required |
| GET | `/users/platform-roles` | `list_platform_roles` | Required |
| PUT | `/users/{user}/platform-roles/{role}` | `grant_platform_role` | Required |
| DELETE | `/users/{user}/platform-roles/{role}` | `revoke_platform_role` | Required |
<!-- end generated -->

## Consumption analytics

`POST /analytics/query` replaces the two consumption GET routes. The
[component README](../../apps/control-plane/README.md#consumption-analytics) retains
request/response examples and history configuration.
[analytics/mod.rs](../../apps/control-plane/src/analytics/mod.rs) validates the batch,
reuses the existing authorization decisions and executes compatible reads once
inside a read-only repeatable-read transaction. The journal aggregation stays in
[read.rs](../../apps/control-plane/src/sessions/usage/read.rs) and
[read.sql](../../apps/control-plane/src/sessions/usage/read.sql); no frontend project
expansion or raw-fact aggregation is required.

### Scopes, measures and budgets

A batch names 1..8 results. Names are distinct ASCII alphanumeric/underscore
strings, 1..64 bytes. Scope is
mandatory: `{"kind":"self","organization_id":"<working-organization UUID>"}`, or
`{"kind":"space","id":"<team-or-project UUID>"}`. Self combines the verified
subject AND that one organization. The organization must be active and the person
must retain a live non-personal role somewhere in it, including governance roles.
An old personal-space grant alone is insufficient; no organization or no current
right is a refusal, never a global fallback. Within an authorized organization,
old team/project memberships are not required to read one's own recorded facts.
No additional consent gate is introduced for self. Service
accounts and the `service_agent` role are refused. Collective reads retain
admission/consent and direct `ReadUsage` (Owner/Analyst), with the existing
outside-context, retirement and permission refusal precedence. Teams include
active, retired and purged projects; projects include only themselves. No user,
session or exchange identity is returned or accepted as a filter/group.

Every result requires `[since, until)` with explicit offset-bearing timestamps,
`since < until`, duration <=366 days and timezone `UTC`. Grouping is omitted/empty
for a total, or exactly one of `time`, `agent`, `model`. Only time grouping accepts
an optional bucket (`hour`, `day`, `week`); otherwise it is resolved automatically:
hour through 48 hours, day through 92 days, week thereafter. Weeks start Monday.
The first bucket may start before `since`, but facts remain clipped to the period.
Empty time buckets contain zero. Groups with no facts are absent.

Exact consumption measures are a distinct selection of `usage.input_tokens`,
`usage.output_tokens`, `usage.cache_read_tokens`, `usage.cache_creation_tokens`,
`usage.total_tokens`, `usage.recorded_exchanges`. Total tokens mean input + output,
without adding cache counters again. All values are non-negative decimal integer
strings, including SQL sums larger than bigint; JavaScript consumers must retain
strings or use `BigInt`, never silently convert to `Number`. Units are `token` or
`exchange`, and `value_type` is `integer`.

Recorded exchanges are distinct `(session_id, exchange_id)` whose first recorded
consumption belongs to the period. Previous reports are consulted even before
`since`: HITL resumes add tokens but not an exchange. Generated titles also create
recorded exchanges, so this measure does not count user messages. An exchange may
appear under multiple models; model distinct counts are not additive. Agent keys
are `(agent_instance_id, space_id)` with a nullable current/retained name; model
keys are `(model_source_id, upstream_model_id)`.

Agent/model rankings alone accept `limit` (1..100, default 100), ordered by input +
output tokens descending and stable identity keys for ties. An additional SQL row
detects truncation; `truncated:true` must be disclosed. Totals always include all
facts, independent of rankings. No implicit Other row or inferred remainder is
returned. Time series are never silently truncated.

Each result selects 1..12 distinct measures. Limits are 64 KiB request,
1000 points per series, 5000 maximum returned rows per
batch and 2 MiB serialized response. Invalid fields/combinations return 422
`invalid_fields`; row/byte budget failures return 422 `query_too_large`; oversized
requests return 413 `request_too_large`. Unknown fields, additional dimensions,
filters, comparison, multiple spaces in one scope, organization/platform scopes
and non-UTC calendars are rejected. There is no storage selection or expression API.

The service validates every query and authorizes every scope before reading data.
All SQL result reads use one `REPEATABLE READ READ ONLY` transaction. Compatible
scope/period requests share the full journal reader; multiple requested series
intervals need separate reads, while totals/rankings reuse one. The output limit
does not bound scanned facts or prior-exchange lookups: statements have a 5-second
timeout, locks a 1-second timeout, and the whole operation (including pool waits)
a 10-second deadline. A database/deadline failure returns 503
`dependency_unavailable` without partial results or fabricated zeros.

`calculation:exact` describes recorded facts only. Collection is best effort and
`collection_completeness:unknown` states that no completeness watermark is measured.
Each measure declares `calculation:exact` or `estimated`; the batch summary is
`mixed` when both occur. Token-only consumers retain `calculation:exact`.

The usage screen uses the generated RTK query client (POST remains the HTTP method).
One SQL batch contains the five consumption results below, for one explicit period
and either `scope:{kind:"self",organization_id:"<active UUID>"}` or
`scope:{kind:"space",id:"<team/project UUID>"}`. Personal skills use a separate
history batch, only in personal space:

| Batch | Result name | Measures | Grouping |
| --- | --- | --- | --- |
| SQL | `total` | `usage.input_tokens`, `usage.output_tokens`, `usage.total_tokens`, `usage.cache_read_tokens`, `usage.cache_creation_tokens` | total |
| SQL | `series` | `usage.total_tokens` | time |
| SQL | `agents` | `usage.total_tokens` | agent, limit 100 |
| SQL | `models` | `usage.total_tokens` | model, limit 100 |
| SQL | `impact` | `usage.cost_eur`, `usage.co2e_grams`, `usage.energy_kwh` | total |
| History | `skills` | `skills.user_loads`, `skills.agent_loads`, `skills.total_loads` | skill, limit 100 |

SQL returns `results.total/series/agents/models/impact`; history returns `results.skills`.
A row's `values` contains exact integer strings. Estimated decimals are instead in
`estimates`, for example `"usage.cost_eur":{"value":null,"coverage":"unavailable","fallback":true}`.
`coverage` is `complete`, `partial` or `unavailable`; `value:null` is not zero.
Empty SQL consumption yields a calculated zero. Partial sums include only fully
covered reports for that measure; they are not estimates of the uncovered portion.

Estimates use every journal report before ranking truncation, with PostgreSQL numeric
arithmetic. Rust embeds the same maintained
[`model_impact_factors.yaml`](../../libs/fred-core/fred_core/kpi/model_impact_factors.yaml)
that Python consumes; the Docker build includes that source. It documents the static
Mistral LCA extrapolation and energy assumptions. Lookup uses `upstream_model_id`,
with an explicitly flagged `default` for unlisted models. A known model's missing
or zero coefficients are unavailable, not free. Input includes cache reads and
creation: cost subtracts the clamped cache-read subset before charging its separate
rate, never adds creation again; CO2e and energy use input + output. USD cost is
converted with the catalog's static `usd_per_eur:1.12`, copied from Swift's display
convention, not a market quote. Currently all cost coefficients are unpopulated;
nonempty usage therefore has no cost estimate. No pricing or measurement claims
follow from these estimates.

Historical loads use `analytics/history.rs::Reader`, implemented by the OpenSearch
adapter. The port accepts a trusted subject, server-resolved organization space IDs, validated period and ranking limit;
its `skill_loads` and `completed_turns` operations fix the supported observations.
The planner shares compatible scope/period/reader calls across named results.
No engine type or DSL crosses into the service. Only self reads are supported;
collective history is forbidden and mixed SQL/history batches fail before execution.
Organization authorization and placement are resolved in a short SQL snapshot, released
before HTTP. No HTTP history call runs under a SQL transaction and no common
cross-source snapshot is claimed. A consumption-journal failure can leave skills
available; a failure of SQL authorization itself must deny historical reads. The UI preserves the available batch when the other fails, uses session-bound
RTK arguments including the organization and `currentData`, and explicitly refreshes fixed periods.
Home requests one total named `usage` with tokens, CO2e and energy through the
same generated query client and shared working organization.

The adapter filters `dims.user_id`, mandatory `dims.space_id` terms from that organization,
`metric.name`, `dims.skill_origin` and
`@timestamp` in `[since,until)`. Counts are successful-load events, not `metric.value`
or actor type. Like Swift, the grouping key is **skill name**, merging equal names
across spaces and revisions within the working organization; skill ownership does
not restrict self events. Placement follows the execution space. The Python KPI
mapping now indexes the already-emitted `dims.space_id`; no second emitter was added.
Old indexes missing this mapping are refused. Adding a mapping
does not backfill old unindexed events; no shared-index repair is performed.

A single composite aggregation gathers up to 10,001 names across all shards,
then sorts exact counts by total descending/name ascending and returns the requested
top-N with truncation. More than 10,000 names is an explicit budget error, not an
approximate ranking. Response bytes are bounded at 8 MiB internally and 2 MiB publicly.
Mapping incompatibility, absent index, partial shards, timeout and missing source
are unavailable errors, never empty success. Collection completeness remains unknown.

### Frontend consumption wiring and verification boundary

[TeamUsagePage](../../apps/frontend/src/rework/components/pages/TeamUsagePage/TeamUsagePage.tsx)
uses `useWorkingOrganization()` and its server-owned `memberships.currentData`.
The route UUID must match a team/project in the working organization, with a direct
Owner or Analyst role. Missing, loading, failed or mismatched context skips the
collective batch. Organization ownership and technical administration do not imply
child-space ReadUsage. Backend admission, consent and authorization remain final.
The sidebar and usage page share the direct-membership prefilter
[`canReadSpaceUsage`](../../apps/frontend/src/rework/core/utils/spaceUsage.ts).
The [space navigation](../../apps/frontend/src/rework/components/shared/layouts/Sidebar/TeamContentNavbar/TeamContentNavbar.tsx)
keeps Consumption in the existing settings navigation, reached through the header
gear, with no entry in the main content menu. Eligible teams/projects remain
accessible without content Read or membership Manage: the gear opens consumption
directly for an Analyst without Manage and exposes no management links;
the personal shortcut remains separate. The
[navigation tests](../../apps/frontend/src/rework/components/shared/layouts/Sidebar/TeamContentNavbar/TeamContentNavbar.test.tsx)
cover these entry points and their context/error/revocation gates.
The existing provider refreshes authority through its bounded membership refresh
and window-focus handling; this screen adds no polling.

The collective subscription is independent of Swift bootstrap and uses one
`useQueryAnalyticsQuery` batch for total, time, agents, models and impact. It is
separate from the self batch and personal skills. `sessionQueryArgs` binds the RTK
cache to identity; the scope and explicit period form the rest of the key.
`currentData`, current membership gating and error/fetching states prevent previous
results being presented after a context change or revocation. Explicit refresh
refetches collective consumption even for an unchanged fixed period.
[ConsumptionUsage](../../apps/frontend/src/rework/components/pages/TeamUsagePage/ConsumptionUsage.tsx)
shares precision, graphs and Rust estimates with
[PersonalUsage](../../apps/frontend/src/rework/components/pages/TeamUsagePage/PersonalUsage.tsx).
Totals retain `BigInt`; an unsafe chart counter becomes an exact table. Rankings
show truncation and estimates retain coverage/fallback markers. No browser estimate
is recomputed from total tokens.

Skills, activity, resource counts and storage in this page retain their legacy
clients and permissions, independently of collective ReadUsage. The administration
dashboard also retains the shared legacy consumption hooks. Their presence is not
an assertion of Weaver reception.

The [usage integration fixtures](../../apps/control-plane/tests/support/usage.rs)
cover isolation, collective rights, purge, HITL, numeric precision, refusal limits,
source failures and concurrent snapshots. Planner tests cover compatible read reuse.
[History adapter tests](../../apps/control-plane/tests/analytics_history.rs) cover
HTTP and three-shard aggregation. The
[collective UI tests](../../apps/frontend/src/rework/components/pages/TeamUsagePage/collectiveUsage.test.tsx)
exercise the actual generated client, working-organization provider and RTK cache
against a simulated HTTP boundary, including role, scope, revocation, late-response
and explicit-refresh cases. The
[shared rendering tests](../../apps/frontend/src/rework/components/pages/TeamUsagePage/personalUsage.test.tsx)
cover exact counters, chart overflow, missing values, errors and estimate coverage.
This consumption wiring is implemented; its new tests, code quality and browser
reception are to be executed by Dimi, not attested by source presence.

The home activity wiring also uses this service: the
[personal activity contract](../../apps/control-plane/README.md#personal-activity-implementation-reception-pending)
defines retained SQL creations separately from observed completed turns and exact
distinct agents. `HomePage::ActivityTab` shares generated-client requests for counters
and rankings; the historical port exposes a bounded `completed_turns` operation.
Current memberships are applied server-side before space ranking limits. This source
wiring excludes old events without canonical execution placement and does not establish
browser or deployment reception; the existing consumption/impact wiring is preserved.
