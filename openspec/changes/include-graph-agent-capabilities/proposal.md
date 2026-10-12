## Why

Tracking: no GitHub issue yet; create one before the PR.

A graph agent that declares a capability in `default_mcp_servers` (mindmap and
comparison in `apps/fred-agents`, Aegis in an external pod, all with
`document_access`) runs that capability, but the agent form says "This agent does
not support capability selection" and shows no way to configure it. The member
cannot see what the agent uses, nor bind it to libraries. The builtin
`knowledge.search` those agents call takes its scope only from the client's
`RuntimeContext`, so a run without the chat UI (an evaluator run, an API client)
ignores any binding.

## What Changes

- **Template contract (runtime, control plane):** for a definition with
  `supports_capabilities=False`, `available_capabilities` lists the catalog
  entries of its defaults instead of `[]`. `supports_capabilities=False` marks
  them as included: always active, configurable, never selectable. No new field.
- **Save (control plane):** create and update ignore a submitted
  `capability_ids` for such a template and take the existing template-default
  path, so each included capability's config is validated by the pod
  (`validate-config`) and stored in `tuning.capability_config`.
- **Form (frontend):** Simple and Advanced list the included capabilities as
  cards with an "Included" badge instead of a switch, each with its config form
  (`DocumentAccessPackOptions` for library binding in Simple,
  `CapabilityConfigForm` otherwise). A neutral line replaces "not supported" for
  an agent that includes nothing.
- **`knowledge.search` (runtime):** the instance's bound libraries, read from
  the `document_scope` chat control its active capabilities compute from their
  stored config, are a ceiling on the turn's library selection, whatever the
  client sends.
- **Document search and tree ports (runtime):** an empty scope, passed by the
  capability or left by intersecting it with the session's selection, selects
  nothing instead of reaching Knowledge Flow as no filter; explicitly picked
  documents are still searched, since libraries and documents union.

Out of scope: graph nodes consuming capability-provided tools, merging
`knowledge.search` with the `document_access` tool, the general agent scope
ceiling of `CAPABILITY-SCOPE-CEILING-RFC.md`.

## Capabilities

### Modified Capabilities

- `agent-capability-packs`: included capabilities of an agent without free
  selection, and the server-side library binding of `knowledge.search`.

## Impact

`fred_runtime/app/agent_app.py`, `fred_runtime/capabilities/assembly.py`,
`fred_runtime/integrations/v2_runtime/adapters.py`,
`control_plane_backend/product/{schemas,service}.py`, the regenerated
`controlPlaneOpenApi.ts` (descriptions only), the agent form under
`TeamAgentsPage/AgentFormModal/`, translations, the Help Center capabilities page,
both contract docs, `COMPONENT-UX.md`, the agent authoring guide and the
migration note `graph-agent-included-capabilities.md`.
