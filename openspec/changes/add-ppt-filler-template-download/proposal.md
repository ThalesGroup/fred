# Download the PPT Filler template an agent already carries

Tracking: ThalesGroup/fred#2779

## Why

A PPT Filler agent is configured by uploading one `.pptx` template, which then
becomes the single source of truth for the fill: its placeholders define what
the agent may write, and its image folders decide where pictures come from. Once
saved, that file is unreachable. The options panel shows the template's name and
its per-slide schema, but nobody can get the file back.

That matters because the template is an authored artifact, not a setting. The
person who needs it next is rarely the person who uploaded it: someone taking
over an agent, checking why a placeholder is not filled, or preparing a variant
has to hunt for the original in a mailbox or a shared drive — and there is no way
to tell whether what they find is what the agent actually holds.

## What Changes

- **New "Download template" button in both option surfaces** — the Advanced
  view's `PptFillerConfigForm` and the Simple view's `PptFillerPackOptions`,
  which already share their upload logic through `usePptTemplateAnalysis`.
  - Disabled while no template is **saved**. The hook already computes that
    state (`hasPersistedTemplate`); no new data is fetched to decide it.
  - It offers only what is saved. A file just picked and not yet saved leaves
    the button on the previously saved template rather than silently offering
    a different file than the one the agent will use.
- **The download reads Knowledge Flow directly**, through the bearer-protected
  `/fs/download` route and the existing `downloadAuthed` helper — the same
  mechanism `PptxDownloadButton` already uses for the *generated* deck. KF
  gates agent-config assets on team membership, so **no new authorization rule
  is introduced** and the read is authorized against the caller's own identity.
- **`CapabilityConfigWidgetProps` gains the agent instance id.** It already
  carries `teamId`; the stored template's location needs both. Optional, like
  `teamId`: during creation there is no instance yet, which is exactly when the
  button must be disabled anyway.
- **The storage path convention gets one named home in the frontend**, beside
  the capability's API slice, with a test pinning its exact shape.

Out of scope, deliberately:

- **A route on the capability itself.** Capability routers are mounted on the
  pod as plain FastAPI routers with no platform services injected — `/analyze`
  works because it is stateless, and `writable_document`'s router works because
  it queries its own store. Reading a stored asset needs an instance-bound
  Knowledge Flow client, which today exists only inside a chat turn. Giving
  capability routes access to instance-scoped services is a new platform
  pattern and belongs in an RFC, not in this button.
- **Template versioning or history.** One template per instance is the
  capability's own convention (`PPT_FILLER_TEMPLATE_KEY` is a fixed key, and
  replacing the file swaps it). Keeping past templates is a different feature.
- **Preserving the uploaded file's original name.** It is not stored anywhere
  today (the asset is written under a fixed key), and storing it would change
  the capability's config model. The download is named after the agent instead —
  see `design.md`, decision 4.

## Capabilities

### New Capabilities

- `ppt-filler-template-download`: how the `.pptx` template stored on one PPT
  Filler agent instance is retrieved, who may retrieve it, and when the option
  is offered.

### Modified Capabilities

<!-- None. No existing capability spec covers the PPT Filler configuration
     surface; the capability's behavioral record lives in its module docstring
     and in AGENT-CAPABILITY's asset-port doctrine, neither of which changes. -->

## Impact

**Frontend**

- `features/capabilities/ppt_filler/PptFillerConfigForm.tsx` and
  `PptFillerPackOptions.tsx` — one shared button component each.
- `features/capabilities/ppt_filler/` — a new download helper holding the
  stored-asset path convention and the `downloadAuthed` call.
- `features/capabilities/types.ts` — `CapabilityConfigWidgetProps` gains the
  optional agent instance id, threaded from the agent form.
- Translation files: French and English labels.

**Capability and backends**

- None. No capability code, no pod route, no control-plane route, no generated
  client regeneration: the read uses an existing Knowledge Flow route with the
  caller's own token.

**Contracts and docs**

- No frozen contract changes. `AgentConfigAssetsAdapter`'s docstring gains one
  line naming the frontend helper that now mirrors its path convention, so the
  two are findable from each other.

**External**

- Knowledge Flow: reads an existing path through an existing route. No
  configuration change, no new endpoint.
