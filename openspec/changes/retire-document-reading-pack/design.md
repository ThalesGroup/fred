## Context

See proposal.md — Why.

The Simple view is a front-only presentation layer over the agent form's stored
capability selection. Two mechanisms already exist in it and this change reuses
both rather than adding a third:

- **Plain packs** own a fixed list of capability ids; toggling adds or removes
  exactly those ids.
- **Document-access packs** ("Team resources" = corpus intent, "Conversation
  attachments" = attachments intent) do not own their ids outright. They declare
  an intent, and a single function recomputes the whole set of
  resource-pack-owned capabilities from the resulting (corpus, attachments)
  pair. That indirection exists because both packs contribute to one shared
  `document_access` config, and because `document_summarize` is already granted
  by both and must not be dropped while one pack still needs it.

The retired pack is a plain pack. Its two capabilities move into the second
mechanism, which is exactly the shape needed for "on when either pack is on".

## Goals / Non-Goals

**Goals:**

- One fewer concept in the Simple view, with no new abstraction introduced.
- Reading capabilities follow the same shared-ownership path as
  `document_summarize`, so there is one recomputation rule, not two.
- Pack cards report everything they grant, including what was previously
  granted silently.

**Non-Goals:**

- No migration of existing agents' stored selections (see Risks).
- No change to the Advanced view, which keeps one toggle per capability.
- No backend, API, or admin-gating change.
- No attachment support for similarity search — that needs a Knowledge Flow
  scope change and belongs to its own slice.

## Decisions

**Make the reading pair resource-pack-owned rather than listing it on both
packs as plain ids.** Listing the same ids in two plain packs would mean
switching either pack off removes them even while the other is still on —
the bug the shared-ownership mechanism was built to avoid. Adding them to the
recomputed set and enabling them on `corpus || attachments` mirrors
`document_summarize` exactly. Alternative considered and rejected: a
pack-level "shared ids" concept, which would add a third mechanism to express
something the existing one already expresses.

**Keep pack on/off derivation unchanged.** The two document-access packs remain
derived from the `document_access` config (corpus reachable / attach-files
shown), not from the presence of the reading capabilities. Deriving from the
reading pair would make the switch flicker off when someone clears one of them
in the Advanced view, which is not what the switch means.

**Keep `document_access` out of the attachments pack's included list.** It was
omitted deliberately when the pack was introduced and stays omitted: the card
presents attaching files as the feature, and listing the capability that
implements it would describe plumbing rather than an ability the agent gains.
The reading tools are listed because they ARE distinct abilities. Alternative
considered and rejected: listing it for symmetry with the team-resources card,
which would make the attachments card read as a capability inventory instead of
a feature.

**Leave similarity search corpus-only.** Knowledge Flow's similarity search
hardcodes `include_session_scope=False`, so it can never match a conversation
attachment. Granting it to an attachments-only agent would add an inert tool to
the model's toolset and, on a conversation with a corpus selection, produce a
scope refusal that reads to the user as "the file you just attached is
unreachable". Deferred to a separate change.

## Risks / Trade-offs

**Existing agents holding only the reading pair lose it on the first Simple-view
pack toggle** → Accepted by the developer. Their stored selection is untouched
until someone toggles a document-access pack, at which point the recomputation
drops ids no pack grants. The Advanced view remains the way to restore them.
No data migration is run, so nothing changes for agents nobody edits.

**Exhaustive extraction becomes enabled by default for every document-access
agent** → Accepted: extraction is the most expensive reading tool, and it now
turns on without a separate opt-in. This is the explicit intent of the change —
exhaustive reading is becoming the expected behaviour — but it does raise the
per-turn tool budget for agents that previously had search only.

**The two packs' included lists diverge (similarity in one, not the other)** →
Accepted and specified, so a later reader does not "fix" it by adding
similarity to the attachments pack. The spec states the reason.

## Migration Plan

None. Frontend-only; a deploy of the frontend is the whole rollout, and
reverting the commit fully restores the previous view. No stored agent data is
read or written by this change.
