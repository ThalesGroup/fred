## Why

In the import panel, a file that has been transferred but not yet picked up by an ingestion worker shows a grey status line and a spinning marker on "Document preparation". The colour says it is waiting, the spinner says it is running. The ingestion worker runs a fixed number of files at a time, so on a batch import most tiles sit in this contradictory state.

Tracked by [GitHub issue #2885](https://github.com/ThalesGroup/fred/issues/2885).

## What Changes

- Add a `waiting` phase state to the import stepper: grey, with the Material Symbols `pending` icon, never a spinner.
- A `pending` import task outside a name conflict shows `waiting` on the phase it is about to start, and its status line reads "Waiting…" / "En attente…", with a hint that it starts as soon as a slot frees up.
- Once the worker reports the file as running, the tile behaves as today. The conflict case is unchanged.
- The Help Center Resources page (fr and en) mentions the waiting state.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `document-import-experience`: a file waiting for a worker is distinguished from a file whose phase is under way.

## Impact

- Frontend import phase model (`features/imports/importPhases.ts`), the `ImportStepper` and its styles, the import panel's status line, English and French translations, the icon list, the packed UI archive's glyph count, and the Help Center Resources page.
- No backend API, data model, or new dependency.
