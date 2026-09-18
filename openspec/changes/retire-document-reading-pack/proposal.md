## Why

Tracking: https://github.com/ThalesGroup/fred/issues/2732

The agent form's Simple capabilities view shows a standalone "Document reading"
pack whose only job is to opt into `document_verbatim` and `document_extract`.
That opt-in no longer matches how the product is used: exhaustive reading is
becoming the normal expectation for both corpus and attachment work, not an
advanced extra. Keeping it as a fourth card asks a non-technical user to reason
about reading strategy on top of *what* the agent may read — the exact framing
the pack model was introduced to remove.

Removing the card and folding its two capabilities into the two packs that
already grant document access reduces the Simple view by one concept and puts
the reading tools where the documents are.

## What Changes

- Delete the `document_reading` pack from `TOOL_PACK_SECTIONS`.
- Make `document_verbatim` and `document_extract` shared, resource-pack-owned
  capabilities: enabled when **either** "Team resources" or "Conversation
  attachments" is on, exactly like the existing `document_summarize`.
- Show the two reading capabilities in the expandable "included capabilities"
  list of both packs.
- **BREAKING (UI-level, no data migration):** in the Simple view there is no
  longer any way to enable verbatim reading or extraction without also granting
  document access. Existing agents are not migrated: their stored capability
  selection is untouched, and the Advanced view still toggles each capability
  individually. An agent that currently holds only the reading pair will keep
  it until someone toggles a resource pack in the Simple view, which recomputes
  the shared set.
- `document_similarity` stays corpus-only and is deliberately NOT added to the
  attachments pack: Knowledge Flow hardcodes `include_session_scope=False` for
  similarity search, so it can return nothing for a conversation attachment.
  Parity is deferred to a separate change that would have to alter that backend
  scope first.
- Update the French and English Help Center pages that name the retired pack.

## Capabilities

### New Capabilities
- `agent-capability-packs`: the Simple capabilities view's pack registry — which
  packs exist, what each one enables, how packs sharing a capability combine,
  and how a pack's on/off state is derived from the agent's stored capability
  selection.

### Modified Capabilities
<!-- None: no existing capability spec covers the agent form's pack registry. -->

## Impact

Frontend only — a presentation layer over the existing capability model. No
backend, API, database, or platform-admin "Features" change; the capability ids
themselves and their admin gating are untouched.

- `apps/frontend/src/rework/components/pages/TeamAgentsPage/AgentFormModal/toolPacks.ts`
  — remove the pack, move the two capability ids onto both resource packs.
- `apps/frontend/src/rework/components/pages/TeamAgentsPage/AgentFormModal/toolPackLogic.ts`
  — extend the resource-pack-owned set and its recomputation.
- `apps/frontend/src/rework/components/pages/TeamAgentsPage/AgentFormModal/toolPackLogic.test.ts`
  — drop the retired pack's cases, cover the new shared behaviour.
- `apps/frontend/src/locales/{fr,en}/translation.json` — delete the
  `packs.documentReading` keys.
- `apps/frontend/src/rework/features/helpCenter/content/{fr,en}/features/capabilities.md`
  — three passages name the retired pack (pack list, tool comparison, tip box).

No component change: `ToolPackCard` renders `pack.includes` generically.
