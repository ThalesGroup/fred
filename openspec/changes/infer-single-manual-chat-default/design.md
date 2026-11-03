## Context

The runtime builds a `ModelRoutingPolicy` from `ModelCatalog` and separately advertises `default_chat_profile_id` in `/agents/models-catalog`. The control plane uses that advertised value to decide whether its no-default admin dialog is needed. The platform binding already has its own table and migration.

## Goals / Non-Goals

**Goals:** Keep routing and advertisement consistent for a single manual chat profile, with or without discovery.

**Non-Goals:** Infer a default from discovery, change explicit YAML defaults, or persist an inferred choice in the control-plane database.

## Decisions

- Compute an effective default map from the catalog instead of modifying the YAML field. This preserves the operator's explicit configuration and avoids a new stored state that could become stale when profiles change.
- Count only manual chat profiles. Resolved discovery profiles carry source ownership, so they can be excluded even after they are appended to the catalog. Other capabilities do not influence the chat default.
- Use the same effective map for `ModelRoutingPolicy` and the pod catalog response. The existing control-plane and frontend paths then receive the correct default without a new API field or UI rule.

## Risks / Trade-offs

- A catalog with two manual chat profiles remains without an inferred default. This is intentional because either choice would be arbitrary; an explicit YAML or admin platform choice resolves it.
- Pods may have different manual catalogs. The existing control-plane status requires every reachable pod to report a default before suppressing the warning.

## Migration Plan

Deploy the runtime update without a database migration. Removing the update restores the prior requirement for an explicit YAML default. Existing saved platform bindings continue to take precedence.
