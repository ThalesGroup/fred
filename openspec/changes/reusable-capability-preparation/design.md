# Design

## Context

See [proposal.md](proposal.md). Swift relays capability assets from the control plane to a pod's `validate-config`; PPT Builder then stores `template_pptx` and `patterns_pdf` as binary columns in `cap_ppt_builder_analysis`, starts work on the serving replica, and remembers a `CapabilityModelPort` in that process. Swift already runs a Python control-plane Temporal worker, but has no shared capability-preparation worker. Weaver has a separate Temporal worker and generic runtime dispatch; its control-plane admission still binds a preparation to `powerpoint_file`/`ppt_builder`, and `agent_instance` has one preparation slot. Swift must avoid those two limits.

## Goals / Non-Goals

**Goals:**

- Make the durable preparation lifecycle and worker extensible to another installed capability without changing the control plane's capability-specific branches.
- Keep PPT-specific interpretation, PDF conversion, slide labelling and derived-result format in the PPT capability.
- Keep Swift's global default template, overrides, read behavior and author permissions.

**Non-Goals:**

- Move ordinary chat execution, all capability tools or Knowledge Flow ingestion onto this worker.
- Let agent authors or platform managers choose a vision model for PPT analysis.
- Port Weaver's Rust control-plane modules verbatim or introduce a new general-purpose asset UI.

## Decisions

### 1. A declarative preparation contract, implemented by installed capabilities

Extend the capability manifest with an optional preparation declaration naming the asset slots, input limits and whether preparation gates readiness. Extend `AgentCapability` with a `prepare(context)` hook and an optional cleanup hook for derived artifacts. The control plane sees only manifest metadata and opaque config/output references; the runtime registry resolves the capability ID and invokes the hook. Existing capabilities without a declaration keep their current save and runtime behavior. An integration fixture using a second, minimal capability will exercise the same path to prove the generic boundary.

The declaration can list preparation-relevant config fields. Changing other saved settings, such as PPT pattern overrides or build-time variety, does not create a new preparation revision. When the list is absent, the full config remains the preparation input for existing declarers.

Alternative: embed `ppt_builder` branches in the control plane as Weaver currently does. That would move ownership but leave each new capability requiring another admission and status implementation.

### 2. Control plane owns originals and preparation state; capability owns derived artifacts

At save, the control plane checks user/team authorization, resource limits and pod manifest, stores the original as an immutable object, then commits a capability-neutral asset record and preparation intention. The pod validates capability-specific content through the existing validation contract, using a short-lived reference or bounded stream rather than copying the binary into agent config. `capability_asset` records owner scope (agent or platform), runtime, capability, slot, hash, size, object key and lifecycle. `capability_preparation` records the asset/config revision, rules version, state, attempts, deadlines, workflow identity and opaque result reference. The agent's current config points to its current asset revision; it does not have a single preparation column. This is distinct from chat attachments and team documents, which have different access, retention and usage semantics; reusing their tables would blur ownership.

The PPT capability stores inventory and preview as derived objects with small metadata rows. It never owns the original upload or stores large PPTX/PDF bytes in SQL. Results are written to an attempt-specific key and only published after a compare-and-swap against the current revision. Old objects are reclaimed after active readers and attempts finish. The built-in Fred deck remains packaged; the platform replacement is an asset with a platform owner and atomic effective-pointer switch after success.

Alternative: retain Swift's capability SQL blobs and only move execution to a worker. That leaves large binary reads in SQL and a second ownership path for every new capability.

### 3. Durable dispatch and aggregate readiness

Persist the intention in the same database transaction as the agent/config revision. A dispatcher claims committed pending rows with bounded batches and sends a deterministic workflow ID to a pod-specific Temporal queue. On uncertain delivery it reconciles by workflow ID; a worker lease, bounded retry count and deadline recover stopped replicas. Temporal history carries IDs, never file contents, config secrets or model output. The worker runs from the `fred-runtime` library CLI in a separate deployment, boots the installed registry and shared clients, fetches the current work by workload identity, invokes `prepare`, then reports a fenced completion. The Fred chart starts one worker by default, while the preparation cutover remains gated by capability and control-plane flags. `fred-agents` exposes local and Docker Make targets, while the generic `agent-pod` chart can enable the same worker for another pod image without app-specific worker code. Worker concurrency and per-capability heavy-job budgets are configurable and bounded independently of chat pods.

Availability is derived from all current, readiness-gating preparation rows plus existing enabled/suspension rules. A success cannot clear another capability's pending state or an unrelated suspension. Listing and chat-picker reads consume this durable projection rather than polling a serving pod for one PPT-specific readiness answer. Status/read APIs expose each capability's state and safe summary only to authorized callers. A stale completion, removed capability or deleted agent is ignored; cleanup is idempotent.

Alternative: a process-local background task or a single `agent_instance.preparation_id`. Neither meets multi-pod recovery and multiple-capability readiness.

### 4. Knowledge Flow supplies the vision call, PPT Builder supplies semantics

Add an internal, authenticated Knowledge Flow endpoint accepting one bounded rendered image plus a bounded text prompt and returning the raw model answer and a safe service status. It uses the already configured `vision_model`, a reused client, an explicit timeout and a concurrency limit. A small capability-facing client/port calls it from the preparation worker. PPT Builder constructs the numbered-slot prompt, parses the answer and checks it against its deterministic geometry, capacities and allowed kinds. The endpoint does not know PPT slots, kinds or templates, and does not accept a model name or arbitrary image URL. A separate lightweight availability read tells the form whether a vision model is configured, without exposing model identity or credentials.

The `use_vision` toggle remains. If Knowledge Flow has no configured model, the UI disables it and new requests cannot enable it; existing saved `use_vision=true` inputs are reported clearly until the service is configured or the editor turns it off. Transient call failures or malformed responses fall back per slide to heuristic labels, as the current spec requires, with a recorded warning. Timeouts and retries are bounded; a whole-service outage does not hold a worker indefinitely. A re-run after analysis-rules changes uses the current Knowledge Flow model and needs no remembered pod model port.

Alternative: route the call through the agent's chat model or move the PPT prompt into Knowledge Flow. The first keeps model-selection coupling; the second makes Knowledge Flow own presentation semantics.

### 5. Remove the global vision-catalog projection end to end

Remove `supports_vision` and derived `model_vision_profile_ids`/`vision_profile_ids` from YAML, model-routing contracts, SDK manifests, pod catalog, control-plane APIs, generated frontend types and PPT UI. Retire PPT's `labelling_model`/`vision_profile_id` inputs and stored selection; old values are ignored on read and stripped on the next write or migration. Preserve unrelated model capabilities and chat routing. During rolling deployment, parsers tolerate legacy `supports_vision` in YAML and older payloads but never emit it from the new API.

Alternative: hide the chooser only in the frontend. That would leave an unused and misleading public contract.

## Risks / Trade-offs

- [Cross-service outage] -> Use deadlines, bounded retries and clear per-capability failure status; do not depend on a specific pod or silently claim vision succeeded.
- [Large uploads and concurrent users] -> Stream to object storage with size/hash bounds; batch dispatch and cleanup; cap worker concurrency and Knowledge Flow requests; test hundreds of simultaneous saves and multiple replicas.
- [Revision races] -> Use immutable asset IDs, unique job identity and compare-and-swap result publication; test replacement, deletion and duplicate delivery.
- [Compatibility during rollout] -> Deploy additive storage and service contracts first, read both legacy/new PPT records during backfill, switch writes only after worker availability, and remove legacy code/data after verification.
- [Knowledge Flow service token and prompt contents] -> Reuse existing workload identity, authorize only the worker service, limit input bytes/pixels/prompt size, redact images/prompts/model answers from logs and traces.

## Migration Plan

1. Add one reviewable additive database migration per PR for generic asset/preparation state and indexes. Deploy it before new writers. Deploy the Knowledge Flow endpoint and generic worker without enabling PPT cutover.
2. Backfill existing `cap_ppt_builder_analysis` rows into immutable objects and generic preparation records, preserving successful inventory, overrides, active platform default and the current `use_vision` value. Reconcile hashes and counts; leave legacy rows intact during the rollback window.
3. Enable new PPT writes and reads behind a rollout flag, per logical pod. Stop new legacy jobs, let running jobs finish or fence them, and keep the previous platform default effective until its replacement succeeds. Remove legacy model selections without changing the vision toggle.
4. Verify multi-pod recovery, cross-capability readiness, copy/import, admin defaults, authorization and cleanup on staging. Then remove the old SQL blob/background path and catalog flag. Keep a rollback path to the legacy reader until data and behavior are validated; later delete legacy blobs only after the rollback window.
