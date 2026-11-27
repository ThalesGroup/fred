---
schema: 1
title: "Improve conversation trace inspection and monitoring"
impact: none
configuration: none
configuration_reason: "The trace inspector, catalog, and bundled Grafana dashboard use the existing permissions and deployment settings."
no_action_reason: "Normal deployment enables the additive API and UI changes. Retained frame indexes are read in their existing storage format."
---

## Applicability

Fred deployments that use the conversation trace catalog or the bundled chat
failure investigation dashboard.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. Dashboard JSON imported manually into Grafana can be
reimported to pick up the revised tool and capability failure accent.

## Validation

Open a masked trace with retained SSE frames. The timeline and list display
event times and types. Grant consent and verify that selecting an event opens
the saved frame. In a multi-day conversation, check that turns are grouped by
local date and that saved history and SSE shortcuts sit before the turn time.
Open the catalog and check the five-minute interval beside Refresh now.

## Rollback

Use the normal deployment rollback. No data migration is involved.

## Limitations

Individual markers require retained frame indexes. During a rolling upgrade,
an older runtime can still serve existing evidence, and masked frame indexes
become available as its replicas upgrade.
