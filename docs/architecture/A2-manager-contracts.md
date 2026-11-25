# Control Plane contracts and evidence

The [resource map](06-resources.md) explains ownership and use. This reference
keeps the storage responsibilities and a few implementation anchors; permissions
are in the [SSI matrices](A7-action-role-matrix.md), routes in the [REST inventory](A12-control-plane-api.md).

## control-plane HTTP surface

| Boundary | Contract |
| --- | --- |
| Authentication | Public exceptions are marked in the REST inventory; other operations require a bearer token. |
| Admission | Business routes require current personal terms acceptance when configured. |
| Space access | Direct organization context, then the permission on the target space; no tenant selected by a token group. |
| Refusal order | Missing/outside-context space: 404; retired space: 409; missing permission: 403. Authorization probes return a decision instead. |
| Invalid input | Malformed JSON: 400; invalid typed fields: 422; oversized JSON: 413. Errors do not echo sensitive input. |

[Authentication and authorization](A6-security.md) explain exceptions and trusted delegation.

## Control-plane SQL catalogue

Control Plane owns its PostgreSQL schema; object storage holds binary content.
The [immutable migrations](../../apps/control-plane/migrations/) define constraints;
`cp_read` views are the bounded reader surface. Other services' private schemas
are outside this catalogue.

### Table responsibilities

| SQL group | Authority and lifecycle |
| --- | --- |
| `space`, `space_role_grant` | Placement and direct business roles; grants disappear with their space. |
| `team_join_link` | One rotating, expiring link per team; redemption writes the existing Member grant. Revoking the link does not revoke acquired membership. |
| `avatar` | Personal or team image and durable object-cleanup receipt; retired objects survive owner deletion until cleanup. |
| `prompt`, `prompt_category`, `prompt_favorite` | Space-owned definitions and categories; caller preferences. |
| `marketplace_entry`, `marketplace_proposal`, `marketplace_installation` | Frozen packages, catalogue decisions and independent-installation receipts; see the [backend contract](../../apps/control-plane/README.md#local-marketplace-api). |
| `agent_instance`, `session_metadata` | Assistant configuration and placement of private conversations. |
| `runtime_catalog`, `capability_source`, `capability_offer`, template/capability policies | Pod, managed MCP and application offers; shared organization and local authorization ceilings. |
| `application` | Organization-owned application registry: immutable UUID/logical name/owner, trusted UI/API destinations and entry permission. Presentation belongs to the linked offer; authorization uses organization capability policy; see [implementation references](#hosted-application-implementation-references). |
| `mcp_connection` | Space-owned configuration and published tools; purge removes offer projections and permissions. The organization management journey awaits [functional reception](../../apps/control-plane/README.md#managed-mcp-connections-reception-pending). |
| Model source, offer and policy tables | [Organization model governance](A13-models.md). |
| `folder`, `document`, `document_content`, `document_current` | Document placement, stored-content references and current content; bytes live in object storage. |
| `document_upload`, `document_processing`, `generation`, `artifact`, `document_storage` | Upload receipts, exact-content processing attempts, derived output inventories and installation storage binding. |
| `kb_definition`, `kb_instance`, `kb_run`, `kb_source_document` | [Managed-mirror admission](A9-documents.md#managed-mirror-admission), durable collection runs and source-to-document identity; document storage and policy remain shared. |
| `powerpoint_file`, `capability_preparation` | [Managed PowerPoint originals and prepared data](A9-documents.md#powerpoint-builder-data). |
| `wiki_page`, `wiki_revision` | Space-owned Wiki tree of pages and files and every proposal; a draft is bound to its conversation, accepted provenance survives it. A file revision owns one `purpose='wiki'` document copy. |
| `deletion` | Durable cleanup receipt, deliberately surviving removal of its target. `document_session_id` retains attachment provenance so team activity excludes private documents even after purge. |
| `platform_bootstrap`, `platform_role_grant` | Bootstrap receipt and canonical direct platform grants. |
| `user_identity`, `terms_acceptance` | Observed directory profile and personal consent; neither grants content access. |

The ER diagram lists all tables, columns and keys; this table groups responsibilities.
The [document storage reference](A9-documents.md#processing-behavior) distinguishes
the shared replacement and reprocessing foundation from human admission, which
still refuses processing after success, and the run-scoped managed-mirror boundary.

### Physical relationships

The [complete ER diagram](generated/control-plane.er.mmd) is generated from the
migration chain. It remains available for database inspection without duplicating
all columns in the architectural reading path.

### Storage assertions and effects

[Chapter 9](09-quality.md#structural-invariants-in-postgresql) explains the three
kinds of rule. This catalogue serves diagnosis and maintenance.

| Kind | SQL signal | Control Plane response |
| --- | --- | --- |
| Assertion: immutability or consistency | `23514`, rule named in `constraint` | 500 `invariant_violation` without detail; the error log carries `constraint` and `table` |
| Business refusal: storage quota | `FR001` | 422 `quota_exceeded` |
| Effect | None | Related rows change in the same transaction |

Declarative CHECK constraints raise the same assertion signal.
[Migration 0035](../../apps/control-plane/migrations/0035_trigger_diagnostics.sql)
adds missing constraint/table diagnostics to existing triggers without changing
their invariants or SQLSTATE. Every trigger needs
a comment starting with `assertion: immutability - `, `assertion: consistency - `
or `effect: `. `make -C docs/architecture check-models` rejects a missing or
malformed comment and a stale table. `document_move` is schema preparation: no
application path writes it yet.

<!-- generated: triggers docs/architecture/generated/control-plane.triggers.json -->
| Family | Table | Trigger / function | When | Why |
| --- | --- | --- | --- | --- |
| 1. Immutability | `agent_instance` | `agent_definition` / `protect_agent_definition` | BEFORE INSERT OR UPDATE / ROW | agent identity, placement and creation provenance; edit attribution |
| 1. Immutability | `application` | `application_identity` / `preserve_application_identity` | BEFORE UPDATE / ROW | application UUID, logical name and owning organization |
| 1. Immutability | `document` | `document_copy_frozen` / `forbid_document_copy_change` | BEFORE UPDATE / ROW | published Wiki and marketplace copies keep their bytes until retirement |
| 1. Immutability | `document` | `document_immutable` / `forbid_document_move` | BEFORE UPDATE / ROW | document placement |
| 1. Immutability | `document_content` | `document_content_immutable` / `protect_document_content` | BEFORE UPDATE / ROW | content bytes and publication; no current-content cleanup |
| 1. Immutability | `document_processing` | `document_processing_identity` / `protect_processing_identity` | BEFORE UPDATE / ROW | processing identity and terminal outcome |
| 1. Immutability | `document_upload` | `document_upload_request_immutable` / `protect_upload_request_fingerprint` | BEFORE UPDATE / ROW | Wiki and marketplace copy request identity survives proposal deletion |
| 1. Immutability | `folder` | `folder_immutable` / `forbid_folder_move` | BEFORE UPDATE / ROW | folder placement |
| 1. Immutability | `kb_definition` | `kb_definition_identity` / `protect_kb_identity` | BEFORE UPDATE / ROW | authenticated definition owner |
| 1. Immutability | `kb_instance` | `kb_instance_identity` / `protect_kb_identity` | BEFORE UPDATE / ROW | managed mirror source and placement |
| 1. Immutability | `kb_run` | `kb_run_identity` / `protect_kb_identity` | BEFORE UPDATE / ROW | admitted run scope and terminal outcome |
| 1. Immutability | `kb_service` | `kb_service_identity` / `protect_kb_service` | BEFORE UPDATE / ROW | dedicated collector identity and organization |
| 1. Immutability | `marketplace_entry` | `marketplace_entry_identity` / `protect_marketplace_entry` | BEFORE INSERT OR UPDATE / ROW | marketplace identity and successive publication versions |
| 1. Immutability | `marketplace_installation` | `marketplace_installation_immutable` / `protect_marketplace_installation` | BEFORE INSERT OR UPDATE / ROW | installation receipt and snapshot provenance |
| 1. Immutability | `marketplace_proposal` | `marketplace_proposal_immutable` / `protect_marketplace_proposal` | BEFORE INSERT OR UPDATE / ROW | submitted package, attribution and final decision |
| 1. Immutability | `mcp_connection` | `mcp_owner` / `protect_mcp_owner` | BEFORE UPDATE / ROW | MCP connection owner |
| 1. Immutability | `powerpoint_file` | `powerpoint_file_identity` / `protect_powerpoint_file` | BEFORE INSERT OR UPDATE / ROW | PowerPoint identity and terminal retirement; live upload owner |
| 1. Immutability | `powerpoint_file` | `template_scope` / `protect_template_scope` | BEFORE UPDATE / ROW | a template receipt keeps its capability and bounded library slot |
| 1. Immutability | `prompt` | `prompt_definition` / `protect_prompt_definition` | BEFORE INSERT OR UPDATE / ROW | prompt identity and creation provenance |
| 1. Immutability | `session_metadata` | `session_identity_not_reused` / `forbid_session_recreation` | BEFORE INSERT / ROW | retired conversation identifiers cannot be reused |
| 1. Immutability | `space` | `space_immutable` / `forbid_space_move` | BEFORE UPDATE / ROW | space identity and hierarchy |
| 1. Immutability | `wiki_revision` | `wiki_revision_immutable` / `protect_wiki_revision` | BEFORE INSERT OR UPDATE / ROW | wiki revision content and provenance; conversation provenance only through a draft of its owner's live conversation; file revisions copy a catalogue output or an authenticated editable-document or workspace export; only acceptance clears the proposed parent |
| 2. Cross-row consistency | `agent_instance` | `agent_discovery` / `protect_resource_discovery` | BEFORE INSERT OR UPDATE / ROW | personal resource metadata stays private |
| 2. Cross-row consistency | `agent_template_policy` | `agent_template_policy_organization` / `require_organization_space` | BEFORE INSERT OR UPDATE / ROW | template policy belongs to an organization |
| 2. Cross-row consistency | `application` | `application_organization` / `require_model_policy_organization` | BEFORE INSERT OR UPDATE / ROW | application owner is an organization |
| 2. Cross-row consistency | `avatar` | `avatar_space_kind` / `require_team_avatar` | BEFORE INSERT OR UPDATE / ROW | collective avatars belong only to teams; personal avatars belong to subjects |
| 2. Cross-row consistency | `document` | `document_current_valid` / `protect_document_current` | BEFORE INSERT OR UPDATE / ROW | live owned content and atomic exact-content source publication |
| 2. Cross-row consistency | `document` | `kb_source_placement` / `protect_kb_source_placement` | BEFORE UPDATE / ROW | managed source placement and name are immutable |
| 2. Cross-row consistency | `document_content` | `document_preview_valid` / `protect_document_preview` | BEFORE INSERT / ROW | preview belongs to its primary content |
| 2. Cross-row consistency | `document_move` | `document_move_identity` / `protect_document_move` | BEFORE INSERT OR UPDATE / ROW | live same-organization move endpoints, frozen request and valid transitions |
| 2. Cross-row consistency | `document_move` | `kb_source_move` / `protect_kb_source_placement` | BEFORE INSERT / ROW | managed source cannot move or receive manual moves |
| 2. Cross-row consistency | `document_processing` | `kb_processing_scope` / `protect_kb_document_scope` | BEFORE INSERT OR UPDATE / ROW | immutable processing run and source content |
| 2. Cross-row consistency | `document_processing` | `processing_source` / `require_processing_source` | BEFORE INSERT OR UPDATE / ROW | ingestion only accepts source documents |
| 2. Cross-row consistency | `document_upload` | `document_upload_source_reservation` / `require_source_reservation` | BEFORE INSERT OR UPDATE / ROW | source uploads reserve initial bytes or replacement growth |
| 2. Cross-row consistency | `document_upload` | `kb_upload_scope` / `protect_kb_document_scope` | BEFORE INSERT OR UPDATE / ROW | immutable source transfer bound to its run |
| 2. Cross-row consistency | `document_upload` | `upload_placement` / `require_upload_placement` | BEFORE INSERT OR UPDATE / ROW | upload target matches its declared destination |
| 2. Cross-row consistency | `folder` | `folder_pending_uploads` / `protect_pending_document_uploads` | BEFORE DELETE / ROW | no folder removal with pending uploads |
| 2. Cross-row consistency | `kb_instance` | `kb_instance_folder` / `require_kb_folder` | BEFORE INSERT / ROW | managed mirror owns an empty dedicated root folder |
| 2. Cross-row consistency | `kb_instance` | `kb_instance_organization` / `require_kb_instance_organization` | BEFORE INSERT / ROW | collection stays in its collector organization |
| 2. Cross-row consistency | `kb_service` | `kb_service_organization` / `require_model_policy_organization` | BEFORE INSERT OR UPDATE / ROW | collector owner is an organization |
| 2. Cross-row consistency | `kb_source_document` | `kb_source_scope` / `protect_kb_document_scope` | BEFORE INSERT OR UPDATE / ROW | source identity, placement and published version |
| 2. Cross-row consistency | `marketplace_proposal` | `marketplace_proposal_document` / `protect_marketplace_document` | BEFORE INSERT OR UPDATE / ROW | marketplace file descriptors refer to a verified immutable copy in the catalogue organization |
| 2. Cross-row consistency | `organization_capability` | `organization_capability_organization` / `require_organization_space` | BEFORE INSERT OR UPDATE / ROW | capability policy belongs to an organization |
| 2. Cross-row consistency | `organization_capability` | `organization_owned_offer_scope` / `require_owned_offer_permission_scope` | BEFORE INSERT OR UPDATE / ROW | owned offer authorization stays in its organization |
| 2. Cross-row consistency | `organization_home_agent` | `organization_home_agent_placement` / `protect_organization_home_agent` | BEFORE INSERT OR UPDATE / ROW | home agents belong to teams or projects of the same organization |
| 2. Cross-row consistency | `organization_home_settings` | `home_settings_organization` / `require_organization_space` | BEFORE INSERT OR UPDATE / ROW | home settings belong to an organization |
| 2. Cross-row consistency | `organization_model_catalog` | `model_catalog_organization` / `require_model_policy_organization` | BEFORE INSERT OR UPDATE / ROW | a catalogue belongs to an organization |
| 2. Cross-row consistency | `organization_model_initialization` | `model_initialization_organization` / `require_model_policy_organization` | BEFORE INSERT OR UPDATE / ROW | model initialization belongs to an organization |
| 2. Cross-row consistency | `organization_model_policy` | `model_policy_organization` / `require_model_policy_organization` | BEFORE INSERT OR UPDATE / ROW | model policy belongs to an organization |
| 2. Cross-row consistency | `organization_model_policy` | `organization_embedding_locked` / `keep_locked_embedding` | BEFORE UPDATE OR DELETE / ROW | an indexed corpus changes models only after successful reconstruction |
| 2. Cross-row consistency | `organization_model_scope` | `organization_model_scope_team` / `require_model_scope_team` | BEFORE INSERT OR UPDATE / ROW | organization model access targets an active local team or the personal class |
| 2. Cross-row consistency | `organization_model_source` | `model_source_organization` / `require_model_policy_organization` | BEFORE INSERT OR UPDATE / ROW | model source belongs to an organization |
| 2. Cross-row consistency | `organization_model_source` | `model_source_owner` / `require_owned_model_source` | BEFORE INSERT OR UPDATE / ROW | only the owning organization can assign its managed catalogue |
| 2. Cross-row consistency | `organization_powerpoint_settings` | `powerpoint_settings_file` / `protect_powerpoint_settings` | BEFORE INSERT OR UPDATE / ROW | settings reference the effective organization file |
| 2. Cross-row consistency | `organization_powerpoint_settings` | `powerpoint_settings_organization` / `require_organization_space` | BEFORE INSERT OR UPDATE / ROW | PowerPoint settings belong to an organization |
| 2. Cross-row consistency | `organization_prompt_settings` | `organization_prompt_settings_organization` / `require_organization_space` | BEFORE INSERT OR UPDATE / ROW | execution prompt settings belong to an organization |
| 2. Cross-row consistency | `prompt` | `prompt_discovery` / `protect_resource_discovery` | BEFORE INSERT OR UPDATE / ROW | personal resource metadata stays private |
| 2. Cross-row consistency | `session_metadata` | `session_association` / `protect_session_association` | BEFORE INSERT OR UPDATE / ROW | same-organization conversation association and immutable ownership |
| 2. Cross-row consistency | `skill` | `skill_discovery` / `protect_resource_discovery` | BEFORE INSERT OR UPDATE / ROW | personal resource metadata stays private |
| 2. Cross-row consistency | `space` | `space_hierarchy` / `require_space_hierarchy` | AFTER INSERT / ROW | organization root and project team parent |
| 2. Cross-row consistency | `space` | `space_pending_uploads` / `protect_pending_document_uploads` | BEFORE DELETE / ROW | no space removal with pending uploads |
| 2. Cross-row consistency | `space_capability_permission` | `local_owned_offer_scope` / `require_owned_offer_permission_scope` | BEFORE INSERT OR UPDATE / ROW | local owned offer permission stays in its organization |
| 2. Cross-row consistency | `space_capability_policy` | `space_capability_policy_kind` / `require_local_capability_space` | BEFORE INSERT OR UPDATE / ROW | local capability policy belongs to a team or project |
| 2. Cross-row consistency | `space_model_policy` | `space_model_policy_kind` / `require_local_model_policy` | BEFORE INSERT OR UPDATE / ROW | local model policy belongs to a team or project |
| 2. Cross-row consistency | `space_role_grant` | `space_role_scope` / `require_space_role_scope` | BEFORE INSERT OR UPDATE / ROW | personal owner and organization admin scope |
| 2. Cross-row consistency | `storage_budget` | `storage_budget_scope` / `require_storage_budget_scope` | BEFORE INSERT OR UPDATE / ROW | immutable budget owner and valid local or organization scope |
| 2. Cross-row consistency | `team_join_link` | `team_join_link_space` / `require_team_join_link` | BEFORE INSERT OR UPDATE / ROW | shareable membership links belong only to teams |
| 3. Effects | `agent_instance` | `capability_agent_retirement` / `invalidate_capability_preparation` | BEFORE DELETE / ROW | mark agent capability preparations obsolete |
| 3. Effects | `agent_instance` | `powerpoint_agent_retirement` / `retire_powerpoint_owner` | BEFORE DELETE / ROW | retire the agent PowerPoint files and schedule cleanup |
| 3. Effects | `capability_preparation` | `template_readiness` / `refresh_template_readiness` | AFTER INSERT OR UPDATE / ROW | recompute agent readiness from every current capability preparation |
| 3. Effects | `conversation_trace` | `conversation_trace_erasure` / `retire_trace_objects` | BEFORE DELETE / ROW | deleting capture metadata preserves durable evidence cleanup inventory |
| 3. Effects | `document` | `document_account` / `account_document` | BEFORE INSERT OR DELETE / ROW | adjust local and organization used storage bytes |
| 3. Effects | `document` | `document_contents_retirement` / `retire_document_contents` | AFTER UPDATE / ROW | schedule retired contents and superseded generation cleanup |
| 3. Effects | `document` | `document_updates_account` / `account_document_updates` | AFTER UPDATE / STATEMENT | aggregate local and organization used storage byte changes |
| 3. Effects | `document_processing` | `document_processing_content_finished` / `finish_processing_content` | AFTER UPDATE / ROW | release replacement growth reservation and schedule failed candidate cleanup |
| 3. Effects | `document_upload` | `document_upload_account` / `account_document_upload` | AFTER INSERT OR UPDATE OR DELETE / ROW | adjust local and organization reserved storage bytes |
| 3. Effects | `marketplace_entry` | `marketplace_publication_retirement` / `retire_marketplace_publication` | AFTER UPDATE / ROW | erase the former publication payload on replacement or withdrawal, preserving installation receipts |
| 3. Effects | `marketplace_proposal` | `marketplace_document_deletion` / `retire_marketplace_document` | AFTER DELETE / ROW | retire the original when its owning proposal is deleted |
| 3. Effects | `marketplace_proposal` | `marketplace_document_retirement` / `retire_marketplace_document` | AFTER UPDATE / ROW | retire the original and release quota when its proposal payload is erased |
| 3. Effects | `marketplace_proposal` | `marketplace_originals` / `bind_marketplace_originals` | AFTER INSERT / ROW | bind every verified configuration original to its immutable proposal |
| 3. Effects | `organization_model_policy` | `remember_model_policy` / `remember_model_policy_initialization` | AFTER INSERT / ROW | record organization model-policy initialization |
| 3. Effects | `organization_model_policy` | `retire_organization_corpus` / `retire_organization_corpus` | BEFORE DELETE / ROW | retain physical corpus retirement after organization deletion |
| 3. Effects | `powerpoint_file` | `capability_file_retirement` / `invalidate_capability_preparation` | AFTER UPDATE / ROW | mark file capability preparations obsolete |
| 3. Effects | `powerpoint_file` | `powerpoint_file_account` / `account_powerpoint_file` | AFTER INSERT OR UPDATE OR DELETE / ROW | adjust local and organization used and reserved storage bytes |
| 3. Effects | `powerpoint_file` | `powerpoint_settings_retirement` / `retire_powerpoint_settings` | AFTER UPDATE / ROW | clear organization settings referencing a retired or ineffective file |
| 3. Effects | `runtime_catalog` | `runtime_catalog_source` / `register_pod_capability_source` | AFTER INSERT / ROW | register the pod capability source |
| 3. Effects | `session_metadata` | `session_drafts_retirement` / `retire_conversation_drafts` | AFTER UPDATE / ROW | delete the Wiki drafts of a conversation marked for deletion |
| 3. Effects | `session_metadata` | `session_trace_retirement` / `retire_session_traces` | AFTER UPDATE / ROW | session retirement immediately revokes diagnostics and schedules physical evidence erasure |
| 3. Effects | `space` | `powerpoint_space_retirement` / `retire_powerpoint_owner` | BEFORE DELETE / ROW | retire the space PowerPoint files and schedule cleanup |
| 3. Effects | `space` | `space_avatar_retirement` / `retire_space_avatar` | BEFORE DELETE / ROW | retire team avatars while retaining their durable object cleanup journal |
| 3. Effects | `wiki_revision` | `wiki_copy_retirement` / `retire_wiki_copy` | AFTER DELETE / ROW | retire the Wiki copy of a removed file revision |
<!-- end generated -->

### Resource identity and conversation placement

| Identity | Meaning |
| --- | --- |
| UUID | Stable identity of a prompt or agent instance. |
| Logical name | Immutable reference, unique per resource type and space; a prompt's slash command. |
| Display name | Editable title, not an authorization fact. |
| Conversation | Owned by a person in a space; association with an agent does not transfer ownership. |

Placement and creation provenance are protected by SQL. Copies have independent
identities. Prepared schema capacity does not establish an integrated cross-space journey.

### Prompt implementation anchors

The prompt contract is described once in the [resource map](06-resources.md#prompts)
and [role matrix](A7-action-role-matrix.md#content-actions). These three anchors trace
write authorization, departure and deletion to existing common mechanisms.

<!-- generated: source-map apps/control-plane/src/spaces.rs::authorized_mutation apps/control-plane/src/spaces.rs::revoke apps/control-plane/src/prompts.rs::delete -->
| Implementation anchor | Responsibility declared in source |
| --- | --- |
| [`spaces.rs::authorized_mutation`](../../apps/control-plane/src/spaces.rs#L777) | Acquire the bounded shared content guard, then decide against current facts. |
| [`spaces.rs::revoke`](../../apps/control-plane/src/spaces.rs#L667) | Revoke access without deleting space-owned resources or their publications. A personal space is managed from its organization: its owner's roles can be removed there, never added, so an organization can always let a member go. |
| [`prompts.rs::delete`](../../apps/control-plane/src/prompts.rs#L256) | Delete the definition and its favorites. Catalogue snapshots are independent. The HTTP caller checks Write permission in the space mutation transaction. |
<!-- end generated -->

| Evidence | What it checks |
| --- | --- |
| [Backend prompt tests](../../apps/control-plane/tests/support/prompts.rs) | Four spaces, direct rights, independent field updates, categories, favorites, departure and deletion. |
| [Browser journey](../../apps/frontend/tests/prompts-browser.mjs) | Real UI, Control Plane and disposable PostgreSQL/Keycloak; four spaces, consumers and role isolation. No model generation. |
| [Editor tests](../../apps/frontend/src/rework/components/pages/PromptsPage/PromptsPage.test.tsx) | Omitted edits survive a refreshed server response; no stale form is reused. |
| [Scenario](../../apps/frontend/src/rework/features/pipeline/scenarios/promptsScenario.test.ts) and [launcher tests](../../apps/frontend/src/rework/components/pages/admin/SelfTestPage/SelfTestPage.test.tsx) | Explicit space selection, generated requests, pagination and cleanup with simulated HTTP. |

The generator checks anchor existence, adjacent comments and link freshness;
it does not prove the function's behavior. Test presence is not an execution result
or deployed acceptance. [SQL publication constraints](../../apps/control-plane/migrations/0018_marketplace.sql)
remain separate from the source prompt's ownership. The
[marketplace transactions](../../apps/control-plane/src/marketplaces/store.rs)
implement snapshot approval, withdrawal and installation receipts; the
[audience policy](../../apps/control-plane/src/marketplaces.rs) limits publication
to the source's organization. The [catalogue reader](../../apps/frontend/src/rework/components/pages/marketplace/MarketplacePage.tsx)
filters the complete loaded catalogue before display pagination; the
[package reader](../../apps/frontend/src/rework/components/pages/marketplace/MarketplacePackageView.tsx)
presents the submitted content without reading the source library. Their
[UI checks](../../apps/frontend/src/rework/components/pages/marketplace/MarketplacePage.test.tsx)
and [package checks](../../apps/frontend/src/rework/components/pages/marketplace/MarketplacePackageView.test.tsx)
use simulated responses, not deployed acceptance.

### Pod capability offers

A pod supplies offers; organization policy authorizes them; an agent selects among
usable offers. Local restrictions narrow the organization ceiling. Permission
changes affect new admissions, not an already admitted turn. See the
[capability journey](02.3-agent-administration.md#which-capabilities-can-an-assistant-use)
and [catalogue implementation](../../apps/control-plane/src/agents/catalog.rs).

The [agent catalogue](../../apps/control-plane/src/agents.rs) keeps healthy sources
in UI lists and logs omitted sources. Operations with saved runtime/template
provenance query only the owning pod; the embedded Ralph catalogue stays local.
Enabling a template by its derived UUID still discovers its provenance, while
revoking its organization default needs no pod discovery.

### Hosted application implementation references

Registration and entry admission are separate from each application's business
journey. The [registry and proxy contract](../../apps/control-plane/README.md#hosted-applications-reception-pending)
is the component entry point; these references do not establish end-to-end
acceptance of an application's business operations.

| Source | Responsibility |
| --- | --- |
| [Migration 0034](../../apps/control-plane/migrations/0034_hosted_applications.sql) and [0056](../../apps/control-plane/migrations/0056_organization_applications.sql) | Organization-owned registry and one linked `capability_offer` under `$applications`; no runtime entry. Logical names are unique within an organization; purge cascades to its registry and offers. |
| [Registry handlers](../../apps/control-plane/src/applications/http.rs) | Organization Owner registration, unauthorized initially; revision-checked updates; authorized collective-space catalogue without internal URLs. |
| [Admission](../../apps/control-plane/src/applications/mod.rs) and [capability policy](../../apps/control-plane/src/agents/enablement.rs) | Existing entry permission and organization ceiling, narrowed by team/project policy; personal spaces excluded. |
| [Proxy](../../apps/control-plane/src/applications/proxy.rs) | Approved destination, bounded transport and credential separation; see the [root transport inventory](A12-control-plane-api.md#root-application-transport). |
| [Application host](../../apps/frontend/src/rework/components/pages/TeamApplicationHostPage/TeamApplicationHostPage.tsx) and [bridge contract](../../apps/frontend/src/rework/features/applications/applicationHost.ts) | Stable logical name for the SDK; host-owned authenticated requests, no token in frame messages. |

Registered services are trusted extensions approved by their organization Owner, including private
service addresses. A same-origin iframe is not hostile-code isolation. Entry
admission does not replace the application's own resource ownership and business
permissions; its database and workers remain owned by that service. Application
offers are excluded from agent tool selection.

### Model storage

[Model governance](A13-models.md) owns the source/offer/policy mapping. Credentials
stay on the trusted execution path; the browser receives public choices.

### Chat model preparation and turn admission

| Selection | Rule |
| --- | --- |
| Precedence | Explicit chat choice, otherwise instance recommendation, otherwise nearest project/team default, otherwise organization default. No choice means refusal. |
| Local policy | Team/project restrictions only narrow the parent ceiling. The nearest saved policy supplies reasoning defaults; an explicit question choice overrides this preference within the model's aptitude and organization ceiling. |
| Eligibility | A model is identified by source and upstream ID; observation does not grant permission. An unknown, forbidden or unusable choice produces a diagnostic, never an arbitrary substitute. |
| Fallback | Only confirmed withdrawal can use the approved fallback, within the same source and provisioning account, and only when still permitted and usable. Failed discovery alone is not withdrawal. |
| Administrative writes | A new selection requires successful observation at the current source revision. |
| Browser preparation | Public choices and diagnostics; no credential and no grant to execute. |
| Turn admission | Control Plane makes a fresh decision; the runtime validates the trusted binding against local provisioning and retains it through the turn. |

[Model governance](A13-models.md) supplies the wire contracts and runtime limits;
[managed turn authority](A6-security.md#managed-agent-turn-authority) explains identity
and conversation binding. An enabled agent is not a model-readiness guarantee.

### Constraints and operational indexes

The [migration chain](../../apps/control-plane/migrations/) and generated ER diagram
are the authority for keys, constraints and indexes. The [quality guarantees](09-quality.md)
record the architectural invariants, separately from measured capacity.

## Permission storage and evaluation

PostgreSQL stores placement and direct grants. [The typed evaluator](../../apps/control-plane/src/authorization.rs)
returns decisions used by all business handlers; [roles](../../apps/control-plane/src/roles.rs)
define permissions. Mutations recheck authority under the shared organization lock.
No role inheritance, second permission engine or author-specific prompt grant is introduced.

## Provisioning declarations

The [provisioning journey](02.1-user-journeys.md#provisioning-the-business-account)
and [organization contract](A8-organizations.md#provisioning-people-and-spaces)
explain account and role import. The [declaration parser](../../apps/control-plane/src/blueprint.rs)
owns the ZIP contract; [component instructions](../../apps/control-plane/README.md#import-a-provisioning-bundle)
provide commands and examples. Optional `skills.json` and `prompts.json` declare
instruction content per declared space. The
[importer](../../apps/control-plane/src/provisioning.rs) creates absent entries in
the space transaction and keeps present ones unchanged, identified by skill name
or prompt logical name. Categories are resolved or created only for new prompts;
replay preserves existing prompt content, category choices and category renames.

## Space deletion contract

Retirement closes new access before physical cleanup. A durable receipt survives
the deleted target; cleanup resumes after failure. Author departure is a role
change, not space deletion. See [lifecycle authority](A6-security.md#space-retirement-and-cleanup-authority)
and [the lifecycle implementation](../../apps/control-plane/src/lifecycle/mod.rs).
