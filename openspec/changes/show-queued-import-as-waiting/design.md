## Context

`importPhaseStates` marks the phase in flight as `current` (spinner) unless the task failed, was cancelled, or waits on a conflict decision. The task's own state is otherwise ignored. A `pending` import task (outside a conflict) always means the browser transfer is done and the file waits for an ingestion worker slot: the frontend sets `pending` at hand-off (`uploadHandedOff`), the backend creates the task as `pending` and never writes it again once it has started.

## Goals / Non-Goals

**Goals:** One unambiguous signal per tile: a waiting file looks waiting in both the stepper and the status line.

**Non-Goals:** Showing a queue position or an estimate, changing worker concurrency, or the stuck-`running` tasks of a crashed worker.

## Decisions

- New `PhaseState` value `waiting`, rather than reusing `pending` (not reached yet) or `current` (under way): the phase is the next one, but nothing has started it.
- Only the phase in flight takes `waiting`; the phases before it stay `done`, the ones after it `pending`. The link feeding it takes its colour, as for `current`.
- `importPhaseLabel` returns "Waiting…" and `importPhaseHintFor` a dedicated hint for that state, so the status line and the stepper agree.
- Marker: the outlined `pending` icon in `--on-surface-retreat`, the same grey as the status line. The icon is added to `materialIcons`, which raises the packed UI archive's glyph count by one.

## Risks / Trade-offs

- A task rehydrated after a reload as `pending` shows `waiting`, which is accurate: the server only creates the task once it holds the file.
- If a future backend emitted `pending` after starting, the tile would read as waiting. The current backend never does.
