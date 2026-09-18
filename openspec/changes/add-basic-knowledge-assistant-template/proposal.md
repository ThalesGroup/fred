## Why

Tracking: https://github.com/ThalesGroup/fred/issues/2750

Fred's agent templates can pre-select which capabilities a new instance starts
with, but not how those capabilities are configured. A template can tick
`document_access`; it cannot say "in corpus + attachments mode". Everything a
team member would otherwise have to set by hand after creating the agent stays
manual, which is the opposite of what a template is for.

That gap blocks the concrete goal: an almost off-the-shelf knowledge assistant a
user can create in one click and immediately ask about anything the team has
written down — in the corpus, in a conversation's attached files, or in the team
wiki — without first reasoning about which tools to tick.

The gap is not theoretical. `document_access` already defaults to corpus +
attachments (`show_attach_files_control=True`, `search_attachments_only=False`),
so a template pre-selecting it gets the right *runtime* behaviour. But the
creation form derives the "Conversation attachments" pack from an explicit
`show_attach_files_control === true` and reads an absent config slice as off. A
template therefore cannot make the form show what the agent will actually do —
only a seeded config can.

## What Changes

- Add `default_capabilities_config` to the agent template definition: a map of
  capability id → default config values, alongside the existing
  `default_mcp_servers` activation list. Activation stays where it is; this
  carries configuration only.
- Expose it on the template summary the runtime serves and the control-plane
  mirrors, and regenerate the frontend API client.
- Seed it in the agent-creation form next to `defaultCapabilitySelection`,
  narrowed through the same `can_use`-filtered advertised set, so a default for
  a capability the team cannot use is neither seeded nor submitted.
- Validate a template-declared default through the pod's own `validate_config`,
  the same path a member's submitted values take, so a malformed default fails
  where it is declared rather than lazily at agent assembly.
- Ship `fred.github.basic-knowledge-assistant`: a ReAct template defaulting to
  the capabilities behind four packs — team resources, team wiki, conversation
  attachments, Word generation — with `document_access` configured for corpus +
  attachments, reasoning offered and new conversations starting with it on, and
  a system prompt written for tool routing rather than tone.

Not breaking: existing instances each carry an explicit
`selected_capability_ids` list persisted at save time, so no stored agent
changes behaviour. Template defaults reach new instances only.

## Capabilities

### New Capabilities
- `agent-template-defaults`: what an agent template may declare as the starting
  point for a new instance — which capabilities are pre-selected, how they are
  pre-configured, and the reasoning posture — and the rules that keep those
  defaults a seed the member can change rather than a lock.

### Modified Capabilities
<!-- None: no existing capability spec covers agent template defaults. -->

## Impact

- `libs/fred-sdk/fred_sdk/contracts/models.py` — the new field on the agent
  definition models that already carry `default_mcp_servers`.
- `libs/fred-runtime/fred_runtime/app/agent_app.py` — project it onto the
  template summary next to `default_capability_ids`.
- `apps/control-plane-backend` — mirror the field on its template listing model.
- `apps/frontend/src/rework/components/pages/TeamAgentsPage/AgentFormModal/` —
  seed the form's `capabilityConfigValues` from it.
- `apps/frontend/src/slices/{runtime,controlPlane}/*OpenApi.ts` — regenerated,
  never hand-edited.
- `apps/fred-agents/fred_agents/basic_knowledge_assistant.py` (new) and
  `registry.py` — the template and its registration.
- `docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md` and
  `CONTROL-PLANE-PRODUCT-CONTRACT.md` — dated entries; both contracts describe
  the template summary.

Operational note, not a blocker: seven of the template's eight capabilities are
`ADMIN_GATED`, so granting it to a team goes through the dependency gate. The
"Enable all" flow shipped on 2026-08-28 grants them in one confirmation, so this
is one dialog rather than seven manual grants.
