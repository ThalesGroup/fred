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
| `wiki_page`, `wiki_revision` | Page identity and revision references within the managed document model. |
| `deletion` | Durable cleanup receipt, deliberately surviving removal of its target. |
| `platform_bootstrap`, `platform_role_grant` | Bootstrap receipt and canonical direct platform grants. |
| `user_identity`, `terms_acceptance` | Observed directory profile and personal consent; neither grants content access. |

The ER diagram lists all tables, columns and keys; this table groups responsibilities.

### Physical relationships

The [complete ER diagram](generated/control-plane.er.mmd) is generated from the
migration chain. It remains available for database inspection without duplicating
all columns in the architectural reading path.

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
| [`spaces.rs::authorized_mutation`](../../apps/control-plane/src/spaces.rs#L674) | Acquire the bounded organization lock, then decide against current facts. |
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
remain separate from the source prompt's ownership.

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
