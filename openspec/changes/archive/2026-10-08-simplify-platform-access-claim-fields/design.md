## Context

The current picker already has verified session values, selectable exact paths and a separate catalog. Its default tree exposes protocol details that distract from account attributes.

## Goals / Non-Goals

Default to useful root text fields; preserve an explicit advanced path for all existing selections. Keep admission evaluation, APIs, saved rules and session-value privacy unchanged.

## Decisions

Use one exact-name metadata exclusion set in both sources. Current-session fields also require string values and a server-selectable path; observed fields require a root path and an observed string type. Do not impose an allowlist on custom business attribute names. Advanced mode restores the existing complete tree/catalog. Source and mode changes clear pending selection and copy state, preventing invisible fields from being confirmed. Search and empty feedback describe the displayed subset.

## Risks / Trade-offs

A custom attribute named like a protocol claim is hidden by default but remains selectable in advanced mode. This is a presentation rule, never an authorization restriction. Test both sources, nested compatibility, empty search, source/mode transitions and literal value reuse.
