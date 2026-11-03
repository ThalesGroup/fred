---
schema: 1
title: "Refresh packaged skills and expose native load status"
impact: minor
configuration: production
configuration_reason: "An absent skills configuration now enables the packaged catalog; explicit null still disables it."
---
## Applicability

Deployments using managed agent runtimes and the chat frontend.

## Prerequisites

Review each agent pod's skills configuration. An absent key or empty object now loads the packaged catalog; `skills: null` keeps it disabled.

## Configuration

Custom skill directories keep their meaning. The packaged catalog now includes `analyze-data`, `compare-options`, `graph`, `grill-me`, `grounded-research`, `meeting-minutes`, and `summarize-document`. Packaged titles and descriptions have English and French frontend translations. Custom skill metadata remains unchanged.

The former packaged `mermaid` and `verify-answer` names are retired. `graph` provides diagrams and charts, with Mermaid guidance in a reference file. Some packaged skills are model-only or require explicit user selection as declared in their frontmatter.

## Upgrade

Deploy the updated runtime and frontend together. Review any saved prompts or integrations that invoke retired skill names.

## Validation

Start a conversation and select `/graph`. Confirm the model receives its procedure and that a skill-load status appears in the trace. Try an ineligible direct selection, then check that it is rejected. Switch languages and confirm packaged skill labels change while canonical invocation names do not.

## Rollback

Restore the previous runtime and frontend packages and any prior explicit skills configuration. Existing conversation history retains its recorded skill names.

## Limitations

Global activation controls are not part of this Weaver backport. The platform skill policy from Swift depends on its retired Python control plane and requires a separate Rust implementation. This draft also needs native Deep integration validation before merge.
