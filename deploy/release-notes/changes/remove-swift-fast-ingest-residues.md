---
schema: 1
title: "Remove Swift fast-ingest residues and delete the self-test attachment"
impact: none
configuration: none
configuration_reason: "Only unused frontend, runtime and validation code is removed and one self-test step gains a cleanup call; no configuration key, chart value or default changes."
no_action_reason: "No deployed component served or called the removed fast-ingest routes, and no schema, stored data or public route changes."
---
## Applicability

Fred deployments whose administrators run the Weaver self-test, and developers or agents that imported `fred_runtime.common.kf_fast_text_client`.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. Code importing `fred_runtime.common.kf_fast_text_client` must drop that import: the module is removed, and the `/fast/*` Knowledge Flow routes it called no longer exist. The `make validation-report` and `make integration-test-*` targets are removed with the Swift black-box suite; it remains on branch `swift`.

## Validation

As a platform administrator, run the conversations family of the self-test (`/admin/self-test`). The "Keep attachment retrieval inside its owning conversation" step passes, and the conversation used by the step no longer lists the diagnostic attachment afterwards.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No black-box multi-identity authorization suite exists for Weaver yet; the administrator self-test is the remaining in-product check.
