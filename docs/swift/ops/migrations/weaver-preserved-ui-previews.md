---
schema: 1
title: "Preserve Swift screens for incremental Weaver migration"
impact: none
configuration: none
configuration_reason: "The additional preview server is developer-only; deployed application configuration and backend contracts are unchanged."
no_action_reason: "No operator action or data migration is required for this pre-release frontend correction."
---

## Applicability

Weaver following `weaver-frontend-core.md`. This correction supersedes that note's
source-removal approach: temporarily unavailable does not mean deleted. Dimitri
requested preserved Swift screens and development fixtures on 2026-10-30 so that
Swift merges can continue while features are ported in small increments.

## Prerequisites

Use matching Weaver frontend and Control Plane versions. For the optional local
preview, use the frontend's normal Node dependencies.

## Configuration

No deployment configuration changes. `make -C apps/frontend swift-preview`
starts an isolated local development server on port 5174 with no backend proxy.
It is not a production build or a backend fallback.

## Upgrade

Deploy normally. The normal UI retains Control Plane document navigation,
imports, processing, folder mutations, previews and individual downloads.
Pending journeys retain their routes and navigation entries with an explicit
availability notice. `/weaver/features` lists the pending work; development
builds link to the separate Swift preview gallery.

Preserved components and tests return to their original source locations. A
byte-identical previously generated Swift Knowledge Flow client lives under
`slices/legacyKnowledgeFlow`; its normal transport rejects requests. The current
Weaver v2 client and generation/drift workflow remain unchanged.

The preview mounts original components with local fixtures, a separate store,
network denial and explicit errors for unmodelled actions. It neither verifies
nor grants real permissions. Production route guards remain in place.

## Validation

Run frontend type, format and lint checks and root code quality. The developer
runs tests and accepts actual journeys from the regular UI. Preview output must
never be treated as evidence that a Weaver backend feature works.

## Rollback

Revert the frontend correction with matching backend/frontend versions. There
is no schema change or database rollback.

## Limitations

Preview coverage and the next small lot for each feature are recorded in
`apps/frontend/src/dev/swiftPreview/README.md`. Import/export/reset operations
and diagnostic executions are not simulated. Unmodelled interactions fail
explicitly. Audio transcription is a constant local fixture.

Shared document components retain their Swift/Control Plane branches during
this transition. Preserve the live Control Plane branch when merging Swift;
move each newly ported caller to its actual backend-generated slice. Remove the
associated fixture and pending route only after that journey is validated.
Other legacy frontend areas are outside this focused change.
