---
schema: 1
title: "Prepare v3.2.0 release documents and audit dependency updates"
impact: none
configuration: none
configuration_reason: "Release notes and operator instructions only; the covered dependency updates change manifests and lockfiles without adding configuration keys or defaults."
no_action_reason: "Release preparation adds no runtime change. Reviewed npm and Python dependency updates require no data migration, re-ingestion or additional configuration; release-wide operations are declared in their respective source notes."
covers:
  - 287b5207f0f8477aeb5468f5d69b917b9302718a
  - 0c3be334f276c4c8bc13833d401e5ff2b5f6209b
---
## Applicability

Release preparation and the reviewed Dependabot contributions in the range from
`code/v3.1.1` to the v3.2.0 release commit.

## Prerequisites

Review all in-range migration notes before approving the paired code and chart
tags. The developer explicitly waived the pre-release Trivy assessment for
v3.2.0; it does not block this preparation.

## Configuration

No additional configuration is introduced by this contribution. Existing
production changes are documented in their owning notes.

The npm contribution updates KaTeX to 0.18.2, http-cache-semantics to 4.3.0 and
source-map-js to 1.2.2; nested Markdown renderers retain KaTeX 0.16.47. The Python
contribution updates fsspec, langgraph-sdk, Mako, multidict, PyJWT and uv across
application and library lockfiles. It changes no Python manifest, schema or
operator-facing setting. These contributions need normal image deployment only.

## Upgrade

Follow the consolidated guide. Preparation itself needs no additional action.
The source notes have been reconciled so the shared database is upgraded once,
with old readers stopped, and dependent validations use the final release head.
Conditional catalog, evaluator and identity-provider actions remain explicit.

## Validation

Generate and verify the v3.2.0 operator guide, confirm coverage is complete and
review the new release entry in Fred. No complete Trivy result is available
for this release; the developer waived that pre-release assessment.

## Rollback

Release-document changes need no data rollback. For runtime rollback, follow the
owning procedures, especially the CGU downgrade guard and irreversible removal
of retired agent capability selections.

## Limitations

This contribution does not publish independent npm or Python libraries, verify
customer overlays or validate a deployed external evaluator's API permissions.
The swift-dev assessment describes the latest published development images;
the release tags rebuild images from the approved release-document commit.
