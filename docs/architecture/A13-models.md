# Reference: model and MCP governance

Companion to [model responsibilities](01-system-overview.md#14-model-decisions-and-credentials)
and [turn admission](02.3-agent-administration.md#2-configure-an-assistant-for-the-task).
The [selection contract](A2-manager-contracts.md#chat-model-preparation-and-turn-admission)
owns precedence, diagnostics and withdrawal fallback; the
[action/role matrix](A7-action-role-matrix.md#model-administration-and-the-first-managed-chat)
owns administration permissions. This reference supplies their generated technical
facts and implementation entry points, not another policy definition.

## MCP connection boundary

Companion to [the administration journey](02.3-agent-administration.md#models-and-mcp)
and [runtime responsibilities](01-system-overview.md#mcp-connection-to-agent-tools).
Model sources remain deployment-configured; external MCP connections are space-owned SQL
resources, currently managed only for organization spaces. Shared governance does
not imply identical provisioning, defaults or transport.

| Boundary | Canonical reference |
| --- | --- |
| Ownership and identity | [SQL migration 0023](../../apps/control-plane/migrations/0023_mcp_space_ownership.sql): required owning space, stable UUID and logical name unique per space |
| Connection management and validation | [MCP HTTP contract](../../apps/control-plane/src/mcp_connections/http.rs), [organization-scoped REST inventory](A12-control-plane-api.md#spaces-routes) |
| Permission | [Existing offer governance](../../apps/control-plane/src/agents/enablement.rs) and [role matrix](A7-action-role-matrix.md#model-administration-and-the-first-managed-chat) |
| Execution | [Managed MCP runtime](../../libs/fred-runtime/fred_runtime/common/managed_mcp.py) and [tool integration](../../libs/fred-runtime/fred_runtime/common/mcp_runtime.py) |

Internal Tabular uses the native capability policy and stable selection ID. The
[MCP binding contract](../../apps/control-plane/src/mcp_connections/mod.rs) distinguishes
an external connection with a reviewed inventory from an internal Knowledge Flow URL.
[Admission](../../apps/control-plane/src/mcp_connections/store.rs) constructs the latter
without discovery or a connection row; the runtime checks its destination and uses
turn delegation. The [capability README](../../libs/capabilities/fred-capability-mcp/README.md)
explains configuration and the [fresh-install constraint](../../apps/control-plane/migrations/0024_native_tabular.sql)
excludes internal authentication from administrable connections.

The following fragments are generated from existing responsibility anchors; they
identify the catalogue/admission bridge without copying its implementation.

<!-- generated: source-map apps/control-plane/src/mcp_connections/store.rs::available_offers apps/control-plane/src/mcp_connections/store.rs::bindings -->
| Implementation anchor | Responsibility declared in source |
| --- | --- |
| [`store.rs::available_offers`](../../apps/control-plane/src/mcp_connections/store.rs#L50) | Read the offer projection maintained in the same transaction as each connection mutation. Template pickers never need observed/published tool contracts. |
| [`store.rs::bindings`](../../apps/control-plane/src/mcp_connections/store.rs#L73) | Resolve in the admission snapshot. Caller has checked the same selection's organization/local policy. Network discovery never occurs in this transaction. |
<!-- end generated -->

Observation, reviewed publication, technical activation, permission and agent
selection are separate facts. The UI calls publication **Validate tools** or
**Apply changes**; REST retains its publication operation. A connection is one
governed capability offer, not one permission per discovered tool. Admission uses
the reviewed inventory and checks the selected connection in the trusted context.

The organization drawer derives its guided steps from these server facts:
check, review tools, then activate and authorize. The final action activates first
and grants usage only after success. These are separate requests, not an atomic
operation: if authorization fails, the connection remains active and the drawer
offers authorization again. Suspension and permission withdrawal remain separate
management actions. This UI composition does not change admission or publication
checks; deployed reception remains separate from component verification.

The [connection contract](../../apps/control-plane/README.md#managed-mcp-connections-reception-pending)
owns credential provisioning and runtime checks. A successful Control Plane
discovery or a UI check with simulated APIs is not proof of a tool call from a
deployed pod. This reference establishes responsibilities and contract boundaries;
it does not certify every deletion, replacement or in-flight execution scenario.

## Responsibility and implementation

| Boundary | Source of truth | Consumer / enforcement |
| --- | --- | --- |
| Approved destinations and inventory | [`ModelSource`](../../apps/control-plane/src/model_catalog/config.rs), platform configuration or organization-owned `organization_model_catalog` | [`discovery.rs`](../../apps/control-plane/src/model_catalog/discovery.rs), retained SQL observations; discovery grants no permission |
| Organization source assignment | [`model_catalog::initialization`](../../apps/control-plane/src/model_catalog/initialization.rs), `organization_model_source` | Startup/provisioning and the [operator CLI](../../apps/control-plane/README.md#assign-a-source-after-initialization) add sources under the organization lock; existing policies and receipts are preserved |
| Organization policy | [`policy.rs`](../../apps/control-plane/src/model_catalog/policy.rs), organization model tables | Organization Owner through [`http.rs`](../../apps/control-plane/src/model_catalog/http.rs); technical Admin alone cannot administer the policy |
| Organization team/personal model positions | [`access.rs`](../../apps/control-plane/src/model_catalog/access.rs), `organization_model_scope` | Organization Owner through the generated client and per-model access matrix; the shared projection applies restrictions without granting content access |
| Team/project policy | [`local_policy.rs`](../../apps/control-plane/src/model_catalog/local_policy.rs), `space_model_policy` and `space_model_setting` | Local Owner writes a revision-checked policy under the organization governance lock; the shared projection narrows parent permissions for configuration, preparation and admission |
| UI choices | [`preparation.rs`](../../apps/control-plane/src/agent_instances/preparation.rs), public `InferenceSelection` | [`OrganizationModels`](../../apps/frontend/src/rework/components/pages/admin/FeaturesPage/OrganizationModels.tsx), generated frontend client; preparation is not admission |
| Agent draft model | [`creation_assistant.rs`](../../apps/control-plane/src/agents/creation_assistant.rs), `organization_model_policy.creation_assistant_source_id` | Pod drafting uses the prompt-settings model override, then the catalogue creation model, then the author's space default. An explicit choice must be usable in that space. Drafting creates no conversation or agent |
| Chat dictation | [`policy.rs`](../../apps/control-plane/src/model_catalog/policy.rs), one optional `transcription` offer per organization | The [Control Plane](../../apps/control-plane/src/agent_instances/dictation.rs) checks the space's model rights and sends the clip to the selected file-transcription endpoint. The common [Knowledge Flow worker](../../apps/knowledge-flow-worker/knowledge_flow_worker/dictation.py) supplies the local Whisper option when deployed |
| Turn decision | [`resolve_runtime_binding`](../../apps/control-plane/src/agent_instances/runtime.rs), [`decide` / `admit`](../../apps/control-plane/src/model_catalog/instance.rs) | Space-derived organization, saved instance tuning and requested choice in a consistent snapshot |
| Shared wire contract | [`InferenceAdmission`](../../libs/fred-rust-sdk/src/inference.rs), Python [`contracts.weaver`](../../libs/fred-sdk/fred_sdk/contracts/weaver.py) | [Generated API types](../../apps/frontend/src/slices/controlPlane/controlPlaneOpenApi.ts); connection only on the trusted execution path |
| Python execution | [`TurnAuthority`](../../libs/fred-runtime/fred_runtime/model_routing/turn.py), [`RoutedChatModelFactory`](../../libs/fred-runtime/fred_runtime/model_routing/provider.py) | [`checked_clients`](../../libs/fred-runtime/fred_runtime/model_routing/guard.py) checks destination/authentication before transport |
| Client translation | `InferenceAdmission.chat_settings` in [`contracts.weaver`](../../libs/fred-sdk/fred_sdk/contracts/weaver.py) | Agent Pod and Knowledge Flow build chat clients from the admitted protocol, destination and options alone |
| Embedded Rust execution | [`InferenceTurn`](../../libs/fred-rust-agent/src/turn.rs) | [`Ralph`](../../libs/fred-rust-agent/README.md), hosted by Control Plane; local binding or encrypted credential checked before inference |
| Document models | Policy `embedding`, `vision` and `default`; source `embedding_models` attestation; [migration 0020](../../apps/control-plane/migrations/0020_document_models.sql) lock trigger | Stage claim [`stage_models`](../../apps/control-plane/src/processing/store.rs) / [`admit_document`](../../apps/control-plane/src/model_catalog/instance.rs) for the worker; [`cp_read.organization_model`](../../apps/control-plane/migrations/0020_document_models.sql), with the same availability criteria, for search and document tools |
| Knowledge Flow execution | [`DocumentModels`](../../libs/fred-knowledge/fred_knowledge/models.py) | Worker [`admit_models`](../../apps/knowledge-flow-worker/knowledge_flow_worker/application_context.py), backend [`organization_models`](../../apps/knowledge-flow-backend/knowledge_flow_backend/common/organization_models.py); local binding or destination-bound encrypted credential checked before inference; corpus stores cached by `DocumentModels.identity` |

Selection is shared; transport support is not identical. The
[runtime connection contract](../../apps/control-plane/README.md#inference-connection)
and [provisioning contract](../../apps/control-plane/README.md#workload-provisioning-and-rotation)
define supported forms. The Python Agent Pod supports every form of the contract.
Ralph and Knowledge Flow accept the `standard` route with `api_key` (Knowledge Flow
also `none`), without an API version or gateway header; Knowledge Flow refuses any
other form before a remote call. `wire` selects the generation protocol, chat
completions or responses; an embedding offer is always called at
`{api_root}/embeddings`. An option the admission leaves unset stays unset: no client
default replaces it. No consumer substitutes a local model policy for the admitted
selection.

An embedding aptitude can come from explicit provider capability metadata, a file
source's `embedding_models` attestation or an organization complement where the
provider is silent. Such an offer is never chat. Chat is attested by a declared list, by a
`chat_source` qualification, which then cannot also attest embedding models, or by
the source's own metadata (`mixed_capabilities_v1`). An advertised offer with no
reported use asks for confirmation before authorization. Its choices are marked
as unverified in model selectors. `model_use_options` applies the same eligibility
to policy writes, admission and document reads. For an unclassified offer, a
selection may try the requested use unless the source explicitly rules it out.
Organization owners can declare a single model by its exact provider ID and
usage. This uses the same credential and authorization path as a catalogue
without fetching the provider's model list. Optional models.dev enrichment
matches exact model IDs using the source hostname's label before the final suffix
or an explicit `metadata_provider`. Opening the catalogue reads its stored inventory.
The catalogue form loads it after creation or token rotation. Its refresh action
updates the selected source and applies the saved enrichment settings.
An outage or disabling the sync preserves previously enriched properties
for still-advertised offers.
Model properties show a license badge when the provider reports a license or
models.dev publishes one for the offer's canonical model ID. The platform terms
badge appears when the source configuration supplies an explicit public URL.
Organizations can record revision-checked manual complements. The catalogue's
Usages column opens the properties editor for supported uses and marks each
effective manual addition. Removing an addition restores detection for that use.
The organization can choose the display name shown in Weaver. The provider name
and exact inference identifier remain available independently of that display name.
Conversation preparation also includes the catalogue name shown in the model picker.
Provider-reported technical properties retain priority after a refresh.
A bounded set of provider-reported capabilities describes other model uses in the
catalogue without granting inference eligibility or inferring uses from names.
A withdrawn offer remains withdrawn even when it has manual complements. A policy
choice must fit its reported capabilities, including chat for default, fallback,
titles and agent drafts, embeddings for the corpus, and chat with image input for
vision when the provider reports that input. The indexed corpus keeps its model
under the existing lock and reindex workflow.

```mermaid
flowchart TB
    claim["Stage claim"] --> done{"Stage already<br/>committed?"}
    done -->|"Yes"| replay["Replay its manifest<br/>No model, no inference"]
    done -->|"No"| admit["Admit the stage's models<br/>in one policy snapshot"]
    admit -->|"Unusable"| stop["Refuse: no generation,<br/>no corpus lock"]
    admit -->|"Usable"| lock["First indexing: lock the<br/>corpus on the admitted model"]
    lock --> gen["Record the generation<br/>Worker infers"]

    classDef fred fill:#DBEAFE,stroke:#2563EB,color:#172554
    classDef neutral fill:#F1F5F9,stroke:#64748B,color:#0F172A
    class claim,admit,lock,gen,replay fred
    class done,stop neutral
```

A document model is never substituted: an unusable choice stops the stage. A new
generation is admitted before the claim records anything. The first indexing claim
then locks the corpus on exactly the admitted model, in the claim's transaction and
serialized with policy writes on the policy row; a policy changed in between is
retried, never locked on another model. A trigger refuses ordinary changes or deletion of the lock while the organization
exists. Migration 0054 permits changing the active model once the recorded corpus
reconstruction succeeds in the same transaction. A committed stage replays its
result with no admission, so a source disabled afterwards cannot block the replay.

Search applies the same availability as the worker's admission: an enabled source
observed at its current revision and a present offer with the aptitude of its use.
A failed discovery keeps the last observed offers; a withdrawn offer or a removed
attestation makes the corpus unavailable until the source changes, never another
model. Each organization's corpus is its own index, `document-vectors-<organization
id>` (pgvector: a collection with the same suffix), created by the first indexing.
A Temporal workflow re-embeds published chunks for documents and attachments in
a separate namespace. Current search stays on the active corpus during the
reconstruction. New indexing and changes to search visibility wait for the
replacement. Control Plane switches the model and namespace together on the
last acknowledgement, then queues the old namespace for cleanup. The model
settings display durable progress and the cleanup receipt. See
[the operation](../../apps/control-plane/README.md#rebuild-an-organizations-vector-corpus).
OpenSearch roles therefore grant the corpus prefix: write and index creation to the
ingestion worker, read to the API. Cleanup and visibility changes use the corpus
without an embedding model on both backends.

[Automatic conversation titles](../../apps/control-plane/README.md#automatic-conversation-titles)
receive their own Control Plane admission through `decide_title`, under the same
organization policy and local model restrictions. This optional title model does not create a runtime-local
selection rule.

Local policies keep restrictions separate from preferences. A policy header owns
the revision and optional default; sparse settings identify disabled offers or
reasoning defaults. Restrictions accumulate along the organization/team/project
path. Confirmed model metadata determines reasoning support on available chat
offers. The nearest saved policy replaces inherited reasoning preferences, while an
omitted model default inherits the parent's. Retained recommendations are not
erased when forbidden: admission refuses them. These source-level contracts do
not establish functional reception of the team settings journey.

The organization Owner's access matrix stores a sparse position for each model
and team, or for the whole personal-space class. Absence inherits organization
permission. Explicit enable never overrides an organization prohibition or a
team's own restriction. Team positions cover their projects; a personal-class
position covers both existing and future personal spaces. Writes use the shared
organization governance lock and policy revision. The matrix lists only team names
and access facts; it does not grant their roles or expose personal contents.
These positions affect chat admission, not the organization's sole embedding model.

## SQL view

**Legend:** 🟦 Fred · 🟨 COTS · 🟪 Extensions · ⬜ Concepts

Generated from the complete migration chain through PostgreSQL and tbls. This is
an induced subgraph: only relationships between the listed tables are shown.
Organization identifiers refer to `space`; instance recommendations/options live
in `agent_instance.tuning`. These external relationships remain in the
[complete SQL catalogue](A2-manager-contracts.md#control-plane-sql-catalogue).
The ER format shows columns and foreign keys, not every check, index or transaction:
consult the [migrations](../../apps/control-plane/migrations) for exact constraints.

<!-- generated: mermaid docs/architecture/generated/control-plane.er.mmd control_plane.model_source control_plane.model_offer control_plane.organization_model_source control_plane.organization_model_policy control_plane.organization_model_permission control_plane.organization_model_scope control_plane.organization_model_initialization control_plane.space_model_policy control_plane.space_model_setting control_plane.organization_model_catalog control_plane.organization_model_metadata control_plane.organization_vector_reindex control_plane.vector_corpus_retirement -->
```mermaid
erDiagram

"control_plane.model_offer" }o--|| "control_plane.model_source" : "source_id"
"control_plane.organization_model_policy" }o--|| "control_plane.organization_model_permission" : "organization_id, creation_assistant_source_id, creation_assistant_upstream_model_id"
"control_plane.organization_model_policy" }o--|| "control_plane.organization_model_permission" : "organization_id, default_source_id, default_upstream_model_id"
"control_plane.organization_model_policy" }o--|| "control_plane.organization_model_permission" : "organization_id, embedding_source_id, embedding_upstream_model_id"
"control_plane.organization_model_policy" }o--|| "control_plane.organization_model_permission" : "organization_id, fallback_source_id, fallback_upstream_model_id"
"control_plane.organization_model_policy" }o--|| "control_plane.organization_model_permission" : "organization_id, title_source_id, title_upstream_model_id"
"control_plane.organization_model_policy" }o--|| "control_plane.organization_model_permission" : "organization_id, transcription_source_id, transcription_upstream_model_id"
"control_plane.organization_model_policy" }o--|| "control_plane.organization_model_permission" : "organization_id, vision_source_id, vision_upstream_model_id"
"control_plane.organization_model_policy" }o--|| "control_plane.organization_vector_reindex" : "organization_id, corpus_generation"
"control_plane.organization_model_permission" }o--|| "control_plane.model_offer" : "source_id, upstream_model_id"
"control_plane.organization_model_permission" }o--|| "control_plane.organization_model_policy" : "organization_id"
"control_plane.organization_model_permission" }o--|| "control_plane.organization_model_source" : "organization_id, source_id"
"control_plane.organization_model_source" }o--|| "control_plane.model_source" : "source_id"
"control_plane.space_model_policy" }o--o| "control_plane.model_offer" : "default_source_id, default_upstream_model_id"
"control_plane.space_model_setting" }o--|| "control_plane.model_offer" : "source_id, upstream_model_id"
"control_plane.space_model_setting" }o--|| "control_plane.space_model_policy" : "space_id"
"control_plane.organization_model_catalog" |o--|| "control_plane.model_source" : "source_id"
"control_plane.organization_model_metadata" }o--|| "control_plane.model_offer" : "source_id, upstream_model_id"
"control_plane.organization_model_metadata" }o--|| "control_plane.organization_model_source" : "organization_id, source_id"
"control_plane.organization_model_scope" }o--|| "control_plane.model_offer" : "source_id, upstream_model_id"
"control_plane.organization_model_scope" }o--|| "control_plane.organization_model_source" : "organization_id, source_id"

"control_plane.model_source" {
  text source_id
  jsonb configuration
  uuid refresh_token
  text state
  text error_code
  timestamp_with_time_zone checked_at
  timestamp_with_time_zone last_success_at
  bigint snapshot_revision
  bigint snapshot_source_revision
  boolean managed
}

"control_plane.model_offer" {
  text source_id FK
  text upstream_model_id
  jsonb metadata
  timestamp_with_time_zone first_seen_at
  timestamp_with_time_zone last_seen_at
  boolean advertised
  timestamp_with_time_zone withdrawn_at
}

"control_plane.organization_model_source" {
  uuid organization_id FK
  text source_id FK
}

"control_plane.organization_model_policy" {
  uuid organization_id FK
  bigint revision
  text default_source_id FK
  text default_upstream_model_id FK
  text fallback_source_id FK
  text fallback_upstream_model_id FK
  text created_by
  timestamp_with_time_zone created_at
  text updated_by
  timestamp_with_time_zone updated_at
  text title_source_id FK
  text title_upstream_model_id FK
  text embedding_source_id FK
  text embedding_upstream_model_id FK
  timestamp_with_time_zone embedding_locked_at
  text vision_source_id FK
  text vision_upstream_model_id FK
  uuid corpus_generation FK
  text creation_assistant_source_id FK
  text creation_assistant_upstream_model_id FK
  text transcription_source_id FK
  text transcription_upstream_model_id FK
}

"control_plane.organization_model_permission" {
  uuid organization_id FK
  text source_id FK
  text upstream_model_id FK
  boolean reasoning_enabled
}

"control_plane.organization_model_scope" {
  uuid organization_id FK
  text source_id FK
  text upstream_model_id FK
  uuid team_id FK
  boolean enabled
  text updated_by
  timestamp_with_time_zone updated_at
}

"control_plane.organization_model_initialization" {
  uuid organization_id FK
  timestamp_with_time_zone completed_at
}

"control_plane.space_model_policy" {
  uuid space_id FK
  bigint revision
  text default_source_id FK
  text default_upstream_model_id FK
  text updated_by
  timestamp_with_time_zone updated_at
}

"control_plane.space_model_setting" {
  uuid space_id FK
  text source_id FK
  text upstream_model_id FK
  boolean disabled
  boolean reasoning_default_on
}

"control_plane.organization_model_catalog" {
  text source_id FK
  uuid organization_id FK
  text name
  bytea encrypted_token
  timestamp_with_time_zone deleted_at
}

"control_plane.organization_model_metadata" {
  uuid organization_id FK
  text source_id FK
  text upstream_model_id FK
  jsonb complements
  bigint revision
}

"control_plane.organization_vector_reindex" {
  uuid id
  uuid organization_id FK
  text requested_by
  text status
  jsonb admission
  uuid cursor
  bigint completed
  bigint total
  uuid lease
  timestamp_with_time_zone lease_until
  uuid document_id
  bigint chunk_cursor
  timestamp_with_time_zone deadline_at
  text error_code
  timestamp_with_time_zone created_at
  timestamp_with_time_zone completed_at
  uuid execution_id
  timestamp_with_time_zone dispatch_after
}

"control_plane.vector_corpus_retirement" {
  uuid organization_id
  uuid corpus_generation
  timestamp_with_time_zone due_at
  uuid replaced_by
  timestamp_with_time_zone cleaned_at
}

classDef fred fill:#DBEAFE,stroke:#2563EB,color:#172554
class control_plane.model_source,control_plane.model_offer,control_plane.organization_model_source,control_plane.organization_model_policy,control_plane.organization_model_permission,control_plane.organization_model_scope,control_plane.organization_model_initialization,control_plane.space_model_policy,control_plane.space_model_setting,control_plane.organization_model_catalog,control_plane.organization_model_metadata,control_plane.organization_vector_reindex,control_plane.vector_corpus_retirement fred
```
<!-- end generated -->

## Control Plane configuration

Generated from the [configuration schema](../../apps/control-plane/config/schema/configuration.schema.json).
`platform.model_sources` contains `ModelSource`; `platform.organization_models`
contains `OrganizationModels`: sources are added at startup/provisioning; permissions
and defaults are seeded once. Subsequent UI choices remain authoritative. Embedded Ralph's local bindings
are in `platform.inference_credentials`.

The schema defines shape and defaults. Cross-field validation and eligibility
remain in the linked Rust sources; a structurally valid configuration does not
prove provider connectivity. Environment-variable names below are references,
never credential values.

<!-- generated: schemas apps/control-plane/config/schema/configuration.schema.json ModelSource OrganizationModels InferenceCredentialBinding -->
### CredentialAuthority

One of: `discovery_only`, `discovery_and_inference`.

### DeclaredModel

A declared offer is chat unless attested for embedding or file transcription.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `audio_transcription` | boolean or null |  | Attest a dedicated model for multipart audio file transcription. |
| `context_window_tokens` | integer (int64), >= 1 or null |  |  |
| `display_name` | string or null |  |  |
| `id` | string | yes | Exact upstream identifier, never normalized. |
| `max_input_tokens` | integer (int64), >= 1 or null |  |  |
| `max_output_tokens` | integer (int64), >= 1 or null |  |  |
| `reasoning` | boolean or null |  |  |

### DiscoveryAuthentication

One of:

- `mode` = `public`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `mode` | `public` | yes |  |

- `mode` = `bearer`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `accept_inference_authority` | boolean |  |  |
| `authority` | [`CredentialAuthority`](#credentialauthority) | yes |  |
| `mode` | `bearer` | yes |  |
| `provider_scopes` | array of string | yes | Actual provider scopes, reviewed by the platform; a separate key proves nothing. |
| `secret_env_var` | string | yes |  |

### InferenceCredentialBinding

Local deployment attestation, independent of the received admission.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `api_key_env` | string | yes |  |
| `api_root` | string | yes |  |
| `credential_binding` | string | yes |  |

### ModelAuth

Authentication facts only: the secrets stay in the workload's local binding.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `client_id` | string or null |  |  |
| `gateway_key_header` | string or null |  | Name of the header carrying a gateway key, with any kind. |
| `kind` | [`ModelAuthKind`](#modelauthkind) | yes |  |
| `scope` | string or null |  |  |
| `tenant_id` | string or null |  | Required with kind `entra`, forbidden otherwise, like `client_id` and `scope`. |

### ModelAuthKind

One of: `none`, `api_key`, `entra`.

### ModelConnection

One destination, independent of the vendor: protocol, address and authentication. Mirrored by `fred_sdk.contracts.weaver`; `inference_connections.json` pins both.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `api_root` | string | yes | Separately approved canonical root; never derived from a discovery URL. |
| `api_version` | string or null |  |  |
| `auth` | [`ModelAuth`](#modelauth) | yes |  |
| `credential_binding` | string | yes | Source-bound workload provisioning reference; never a credential value. |
| `dialect` | [`ModelDialect`](#modeldialect) | yes |  |
| `route` | [`ModelRoute`](#modelroute) | yes |  |
| `wire` | [`ModelWire`](#modelwire) | yes |  |

### ModelDialect

One of: `openai`, `openai_compatible`, `mistral`.

### ModelOfferKey

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `source_id` | string | yes |  |
| `upstream_model_id` | string | yes |  |

### ModelRoute

One of: `standard`, `azure_deployment`.

### ModelSource

Platform approval of one source. Contains references only, never secret values.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `allow_insecure_http` | boolean |  | Explicit platform approval for internal HTTP routes; HTTPS is the default. |
| `embedding_models` | array of string, max items 256 |  | Extra attestation for offers without a published embedding capability. These exact offers compute embeddings and are never chat. |
| `enabled` | boolean |  |  |
| `inference` | [`ModelConnection`](#modelconnection) | yes |  |
| `inventory` | [`SourceInventory`](#sourceinventory) | yes |  |
| `metadata_provider` | string, min length 1, max length 64 or null |  | Optional models.dev provider ID. When omitted, derive it from the catalogue hostname. |
| `models_dev_enabled` | boolean or null |  | Defaults to true. Disabling synchronization retains the last enriched properties. |
| `platform_terms_url` | string, max length 2048 or null |  | Public link to the platform's license or terms of service. |
| `revision` | integer (int64) | yes | Strictly increase for every configuration change, including secret rotation. |
| `source_id` | string | yes |  |
| `visibility_scope` | string | yes | Stable provider account, model namespace and list visibility contract. A changed account/namespace/scope needs a new source_id, even with the same URL. |

### ModelWire

Generation protocol only. An attested embedding offer is always called at `{api_root}/embeddings`, the one embedding endpoint of these APIs.

One of: `openai_chat`, `openai_responses`.

### OrganizationModels

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `default` | [`ModelOfferKey`](#modelofferkey) or null |  |  |
| `embedding` | [`ModelOfferKey`](#modelofferkey) or null |  |  |
| `fallback` | [`ModelOfferKey`](#modelofferkey) or null |  |  |
| `organization` | string | yes | Exact existing organization name, resolved using the provisioning SQL lookup. |
| `permitted` | array of [`ModelOfferKey`](#modelofferkey), max items 4096 | yes |  |
| `reasoning_enabled` | array of [`ModelOfferKey`](#modelofferkey), max items 4096 |  | Deprecated deployment input. Reasoning support follows model metadata. |
| `sources` | array of string, max items 64 | yes |  |
| `transcription` | [`ModelOfferKey`](#modelofferkey) or null |  |  |
| `vision` | [`ModelOfferKey`](#modelofferkey) or null |  |  |

### Qualification

One of: `chat_source`, `mixed_capabilities_v1`.

### SourceInventory

Where this source's offers come from. A declared list replaces discovery for its source, never supplements it, and both publish through the same refresh.

One of:

- `kind` = `discovered`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `authentication` | [`DiscoveryAuthentication`](#discoveryauthentication) | yes |  |
| `complete_inventory_guaranteed` | boolean | yes | Platform attests that an unpaginated response lists the entire visibility scope. Without this guarantee, discovery cannot publish an authoritative inventory. |
| `kind` | `discovered` | yes |  |
| `qualification` | [`Qualification`](#qualification) | yes |  |
| `url` | string | yes |  |

- `kind` = `declared`

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `kind` | `declared` | yes |  |
| `models` | array of [`DeclaredModel`](#declaredmodel), min items 1, max items 256 | yes |  |
<!-- end generated -->

## Agent Pod and Knowledge Flow configuration

Python's top-level `inference_credentials` is generated from the
[Agent Pod configuration schema](../../apps/fred-agents/config/schema/configuration.schema.json),
whose owner is [`AgentPodConfig`](../../libs/fred-runtime/fred_runtime/app/config.py).
Knowledge Flow's backend and worker configurations carry the same type. It maps an
admitted binding/destination to local variables; it contains no model catalogue or
organization selection policy.

<!-- generated: schemas apps/fred-agents/config/schema/configuration.schema.json InferenceCredentialBinding -->
### InferenceCredentialBinding

A workload's local attestation of one admitted destination, read from its own configuration: variable names only, never secrets. Every model client (Agent Pod, Knowledge Flow) checks the Control Plane's admitted connection against it.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `api_key_env` | string or null |  | Default: `null`. |
| `api_root` | string | yes |  |
| `client_secret_env` | string or null |  | Default: `null`. |
| `credential_binding` | string, min length 1, max length 128 | yes |  |
| `gateway_key_env` | string or null |  | Default: `null`. |
<!-- end generated -->

## Deployment evidence

The local profile is owned by the factory; the [deployment guide](../../deploy/k3d/README.md#models-for-local-testing)
owns its operational procedure. It declares the `mistral` (discovered) and `openai`
(declared) sources, maps their bindings to the same API roots in Control Plane,
Agent Pod and Knowledge Flow, and gives each workload `MISTRAL_API_KEY` and
`OPENAI_API_KEY` from optional keys of the Kubernetes Secret `fred-model-credentials`.
The operator chooses the demo organizations' initial policy explicitly: Mistral by
default, or an OpenAI-only or mixed overlay. A source without its key stays
unavailable; it does not block a policy that does not use it. No Secret value is read
or embedded here. The
[rotation procedure](../../apps/control-plane/README.md#workload-provisioning-and-rotation)
covers source revision, refresh and workload rollout; environment variables are
process snapshots. Revoking a provider key can still interrupt an admitted turn.

Three kinds of evidence stay distinct. Source inspection and the generated references
here describe the code. Automated checks run on fakes and disposable databases and
prove no provider call. Only a deployed reception, recorded in its PR with the Fred and
factory revisions it used and its outcome, establishes that a configuration works; a
branch name or an uncommitted factory change is not such a record. Fred-only CI cannot
establish freshness of a separate factory checkout.

## Keeping this reference current

Use the existing architecture generator from `docs/architecture`:

```sh
make generate-models
make check-models
```

Generation rebuilds the SQL reference from disposable PostgreSQL and reads the
committed configuration schemas. The existing config-schema checks compare those
schemas with Rust/Pydantic types. `check-models` compares SQL without rewriting the
versioned diagram, checks these generated blocks and local navigation links, and
renders the reading-path diagrams. CI runs both the architecture and schema checks
on Weaver changes. A schema/type rename or changed field therefore requires a
regenerated reference, not a manually edited table.

Human review still owns diagram meaning, selection rules and runtime limitations.
Follow the source map when changing those responsibilities; update the main
explanation and its contract in the same PR. Generated references describe code,
not successful tests or deployed behavior. Shared inference fixtures and their
consumers are linked in the [runtime contract](../../apps/control-plane/README.md#workload-provisioning-and-rotation);
their presence is not an execution result.
