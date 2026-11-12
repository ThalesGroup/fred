---
schema: 1
title: "Integrate selected Swift changes into Weaver"
impact: none
configuration: none
configuration_reason: "The merge preserves Weaver's Rust Control Plane, existing workers, storage and generated API contracts; no additional runtime setting is introduced."
no_action_reason: "The selected HTML, CI and PowerPoint adaptations use existing installation mechanisms, while unsupported Swift features remain deferred."
---

## Applicability

Fresh Weaver installations incorporating Swift ancestry through
`222bc60acda8b806c2186bd241dfbf3db180fac2`. Git ancestry does not imply that every
Swift feature is enabled in Weaver.

## Prerequisites

Use the normal Weaver prerequisites, including the existing PowerPoint preparation
worker when that capability is enabled.

## Configuration

No configuration changes are required. The retired Python Control Plane and
OpenFGA are not restored. No generic preparation worker or background vision path
is introduced.

## Upgrade

Only fresh Weaver installations are supported. Use the normal installation
procedure. This merge adds no schema migration or live data operation.

## Validation

The selected changes are documented in html-artifact-link-guidance.md,
defer-pr-checks-until-ready.md and weaver-powerpoint-preparation-reuse.md.
Verify those behaviors using their individual validation instructions.

## Rollback

Use the normal application rollback procedure. This merge changes no database
schema or storage format.

## Limitations

The Swift unsent-attachment draft mechanism is excluded. The analytics redesign,
its new instrumentation and the SQL-backed home-agent suggestions remain deferred;
the current Weaver implementations and their existing limits remain in place.
Detailed source decisions and follow-up needs are recorded in
WEAVER_SWIFT_PORTAGE_A_REPRENDRE.md. No push or deployed acceptance accompanies
the local merge.
