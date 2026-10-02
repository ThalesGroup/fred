## Context

See proposal.md. Existing React capture handlers recognize already-focused portals but cannot enumerate undiscovered raw portal controls. The current trap enumerates only aside descendants.

## Goals / Non-Goals

Goals: explicit, discoverable focus scope using public DOM/React APIs. Non-goals: discovering arbitrary React ownership, global portal policy, or changing Dialog trapping.

## Decisions

Add optional readonly `(HTMLElement | null)[]` portalRoots. Use a ref for current roots so array identity changes do not reinstall the focus effect or reset focus. Enumerate connected same-document roots plus the drawer, deduplicate and order tabbables by positive tabindex then document order. Cycle deterministically on unconsumed Tab within that scope. Retain React event ownership for nested self-trapping Dialogs and Escape priority. Consumers must use dedicated containers, never body or a shared application root.

## Risks / Trade-offs

A broad root would admit unrelated controls: document the dedicated-root requirement. Removed/hidden/disabled portal controls must be excluded on every keypress. Nested Dialog prevents its own Tab and retains priority. No focus probing or private React internals.

## Migration Plan

Update the neutral consumer to create a dedicated portal container and declare it. Document the additive prop in the existing migration note. Existing nonportal consumers need no change. Rollback the patch if validation fails.
