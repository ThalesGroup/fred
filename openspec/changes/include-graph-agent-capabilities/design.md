## Context

`GraphAgentDefinition.supports_capabilities` defaults to False: no free
selection, because graph nodes do not consume capability tools. The runtime
already activates `default_mcp_servers` for such a definition and reads
`tuning.capability_config` for them (`_effective_capability_ids`,
`_build_capability_block`). Only the template listing (`available_capabilities
= []`) and the form hid them. The control plane's default path narrowed the
defaults to `available_capabilities`, so it stored `selected_capability_ids: []`
and no config, and session prep resolved no chat controls.

## Decisions

### D1. Contract: `available_capabilities` restricted to the included defaults

Chosen over a new `included_capabilities` field. `supports_capabilities=False`
already exists, unfiltered by team grants, and becomes the marker. Every consumer
of `available_capabilities` (team `can_use` filter, version map for chat
controls, suspension checks, the form's capability base URLs) then works for
included capabilities without a parallel path. The listing keeps the
execution-model filter (`_template_capability_entries`).

### D2. One rule for "no free selection", applied where the selection is read

The runtime already ignores a saved selection for such a definition. The control
plane now does the same in `_apply_capability_selection` (`selected_ids = None`),
which reuses its default path: ReBAC narrowing of the defaults, pod validation of
each slice, persistence of the effective ids. A template whose defaults are all
unusable by the team is refused with the existing 422. The form submits every
advertised (included) id with its config (`activeCapabilityIds`), so a stale or
empty stored selection never drops a config.

### D3. Binding source: the capability's own `document_scope` chat control

`resolve_bound_library_ids` evaluates each active capability's chat controls
from its stored config and collects `document_scope.bound_library_ids`. That is
the descriptor the composer already pins its picker from, and the place where
`document_access` decides what "bound" means (`bind_libraries`, `team_documents`,
`library_tag_ids`). fred-runtime imports no capability package, and a second copy
of that decision would drift. The MCP search capability's binding is read the
same way.

### D4. Narrowing: the existing `_narrow_scope_ids`

`knowledge.search` narrows the turn's library selection by the bound libraries
with `_narrow_scope_ids`, the primitive `DocumentSearchAdapter` uses. An empty
intersection returns no hits: `VectorSearchClient` drops an empty filter, so it
must never reach the search. Document picks are not narrowed, as in
`document_access`, where libraries and documents union.

### D5. An empty scope finds nothing, at the port seam

Found while doing D4: `DocumentSearchAdapter` and `DocumentTreeAdapter` sent an
empty intersection on, and `VectorSearchClient` / the tree drop an empty filter.
Two ways reach it with `document_access`: the turn's `turn_options` disjoint from
the bound libraries (the capability passes `[]`, which the adapter read as "no
narrowing"), or the `RuntimeContext` selection disjoint from them. Both searched
the session's selection or the whole corpus. The adapters now treat an empty
scope as selecting nothing on its side, as `DocumentSimilarityAdapter` already
refuses one, and the port docstrings say `[]` means nothing in scope. Knowledge
Flow unions libraries and documents, so an empty library scope still leaves the
picked documents: the call stops only when neither side selects anything
(`_matches_nothing`), and the builtin `knowledge.search` applies the same test.
One owner, no capability-side guard.

## Risks / Trade-offs

- Instances saved before this change keep `selected_capability_ids: []`, so their
  chat shows no capability controls until edited and saved once. No backfill: the
  runtime behaviour of those instances does not change.
- This is a ceiling for one port, the kind CAPAB-SCOPE-01 wants generalized. That
  RFC stays open; this change does not preempt its descriptor design.
