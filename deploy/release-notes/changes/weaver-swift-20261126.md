---
schema: 1
title: "Weaver spreadsheet generation and Swift interface improvements"
impact: minor
configuration: none
configuration_reason: "Uses existing capability governance, conversation files and theme settings; no environment variable, chart value or secret is added."
---
## Applicability

Fresh Weaver installations using the standard fred-agents image and frontend.
This integration preserves Weaver 5.x versions and its Control Plane authority.
It replaces the incoming Swift-only operator instructions for this merge.

## Prerequisites

Deploy matching Control Plane, agent and frontend components. The spreadsheet
package is included in fred-agents; third-party pods keep their own package set.
The frontend image uses `nginx/nginx-unprivileged:1.31.10-alpine`; installations
that mirror images must make that image available through their existing process.

## Configuration

Use existing organization and space capability governance to make spreadsheet
generation available, then enable the Excel pack on the agent. No new global
activation or database configuration is introduced. Optional daily theme schedules
use the existing theme configuration and the browser's local clock.

## Upgrade

Use the normal fresh-install deployment procedure. Upgrades from Swift or earlier
Weaver installations remain unsupported. No spreadsheet table or migration is
introduced: generated workbooks and their previews belong to the conversation's
existing file catalogue and deletion lifecycle.

## Validation

In a conversation with an enabled agent, create a workbook, preview and download
it, then request a targeted change in the next turn. Both versions must remain
downloadable. Reload the conversation and repeat a change; stale or conflicting
sources must produce an explicit refusal, not overwrite an existing version.
Verify conversation deletion revokes access to its files through the usual path.

Also check resource table resizing and range selection, the friendly router error
page, copying error details, unsaved wiki history, and queueing a message while a
dialog is open. Agent model calls receive the current UTC date. These are developer
reception scenarios, not a claim that a deployed browser or provider was tested.

## Rollback

Use matching previous Weaver components through the normal deployment process.
Previously generated files remain ordinary conversation deliverables; removing
the capability removes its creation/revision tool. No capability database state
needs repair or conversion.

## Limitations

Revision requests refer to an exact file snapshot, with identifiers supplied to
the model rather than entered by the user. Workbooks carry their bounded revision
specification; imported or modified files without a valid specification cannot be
revised by this tool. There is no hidden mutable "last workbook" record.

Existing spreadsheet engine limits and unsupported formulas remain documented in
the package README. Existing conversation file quotas still apply. JSON previews
are attached to their workbook and are not PDF previews for generic viewers.

Organization allowlisting remains deferred. The legacy Resources tree is absent
from active Weaver pages, so its new Swift persistence preference is not added to
the SQL model. Trace improvements retain existing observer and consent boundaries;
they do not grant new access to owner identity or contact details.
