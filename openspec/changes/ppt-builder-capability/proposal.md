## Why

Teams want an agent that produces a PowerPoint deck from a few instructions, on the blank corporate template their company hands out — or from nothing when they have none. The existing `ppt_filler` capability only fills a fixed deck whose slides carry `{{key}}` markers and notes; that annotation step is why the feature is not used. The new capability must work from a plain, unannotated template (GitHub issue #2679).

## What Changes

- A second capability, `ppt_builder`, shipped in the existing `fred-capability-ppt-filler` package (same pod install, same preview and delivery machinery). `ppt_filler` is unchanged.
- **Template analysis with zero annotation.** On upload, the capability inventories every usable _pattern_ of the template: master layouts (classified from their typed placeholders) and example slides from the deck body (typed placeholders kept from their layout, free text boxes classified by geometry, typography and sample text, repeated sibling groups detected as lists). Decoration, shared footers and logos are never touched. Slides with nothing to fill are _fixed_ slides the agent can include as-is; resource slides (icon banks, charts, tables) are excluded by default.
- **Closed intent vocabulary.** Every pattern maps to one intent (`title`, `section`, `agenda`, `content`, `two_columns`, `comparison`, `image_text`, `cards`, `steps`, `statement`, `contact`, `fixed`), with graceful degradation when a plan asks for an intent the template lacks.
- **Optional author review.** A config widget shows the inventory as a confirmation surface: thumbnails, detected intent, detected fields; the author can relabel a pattern, change its intent, exclude it, or change a zone's role. Nothing is mandatory — upload, read the summary, save is the nominal path. Only the analysis result and the author's overrides are persisted, never the template bytes.
- **Optional annotation channels** honoured when present: shape names set in PowerPoint's Selection pane, speaker-notes descriptions. Neither is required.
- **Generation** through a ReAct tool that takes a typed deck plan (ordered slides, each an intent-bearing pattern plus its content) and renders it by instantiating layouts or duplicating example slides and filling their zones — never adding free shapes, never leaving sample text behind, with computed overflow control. Image zones are filled from team folders or removed.
- **No template** → a neutral built-in theme covering every intent.
- **Delivery** reuses `ppt_filler`'s workspace write, PDF preview chat part, side pane and download.
- A new "Presentation builder" capability pack in the agent form's Simple view, next to the existing PowerPoint (filler) pack.

## Capabilities

### New Capabilities

- `ppt-builder`: generating a PowerPoint deck from a chat plan on an analysed corporate template or the built-in theme — template analysis, author review, plan rendering and delivery.

### Modified Capabilities

- none — `ppt_filler` keeps its contract; the preview chat part and side pane are reused, not changed.

## Impact

- `libs/fred-capability-ppt-filler/`: new `fred_capability_ppt_filler/builder/` subpackage, a second `fred.capabilities` entry point, a bundled default theme `.pptx`, new tests.
- `apps/frontend/src/rework/features/capabilities/ppt_builder/`: plugin, config widget (summary, pattern grid, pattern detail), pack options, generated API slice; `toolPacks.ts`, `AgentFormBody.tsx` (pack options), `index.ts` plugin list; `Makefile` target `update-ppt-builder-capability-api`; `locales/{en,fr}`.
- `docs/swift/ux/COMPONENT-UX.md` (config widget), `docs/swift/capabilities/AUTHORING.md` (worked-example row: two capabilities in one package sharing a chat part).
- Dependencies: none new — python-pptx, Pillow, LibreOffice conversion and react-pdf are already in place.
- Runtime cost: analysis and rendering are CPU-bound python-pptx work bounded by the package's existing per-pod heavy-job slots; no per-turn cost while the tool is not called.
