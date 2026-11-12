---
schema: 1
title: "Reuse Weaver PowerPoint analysis and let organization owners manage common templates"
impact: none
configuration: none
configuration_reason: "The existing Control Plane, pod worker, Temporal and storage configuration is reused; no new model, route or worker setting is required."
no_action_reason: "Fresh Weaver installations use existing space roles and preparation storage; this change needs no migration or additional activation."
---

## Applicability

Fresh Weaver installations using PowerPoint Builder. This refines the preparation
and common-template access described in weaver-powerpoint-file-ownership.md.
It does not enable the separate Swift preparation framework.

## Prerequisites

Use the existing Control Plane, logical pod and preparation worker configuration.
An organization Owner manages its common template; an agent's own template retains
the existing agent authoring permissions. Technical administrator status alone
does not grant either permission.

## Configuration

No configuration changes are required. Analysis remains structural; background
vision is unavailable and its unused model selector has been removed.

## Upgrade

Only fresh installations are supported. Use the normal Weaver installation
procedure. No database or object-store operation accompanies this change.

Common-template management, including previews and downloads, now requires
organization management permission instead of content write permission. Editors
can still configure their authorized agents and use the common template through
those agents.

## Validation

Rename an agent during or after template analysis: its preparation should be
retained. Replace its template: a new preparation should be created. After a
Control Plane-confirmed failure, retry from the agent form without uploading the
file again; unsaved form changes should remain local. Two concurrent retries
must not create two pending preparations.

With an organization Owner having no content role, manage the common template
and view its preview. An organization Editor without Owner must be refused on
that common-template administration path; agent-specific permissions are unchanged.

## Rollback

Use the normal application rollback procedure. No schema change is introduced;
the previous application behavior may reanalyse on descriptive edits and require
content write permission for common-template administration.

## Limitations

No vision activation, generic multi-capability preparation or forced refresh of
a successful analysis after analysis-rule changes is added. A pod interruption
alone is not sufficient to offer retry while Control Plane still considers the
preparation pending. Local checks do not attest a deployed Temporal/worker/UI journey.
