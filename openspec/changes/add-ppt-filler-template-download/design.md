# Design — Download the PPT Filler template an agent already carries

## Context

See `proposal.md` — Why. Four facts about the existing code shape this design.

**The bytes are already reachable from a browser.** The template is stored in
Knowledge Flow under `teams/{team}/agents/{agent_instance_id}/config/{key}`,
written by `AgentConfigAssetsAdapter` on save. KF gates agent-config reads on
team membership, and `PptxDownloadButton` already downloads a *generated* deck
from a bearer-protected `/fs/download` URL through `downloadAuthed`. Nothing has
to be built for the transport or the authorization.

**Capability routers cannot read stored state.** They are mounted on the pod
under `/capabilities/{id}` as plain FastAPI routers with no platform services
injected. `ppt_filler`'s `/analyze` works because it is stateless — the file
arrives in the request. `writable_document`'s router works because it queries
its own capability-local store. An instance-bound Knowledge Flow client exists
only inside a chat turn (`ctx.services.agent_assets`), and the client itself
lives in `fred-runtime`, which a capability package does not depend on.

**The control plane has no filesystem access to Knowledge Flow at all.** It
mediates the save (multipart → the pod's `validate_config`) but never touches
`/fs`. Serving the download from there would mean giving it that access.

**The disabled state already exists.** `usePptTemplateAnalysis`, shared by both
option surfaces, computes `hasPersistedTemplate`.

## Goals / Non-Goals

**Goals:**

- Retrieve the saved template from the place it was uploaded, using only
  mechanisms already proven in this codebase.
- Introduce no authorization rule: the caller's own identity does the reading.
- Keep the two option surfaces behaving identically, without a second
  implementation.

**Non-Goals:**

- A capability-owned or platform-owned download route (see decision 1).
- Any change to what is stored: no new config field, no second asset, no
  original-filename capture.
- Making other capabilities' config assets downloadable.

## Decisions

### 1. The browser reads Knowledge Flow directly — **confirmed with the developer**

**This reverses a recommendation made earlier in the discussion.** A route on
the capability was proposed first, by analogy with `/analyze`. The analogy does
not hold: `/analyze` is stateless, and a route that must read a stored asset
needs instance-scoped platform services that capability routers are not given.
Recorded rather than quietly dropped, because the analogy is tempting and the
next person may reach for it too.

The three alternatives, and why they lose:

- *A route on the capability.* Would require giving capability routes access to
  instance-scoped services — a new platform pattern, reusable and arguably the
  right long-term shape, but an RFC and a scope out of all proportion with one
  button. Deferred, not rejected on merit.
- *A route on the control plane.* It has neither KF filesystem access nor a
  reason to gain it; adding that for one download widens its surface toward
  serving capability assets generally, which this change explicitly avoids.
- *Serving the template through the pod at turn time.* Would make a
  configuration action depend on starting a conversation.

### 2. The path convention gets exactly one home in the frontend

Reading `teams/{team}/agents/{instance}/config/{key}` from the browser mirrors a
server-side convention that the SDK deliberately keeps private — a capability
names a slot-relative key and never a path. That duplication is the real cost of
decision 1, and it is paid once, visibly: one named helper beside the
capability's API slice, and the SAME literal pinned on both sides — a Python
test over `_config_path` and the helper's own test — so changing either side
alone fails a suite. A frontend-only assertion would have been self-referential:
it would compare the mirror to itself and notice nothing.

*Rejected:* building the path inline at the two call sites. Same cost, spread
over two places, discoverable from neither.

*Accepted consequence:* if the server-side path ever changes, the download 404s
until the helper follows. The paired tests make that break loud in a suite
rather than silent in the browser.

The path also carries an alias trap the repo already documents on
`personalTeamId`: the personal space is ROUTED as the bare `personal` but STORED
under `personal-<uid>`, so the helper canonicalizes before building the path.
Without it the feature would have been dead in the personal space — enabled
button, 404 on click — and every test would still have passed, because they all
name a real team.

Only the BARE alias is rewritten, as the repo's two other `/fs` call sites do.
The first fix used `isPersonalTeamId`, which also matches an already-canonical
`personal-<uid>` and therefore discarded a correct id to re-derive it from the
session — wrong for a caller whose uid differs from the id, and `personal-` if
the uid were ever unavailable. Its test could not catch it: the mocked uid
matched the id under test, so "passed through" and "rebuilt" produced the same
string. The test now uses a deliberately different uid.

### 3. The agent instance id reaches the widget as an optional prop

`CapabilityConfigWidgetProps` already carries `teamId` for exactly this kind of
lookup; the instance id joins it, optional for the same reason `teamId` is: the
widget also renders while an agent is being *created*, where no instance exists.
That is precisely when nothing is saved and the button must be disabled anyway,
so the missing value and the disabled state coincide instead of needing to be
reconciled.

### 4. The download is named after the agent, not after the uploaded file

The original filename is not stored anywhere: the asset is written under the
fixed key `ppt_filler_template.pptx`, and `PptFillerConfig` keeps only
`schema_slides` and `template_key`. Downloading would otherwise always produce
`ppt_filler_template.pptx`, identical for every agent — unhelpful the moment
someone downloads two.

The button names the file after the agent instance, which the form already
knows. Capturing the original filename at upload would mean a new config field
and a migration for existing instances, for a cosmetic gain.

### 5. One button component, used by both surfaces

The two surfaces already share `usePptTemplateAnalysis`; the button follows the
same rule. A second implementation would be where the two surfaces start
drifting — which is the whole reason the upload logic was shared in the first
place.

## Risks / Trade-offs

- **A server-side convention now also lives in the browser.** → Confined to one
  named, tested helper (decision 2), and cross-referenced from the adapter that
  owns the original.

- **A failed download is indistinguishable from a missing file.** KF's refusal
  and a network failure both surface as "it did not work". → The button reports
  a generic failure rather than guessing a cause, per the spec's last
  requirement. Guessing would be worse than saying less.

- **The button's enabled state reads stored CONFIG, not the stored file.**
  `hasPersistedTemplate` is `schema_slides.length > 0`, which lives in Postgres,
  while the `.pptx` lives in the object store. They come apart in a routine
  action, not only in a disaster: **duplicating an agent** copies the capability
  config, so the copy inherits the slide schema while the bytes stay with the
  original (the pod's save path passes a no-upload edit straight through). An
  export/reset/import cycle does the same. → The button stays enabled, and the
  failure says what actually happened — "the template file is missing for this
  agent, upload it again" — instead of a generic download failure. Probing the
  object store on every render of the options panel would buy a disabled button
  at the cost of a request per open; the named message is the cheaper honest
  answer. Revisit if duplication turns out to be common enough to confuse
  people.

- **A staged, unsaved file sits next to a button that offers the SAVED one.**
  The chip shows the new file's name; the button hands back the previous
  template. → Deliberate (decision 4 of the proposal's scope), but nothing on
  screen distinguishes them. The button's own title says which one it offers;
  a clearer affordance is worth revisiting if anyone is actually confused.

- **The deferred platform extension may make this work look redundant later.**
  If capability routes ever gain instance-scoped services, this download would
  be a natural first consumer and the helper would be deleted. → Acceptable: the
  helper is small and its deletion would be mechanical. Building the platform
  extension first would block a button on an RFC.

## Migration Plan

One deployment, frontend only. No data migration, no contract change, no
Knowledge Flow configuration. Rollback is a revert; nothing is persisted.

## Open Questions

None. The two decisions that could have changed the approach — where the read
happens, and what the button offers when a file is staged but unsaved — were
both settled with the developer before this document was written.
