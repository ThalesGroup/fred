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
| `prompt`, `prompt_category`, `prompt_favorite` | Space-owned definitions and categories; caller preferences. |
| `marketplace_entry`, `marketplace_proposal`, `marketplace_installation` | Frozen packages, catalogue decisions and independent-installation receipts; see the [backend contract](../../apps/control-plane/README.md#local-marketplace-api). |
| `agent_instance`, `session_metadata` | Assistant configuration and placement of private conversations. |
| `runtime_catalog`, `runtime_capability`, template/capability policies | Observed pod offers and their authorization ceilings. |
| Model source, offer and policy tables | [Organization model governance](A13-models.md). |
| `folder`, `document`, `document_content`, `document_current` | Document placement, stored-content references and current content; bytes live in object storage. |
| `document_upload`, `document_processing`, `document_storage` | Upload receipts, processing attempts and installation storage inventory. |
| `powerpoint_file`, `capability_preparation` | [Managed PowerPoint originals and prepared data](A9-documents.md#powerpoint-builder-data). |
| `wiki_page`, `wiki_revision` | Space-owned editorial content, separate from the file catalogue; published provenance survives conversation deletion. |
| `deletion` | Durable cleanup receipt, deliberately surviving removal of its target. |
| `platform_bootstrap`, `platform_role_grant` | Bootstrap receipt and canonical direct platform grants. |
| `user_identity`, `terms_acceptance` | Observed directory profile and personal consent; neither grants content access. |

The ER diagram lists all tables, columns and keys; this table groups responsibilities.

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

Declarative CHECK constraints raise the same assertion signal. Every trigger needs
a comment starting with `assertion: immutability - `, `assertion: consistency - `
or `effect: `. `make -C docs/architecture check-models` rejects a missing or
malformed comment and a stale table. `document_move` is schema preparation: no
application path writes it yet.

<!-- generated: triggers docs/architecture/generated/control-plane.triggers.json -->
| Family | Table | Trigger / function | When | Why |
| --- | --- | --- | --- | --- |
| 1. Immutability | `agent_instance` | `agent_definition` / `protect_agent_definition` | BEFORE INSERT OR UPDATE / ROW | agent identity, placement and creation provenance; edit attribution |
| 1. Immutability | `document` | `document_immutable` / `forbid_document_move` | BEFORE UPDATE / ROW | document placement |
| 1. Immutability | `document_content` | `document_content_immutable` / `protect_document_content` | BEFORE UPDATE / ROW | content bytes and publication; no current-content cleanup |
| 1. Immutability | `document_processing` | `document_processing_identity` / `protect_processing_identity` | BEFORE UPDATE / ROW | processing identity and terminal outcome |
| 1. Immutability | `folder` | `folder_immutable` / `forbid_folder_move` | BEFORE UPDATE / ROW | folder placement |
| 1. Immutability | `marketplace_entry` | `marketplace_entry_identity` / `protect_marketplace_entry` | BEFORE INSERT OR UPDATE / ROW | marketplace identity and successive publication versions |
| 1. Immutability | `marketplace_installation` | `marketplace_installation_immutable` / `protect_marketplace_installation` | BEFORE INSERT OR UPDATE / ROW | installation receipt and snapshot provenance |
| 1. Immutability | `marketplace_proposal` | `marketplace_proposal_immutable` / `protect_marketplace_proposal` | BEFORE INSERT OR UPDATE / ROW | submitted package, attribution and final decision |
| 1. Immutability | `organization_model_policy` | `organization_embedding_locked` / `keep_locked_embedding` | BEFORE UPDATE OR DELETE / ROW | the indexed corpus embedding model |
| 1. Immutability | `powerpoint_file` | `powerpoint_file_identity` / `protect_powerpoint_file` | BEFORE INSERT OR UPDATE / ROW | PowerPoint identity and terminal retirement; live upload owner |
| 1. Immutability | `prompt` | `prompt_definition` / `protect_prompt_definition` | BEFORE INSERT OR UPDATE / ROW | prompt identity and creation provenance |
| 1. Immutability | `session_metadata` | `session_identity_not_reused` / `forbid_session_recreation` | BEFORE INSERT / ROW | retired conversation identifiers cannot be reused |
| 1. Immutability | `space` | `space_immutable` / `forbid_space_move` | BEFORE UPDATE / ROW | space identity and hierarchy |
| 1. Immutability | `wiki_revision` | `wiki_revision_immutable` / `protect_wiki_revision` | BEFORE UPDATE / ROW | wiki revision content and provenance |
| 2. Cross-row consistency | `agent_template_policy` | `agent_template_policy_organization` / `require_organization_space` | BEFORE INSERT OR UPDATE / ROW | template policy belongs to an organization |
| 2. Cross-row consistency | `document` | `document_current_valid` / `protect_document_current` | BEFORE INSERT OR UPDATE / ROW | published owned current content and fixed source identity |
| 2. Cross-row consistency | `document_content` | `document_preview_valid` / `protect_document_preview` | BEFORE INSERT / ROW | preview belongs to its primary content |
| 2. Cross-row consistency | `document_move` | `document_move_identity` / `protect_document_move` | BEFORE INSERT OR UPDATE / ROW | live same-organization move endpoints, frozen request and valid transitions |
| 2. Cross-row consistency | `document_processing` | `processing_source` / `require_processing_source` | BEFORE INSERT OR UPDATE / ROW | ingestion only accepts source documents |
| 2. Cross-row consistency | `document_upload` | `upload_placement` / `require_upload_placement` | BEFORE INSERT OR UPDATE / ROW | upload target matches its declared destination |
| 2. Cross-row consistency | `folder` | `folder_pending_uploads` / `protect_pending_document_uploads` | BEFORE DELETE / ROW | no folder removal with pending uploads |
| 2. Cross-row consistency | `organization_capability` | `organization_capability_organization` / `require_organization_space` | BEFORE INSERT OR UPDATE / ROW | capability policy belongs to an organization |
| 2. Cross-row consistency | `organization_model_initialization` | `model_initialization_organization` / `require_model_policy_organization` | BEFORE INSERT OR UPDATE / ROW | model initialization belongs to an organization |
| 2. Cross-row consistency | `organization_model_policy` | `model_policy_organization` / `require_model_policy_organization` | BEFORE INSERT OR UPDATE / ROW | model policy belongs to an organization |
| 2. Cross-row consistency | `organization_model_source` | `model_source_organization` / `require_model_policy_organization` | BEFORE INSERT OR UPDATE / ROW | model source belongs to an organization |
| 2. Cross-row consistency | `organization_powerpoint_settings` | `powerpoint_settings_file` / `protect_powerpoint_settings` | BEFORE INSERT OR UPDATE / ROW | settings reference the effective organization file |
| 2. Cross-row consistency | `organization_powerpoint_settings` | `powerpoint_settings_organization` / `require_organization_space` | BEFORE INSERT OR UPDATE / ROW | PowerPoint settings belong to an organization |
| 2. Cross-row consistency | `session_metadata` | `session_association` / `protect_session_association` | BEFORE INSERT OR UPDATE / ROW | same-organization conversation association and immutable ownership |
| 2. Cross-row consistency | `space` | `space_hierarchy` / `require_space_hierarchy` | AFTER INSERT / ROW | organization root and project team parent |
| 2. Cross-row consistency | `space` | `space_pending_uploads` / `protect_pending_document_uploads` | BEFORE DELETE / ROW | no space removal with pending uploads |
| 2. Cross-row consistency | `space_capability_policy` | `space_capability_policy_kind` / `require_local_capability_space` | BEFORE INSERT OR UPDATE / ROW | local capability policy belongs to a team or project |
| 2. Cross-row consistency | `space_role_grant` | `space_role_scope` / `require_space_role_scope` | BEFORE INSERT OR UPDATE / ROW | personal owner and organization admin scope |
| 2. Cross-row consistency | `storage_budget` | `storage_budget_scope` / `require_storage_budget_scope` | BEFORE INSERT OR UPDATE / ROW | immutable budget owner and valid local or organization scope |
| 3. Effects | `agent_instance` | `capability_agent_retirement` / `invalidate_capability_preparation` | BEFORE DELETE / ROW | mark agent capability preparations obsolete |
| 3. Effects | `agent_instance` | `powerpoint_agent_retirement` / `retire_powerpoint_owner` | BEFORE DELETE / ROW | retire the agent PowerPoint files and schedule cleanup |
| 3. Effects | `document` | `document_account` / `account_document` | BEFORE INSERT OR DELETE / ROW | adjust local and organization used storage bytes |
| 3. Effects | `document` | `document_contents_retirement` / `retire_document_contents` | AFTER UPDATE / ROW | schedule cleanup of retired or superseded file contents |
| 3. Effects | `document` | `document_updates_account` / `account_document_updates` | AFTER UPDATE / STATEMENT | aggregate local and organization used storage byte changes |
| 3. Effects | `document_upload` | `document_upload_account` / `account_document_upload` | AFTER INSERT OR UPDATE OR DELETE / ROW | adjust local and organization reserved storage bytes |
| 3. Effects | `organization_model_policy` | `remember_model_policy` / `remember_model_policy_initialization` | AFTER INSERT / ROW | record organization model-policy initialization |
| 3. Effects | `powerpoint_file` | `capability_file_retirement` / `invalidate_capability_preparation` | AFTER UPDATE / ROW | mark file capability preparations obsolete |
| 3. Effects | `powerpoint_file` | `powerpoint_file_account` / `account_powerpoint_file` | AFTER INSERT OR UPDATE OR DELETE / ROW | adjust local and organization used and reserved storage bytes |
| 3. Effects | `powerpoint_file` | `powerpoint_settings_retirement` / `retire_powerpoint_settings` | AFTER UPDATE / ROW | clear organization settings referencing a retired or ineffective file |
| 3. Effects | `space` | `powerpoint_space_retirement` / `retire_powerpoint_owner` | BEFORE DELETE / ROW | retire the space PowerPoint files and schedule cleanup |
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
| [`spaces.rs::authorized_mutation`](../../apps/control-plane/src/spaces.rs#L674) | Acquire the bounded shared content guard, then decide against current facts. |
| [`spaces.rs::revoke`](../../apps/control-plane/src/spaces.rs#L597) | Revoke access without deleting space-owned resources or their publications. A personal space is managed from its organization: its owner's roles can be removed there, never added, so an organization can always let a member go. |
| [`prompts.rs::delete`](../../apps/control-plane/src/prompts.rs#L252) | Delete the definition and its favorites. Catalogue snapshots are independent. The HTTP caller checks Write permission in the space mutation transaction. |
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
to the source's organization.

### Pod capability offers

A pod supplies offers; organization policy authorizes them; an agent selects among
usable offers. Local restrictions narrow the organization ceiling. Permission
changes affect new admissions, not an already admitted turn. See the
[capability journey](02.3-agent-administration.md#which-capabilities-can-an-assistant-use)
and [catalogue implementation](../../apps/control-plane/src/agents/catalog.rs).

### Model storage

[Model governance](A13-models.md) owns the source/offer/policy mapping. Credentials
stay on the trusted execution path; the browser receives public choices.

### Chat model preparation and turn admission

| Selection | Rule |
| --- | --- |
| Precedence | Explicit chat choice, otherwise instance recommendation, otherwise organization default. No choice means refusal. |
| Eligibility | A model is identified by source and upstream ID; observation does not grant permission. An unknown, forbidden or unusable choice produces a diagnostic, never an arbitrary substitute. |
| Fallback | Only confirmed withdrawal can use the approved fallback, within the same source and provisioning account, and only when still permitted and usable. Failed discovery alone is not withdrawal. |
| Administrative writes | A new selection requires successful observation at the current source revision; a retained legacy profile requires explicit reselection unless a recommendation exists. |
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
owns the ZIP contract; [component instructions](../../apps/control-plane/README.md)
provide commands and examples.

## Space deletion contract

Retirement closes new access before physical cleanup. A durable receipt survives
the deleted target; cleanup resumes after failure. Author departure is a role
change, not space deletion. See [lifecycle authority](A6-security.md#space-retirement-and-cleanup-authority)
and [the lifecycle implementation](../../apps/control-plane/src/lifecycle/mod.rs).
