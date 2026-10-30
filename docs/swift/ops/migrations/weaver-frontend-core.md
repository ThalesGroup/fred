---
schema: 1
title: "Use the Control Plane document contracts and retire unported Weaver screens"
impact: none
configuration: none
configuration_reason: "The frontend uses existing Weaver routes; no backend setting, schema or deployment configuration changes."
no_action_reason: "This pre-release UI cleanup requires no data migration or additional operator action."
---

## Applicability

Weaver frontend builds following the Knowledge Flow v2 client regeneration.
Dimitri approved temporarily withdrawing unported journeys on 2026-10-30.

## Prerequisites

Use matching Weaver Control Plane and frontend versions.

## Configuration

No configuration changes are required.

## Upgrade

Deploy normally. Documents, folder navigation, upload preflight, durable upload
receipts, processing, inclusion in search, previews and individual downloads use
the existing Control Plane contracts. The browser no longer calls the deleted
Knowledge Flow v1 document and generic task endpoints from these journeys.

## Validation

Run frontend TypeScript and root code-quality checks. The developer runs tests
and validates the journeys on k3d before considering them accepted end to end.
This note does not establish product-wide Weaver readiness.

## Rollback

Use the normal rollback procedure with matching backend and frontend versions.
No database rollback is introduced by this change.

## Limitations

The following journeys are explicitly deferred and withdrawn from this UI:

- Audio dictation in managed chat.
- Corpus audit and repair.
- Global and team activity views backed by the old generic task service.
- The old self-test diagnostics and their pipeline scenarios.
- The old platform migration/import/export screen.
- Team Knowledge Base management and their document libraries.
- Document renaming and labels; folder renaming remains available.
- Bulk ZIP downloads; individual document downloads remain available.
- Replacement of an existing document during upload; users can skip name
  conflicts and submit a file under another name.
- Folder-wide status rollups and byte totals from the old tag catalog.

Existing Control Plane import receipts and document processing status remain
visible. Obsolete Swift-only implementations and their contract tests are
removed; retained guards and document tests are adapted to Control Plane.
Other legacy frontend areas are outside this focused migration and are not
claimed to be ported or validated by this change.
