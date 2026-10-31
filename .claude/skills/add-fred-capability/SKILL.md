---
name: add-fred-capability
description: Integrate or extend a Fred capability through the shared SDK/runtime and existing capability libraries. Use for capability tooling, configuration or registration work; first determine what to reuse, extend, replace or remove rather than creating a parallel feature.
---

# Integrate a capability into Fred

Follow `AGENTS.md`. Start with the business use and existing capability surface.
Identify which capability or shared primitive can express it, which old behavior
it supersedes, and which code can disappear. A separate package, tool, hook or
configuration concept needs a concrete gap; a new feature name is not a reason.
For persisted domain changes, apply `fred-reconstruction-method` before API/UI.

## Inspect the actual extension points

Read current definitions and consumers, not old contract documents:

- `libs/fred-sdk/fred_sdk/contracts/capability/` for capability base classes,
  manifests, context, configuration scoping and human-interaction declarations;
- `libs/fred-sdk/fred_sdk/contracts/runtime.py` for runtime service ports;
- `libs/fred-runtime/fred_runtime/capabilities/` for registration and assembly;
- the nearest existing implementation under `libs/capabilities/`, particularly
  `fred-capability-document-access` for calls through knowledge service ports;
- the owning pod's installed distributions and entry points for actual discovery.

Verify APIs and supported execution models in this checkout. Imports or a manifest
alone do not prove a capability works in an integrated Weaver journey. Compare
current users before replacing a mechanism. An MCP integration may reuse the
catalog surface; do not create a second capability wrapper if it adds no behavior.
Model-call settings are not automatically tool capabilities.

## Keep responsibility in the owning library

Configuration models, `validate_config`, tools, service ports and capability UI
packs belong to the library/pod. Control Plane checks authority and forwards to
the owner; it does not contain per-capability schemas or business branches.
Use existing `tools()` or middleware extension points according to their actual
runtime support. Do not invent a hook or duplicate an execution path.

LLM tool arguments must not carry credentials or trusted identity/scope. Use typed
runtime services and server-bound context. Preserve resource access boundaries,
conversation attachment ownership, replay/idempotency and the turn admission
lifetime. Use the shared human-approval declarations instead of a private gate.

Inspect configuration-copy and validation consumers before introducing a scoped
reference or changing persisted configuration. Keep blobs in the owning storage
service, not configuration JSON. Do not add generalized versioning or a migration
layer without a real compatibility requirement.

Register through the existing distribution entry point. Do not hand-edit central
unions or registries that discovery generates. Reuse design-system components,
existing panels and controls; extend the shared primitive when genuinely necessary.
Regenerate affected API clients through their existing commands.

## Deliver

Remove replaced paths and unused configuration within the accepted scope, after
checking consumers. Explain the shared mechanisms reused and the net change in
owned production code; separate tests, generated code and documentation. Do not
shrink checks or hide code in generated/minified blobs to claim a reduction.
Run scoped formatting/code-quality checks under `AGENTS.md`; run functional or
runtime tests only within the requested validation scope. Report remaining wiring
gaps without describing a prepared library as a working user feature.
