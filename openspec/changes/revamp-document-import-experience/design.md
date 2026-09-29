## Context

The pieces are already there, unconnected. The backend streams per-file,
per-step progress as NDJSON and `streamDocumentUpload.tsx` parses every line;
`DocumentUploadDrawer` wires only a Redux dispatch and an error toast, keeping a
single boolean for itself. `TaskTray` — trigger with an aggregate progress ring,
expandable panel, running and failed counts, per-task list — is built and
mounted nowhere. An SSE manager already streams live task updates, and
rehydration already re-registers non-terminal tasks on every page load.

This change connects them. It is deliberately frontend-only.

## Goals / Non-Goals

**Goals**

- Give the application back immediately.
- Make the two stages legible, because only the second decides usability.
- Make a failure survivable: visible, explained, retryable.

**Non-Goals**

- A new activity surface. RFC OPS-04 requires reusing existing components rather
  than one activity UI per feature; this change mounts and completes `TaskTray`.
- Fixing the task lifecycle (see Risks).
- Detecting conflicts and applying a decision (`add-import-conflict-resolution`); this change owns only where the user answers a conflict raised at write time.
- Server-side import latency (#2370, #2844, RFC §8).

## Decisions

### Mount `TaskTray` rather than build an import panel

It already matches the intended shape. Building a second surface would duplicate
it and contradict OPS-04. The work is mounting it in the layout, making sure
import tasks carry what the panel needs to show two stages, and finishing the
gaps found on the way.

### Close the dialog on acceptance, not on completion

Today the closing promise resolves only when every file of every batch has an
outcome. That guarantee exists so the drawer does not close while files are
unaccounted for — which is exactly the right concern, and the panel is the
correct answer to it. Once the panel owns per-file outcomes, the dialog no
longer needs to.

### The panel lists the user's own imports

A team-wide panel fills with other people's work on an active team. Team
activity stays where it is already visible: on the rows of the folder concerned.

### The panel adds to the rows, it does not replace them

A document row is the permanent home of that document's status. The panel is an
aggregated, always-reachable view of the same state, and a place to offer
actions later. No row indicator is removed by this change, and progress must not
be moved out of the table.

### Leave room for a state that is neither running nor failed

The panel's item model must not assume every item is running, done or failed —
one can be waiting on the user, as `add-import-conflict-resolution` will need
for a conflict detected at write time. Nothing here needs to understand
conflicts, but baking in a three-state assumption now would force that change to
rework the panel or invent a second surface.

### Cancellation stops at the upload stage

Stopping files not yet sent covers the common case — a wrong destination folder.
Cancelling an analysis in flight is a different capability: the server refuses
ingestion cancellation outright today, and the underlying support is being built
by `isolate-ingestion-extraction-queues`.

## Risks / Trade-offs

- **The panel is only as truthful as the lifecycle beneath it.** A task that
  never reaches a terminal state will show as running forever, and a failure
  reported as "Execution failed" has no cause to display. This change does not
  cause those defects, but it does make them visible, and it must not paper over
  them with a fake timeout in the UI. The lifecycle work is the agreed next
  piece; this change states the dependency rather than absorbing it.
- **Each non-terminal task holds one live stream.** With the panel mounted
  everywhere, stuck tasks cost more than they do today. This is an argument for
  the lifecycle work, not against the panel, but it should be watched.
- **Retry needs the file content.** The browser cannot re-read a file it no
  longer holds, so a retry after a reload may require re-selecting. The panel
  must say so rather than offering a retry that silently cannot work.
- **"Ready" must mean usable.** If the panel says ready while indexing is still
  catching up, it is worse than saying nothing. The ready signal must come from
  the same event that makes the document searchable.

## Migration Plan

None. No data, no API, no configuration changes.

## Open Questions

- How long do finished entries stay in the panel? `TaskTray` evicts on a timer
  today; whether import entries should survive a reload until acknowledged
  depends on OPS-04's acknowledgement model.
