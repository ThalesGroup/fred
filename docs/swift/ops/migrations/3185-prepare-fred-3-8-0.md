---
schema: 1
title: "Prepare the Fred 3.8.0 release"
impact: none
configuration: none
after: [2845-derive-document-access-from-folders, 3067-require-team-description, agent-pod-http-route, pod-charts-as-helm-dependency, t0-initial-import-null-body, 3185-recognize-pod-chart-production-values]
configuration_reason: "Release notes, independent Python package and capability versions, synchronized locks and pod chart appVersion values change; this preparation adds no application settings or chart values."
no_action_reason: "Release preparation adds no action beyond the team-description migration and optional Gateway activation documented in their source notes. Existing documents need no re-ingestion."
---
## Applicability

Fred deployments upgrading from 3.7.1 to 3.8.0. This release includes the team
description requirement, platform team registry editing, the agent-pod HTTPRoute,
pod chart dependencies, folder-derived document access and initial T0 import fix.

## Prerequisites

Review the team-description source note before deployment. Count teams that will
receive a default description and prepare an updated OpenFGA model if its model
ID is pinned. Optional HTTPRoute activation requires a suitable Gateway.

## Configuration

This release preparation adds no settings. The HTTPRoute source note describes
the optional agent-pod chart values; the team-description note describes the
authorization model update for pinned deployments.

## Upgrade

Apply the control-plane database migration, update a pinned OpenFGA model when
needed, then deploy the matching 3.8.0 images and charts. Follow the ordered
team-description procedure for rollout. Optional HTTPRoute activation can follow
the normal chart upgrade; no document re-ingestion is required.

The release prepares fred-core, fred-sdk and fred-runtime 4.5.5, and
fred-capability-documents 4.5.3. The document_extract, document_similarity and
document_verbatim manifests advance from 0.1.0 to 0.1.1 with compatible stored
configuration. Other capability packages and fred-pod keep their versions.

## Validation

Confirm the installed images and charts use 3.8.0. Validate team description
backfill and platform team editing, the initial T0 import, document reading in a
large library and pod chart rendering. If activated, confirm Gateway acceptance
and browser requests to the agent pod.

## Rollback

Follow the team-description source note's database downgrade procedure before
redeploying 3.7.1 images and charts; the downgrade can truncate descriptions.
Disable the optional HTTPRoute before rolling back its chart if it was activated.

## Limitations

The folder-access note records remaining folder enumeration and historical
orphaned document limitations. Python package publication is separate from image
and chart publication; external package consumers must wait for those coordinates.
