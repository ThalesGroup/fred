## Context

`ModelCatalog` currently parses local YAML. `_build_chat_model_factory` resolves it once at pod startup, while `GET /agents/models-catalog` rereads the file for control-plane. Control-plane already projects that response into `kind="model"` capabilities; `FeaturesPage` already has the access switches. The new source must keep the startup routing snapshot and the advertised inventory aligned.

The [OpenAI model-list API](https://developers.openai.com/api/reference/resources/models/methods/list) defines `GET /v1/models` with `data[].id`, `created` and `owned_by`. It does not define a display name, context window, token limits or chat capability. [vLLM](https://docs.vllm.ai/en/v0.20.0/api/vllm/entrypoints/openai/models/serving/) adds `max_model_len`; [LiteLLM](https://docs.litellm.ai/docs/proxy/model_management) has richer, gateway-specific model information. The baseline therefore uses the common OpenAI shape and treats metadata extensions as optional.

## Goals / Non-Goals

**Goals:**

- One configured gateway source can replace a manually enumerated set of chat profiles.
- A discovered model has a stable identity across restarts and list reordering.
- The admin view and runtime agree on the same set of models.

**Non-Goals:**

- Moving model catalog ownership to control-plane (#2710), editing the endpoint in the browser, or supporting arbitrary provider-specific discovery protocols.
- Inferring reasoning support or chat capability from the standard OpenAI response. The configured source must expose chat-capable models; an optional model-id allowlist can narrow a mixed gateway without declaring full profiles.
- Hot reloading remote model inventory without a pod restart.

## Decisions

### 1. Add one opt-in `discovery` block to `models_catalog.yaml`

The block contains a stable `source_id`, an OpenAI-compatible inference `base_url` ending at `/v1` (or an equivalent API root), an optional `default_model_id`, and an optional list of included model ids. The pod calls `{base_url}/models`; the same base URL goes into each generated OpenAI chat profile. `OPENAI_API_KEY`, already required by the OpenAI chat factory, supplies the bearer credential for discovery and inference. The key never appears in YAML, catalog responses or logs. Keep the existing static `profiles` collection and settings merge. An absent discovery block makes no network call.

Allow `profiles` and `default_profile_by_capability` to be empty when discovery supplies a chat default. A static chat default and `discovery.default_model_id` are mutually exclusive; a discovered default must exist in the filtered response. This is enough for a discovery-only catalog without adding a database or a new admin configuration surface.

An alternative would fetch and persist the list in control-plane. The pod still needs each model at startup for routing, so that would create a second source and a startup dependency on control-plane for a pod-owned configuration. This change stays within the existing catalog boundary.

### 2. Resolve once at startup and retain the resolved catalog

Fetch with a short timeout and bounded response size. Require a successful JSON object with a `data` array and distinct nonblank string ids after filtering. Reject an empty filtered result, a missing default, duplicate ids and malformed metadata that would create an ambiguous identity. Reject non-HTTP(S) URLs, URL credentials and redirects; a configured local HTTP gateway remains possible. Report a sanitized source id and cause on failure, never response headers or authorization values.

Build generated `ModelProfile` values and merge them with static profiles before constructing `ModelRoutingResolver`. Retain that resolved catalog in the pod context for `/agents/models-catalog` when discovery is configured; the route does not repeat network discovery or advertise models the factory has not loaded. Catalogs without discovery keep their existing local-file read on the admin route. The alternative of polling the gateway on each admin read would expose unroutable models and make the admin page dependent on gateway latency.

The source is trusted deployment configuration, but the response is untrusted. Model ids are treated as data, validated and bounded. The optional allowlist addresses endpoints that mix chat and embedding models because `/models` supplies no standard modality field.

### 3. Keep wire names and authorization identities separate

Each generated profile uses the exact upstream `id` as `model.name`, which is sent to the gateway. Its `model_id` and `profile_id` are deterministic from `source_id` and a digest of the raw id, with a discovery namespace; they do not depend on response order or URL hostname. This avoids collisions between two gateways serving the same wire name and limits identifier characters crossing Fred's capability id normalization. Reject collisions with static profile ids or capability identities rather than silently merging unlike deployments. The initial deployment requires ordinary admin grants for new model capability ids; changing `source_id` intentionally creates new identities and requires new grants.

### 4. Project optional metadata through the existing model capability

The standard `id` is always shown. Prefer a nonblank upstream `name` or `display_name` for the label when present. Accept a positive integer `context_length` or `max_model_len` as context window; carry `max_input_tokens` and `max_output_tokens` separately because they are not equivalent to total context. Ignore unknown fields and invalid optional metadata. Add typed optional fields through the pod catalog response, control-plane `CapabilityCatalogEntry` and `CapabilityEnablementItem`, generated frontend client, and existing Models table. No database storage is needed; values are advisory. Absence displays no value, and no field changes the reasoning aptitude or access grant.

### 5. Reuse access and drift handling

The existing capability projection creates model rows with no grant by default. Default-on, per-team enablement, reasoning controls and chat policy validation remain the authorities. Discovery does not set `supports_thinking`; the reasoning control remains absent unless an explicit static profile declares it. A model removed from the gateway is absent after the next pod restart, and stored team policies hit existing unknown-profile handling. Rollout across pods must keep `source_id` and the relevant inventory consistent so team-selectable profile validation remains sound.

## Risks / Trade-offs

- A gateway may list non-chat models without capability metadata -> document the chat-only source contract and provide an optional id allowlist.
- A gateway may change model ids -> treat these as new model identities and require explicit grants; existing stored choices fail through current drift checks.
- A gateway outage blocks startup for an opted-in source -> fail clearly rather than silently starting with stale or partial routing data; existing pods without discovery are unaffected.
- A metadata extension may use another spelling or inaccurate value -> accept only named, typed fields and present them as information, never as a routing guarantee.

## Migration Plan

Deploy the new runtime and control-plane/frontend readers, then add a discovery block to the pod catalog and roll the pods. Verify the discovered rows and enable intended models in admin. Keep the old static profiles during a gradual move if their ids must remain available; choose a distinct source id and resolve collisions before rollout. Rollback removes the discovery block and restores the prior catalog/pod image; no schema or data rollback is needed, though grants to discovery-only ids become dormant.
