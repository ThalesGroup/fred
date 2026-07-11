# HANDOFF — #1976 chat-time controls + typed turn options (CAPAB-01)

Branch: `feat/capab-1976-chat-controls`. RFC §3.3/§3.5/§3.7/§9.

## DONE + GREEN (committed & pushed)
- **Backend** (commit `feat(CAPAB-01): compute chat controls + typed turn options; retire chat-options`):
  - fred-sdk: `contracts/capability/chat_controls.py` (request/response wire), `manifest.py` `ChatControlItem`/`ChatControlDescriptor`, `execution.py` `turn_options`. Fixed `ChatControlsResult.manifest_version` min_length bug (error results carry `""`). **223 tests, code-quality clean.**
  - fred-runtime: `capabilities/assembly.py` `evaluate_chat_controls_batch` + `validate_turn_options`; `mcp.py` `McpCapability.chat_controls`; `agent_app.py` `POST /agents/capabilities/chat-controls` + `_enforce_turn_options` (422) on all execute paths; `errors.TurnOptionsInvalidError`. New test file `tests/test_capability_chat_controls_1976.py` (+10). **508 tests, code-quality clean.** runtime openapi.json regenerated (gitignored build artifact).
  - control-plane: `product/service.py` `_resolve_chat_controls` wired into `prepare_execution`; `_available_capabilities_for_source`; cache-aside LRU `_chat_controls_cache` keyed `(capability_id, manifest.version, config_hash)`. Removed `EffectiveChatOptions`, `_resolve_effective_chat_options`, `_mcp_field_defaults_*`, `_as_bool`, `chat_options.*` constants. `schemas.py`: dropped `EffectiveChatOptions`, removed the field from `ManagedAgentInstanceSummary`, added `chat_controls` to `ExecutionPreparation`. `tests/test_main.py`: replaced 3 old resolution tests with 4 orchestration tests (attach/cache/error-skip/unreachable). openapi.json regenerated. **250 tests, code-quality clean.**
  - Fable design calls applied: (Q1b) `ManagedAgentInstanceSummary.effective_chat_options` DROPPED (composer uses eager prepare-execution at chat open); (Q2) per-item `StoredCapabilityConfig.model_validate` try/except so a bad envelope skips one capability not the whole prep; copy-on-get for cached items; corrected `_fetch_chat_controls` silent-degrade docstring.
- **Docs** (commit `docs(CAPAB-01): ...`): RFC §3.7 as-implemented note; CHAT-UI-BACKLOG §3.4 marked SUPERSEDED; CONTROL-PLANE-PRODUCT-CONTRACT dated removal; RUNTIME-EXECUTION-CONTRACT §8.14.

## prepare_execution seam (for #1975 hand-merge)
My ONLY edit inside `prepare_execution` is a contained block placed AFTER the
`capability_base_urls` dict and immediately BEFORE the `return ExecutionPreparation(...)`:
```
available_capabilities = await _available_capabilities_for_source(source.base_url)
chat_controls = await _resolve_chat_controls(instance.tuning, available_capabilities, source.base_url)
```
plus the return arg changed `effective_chat_options=_resolve_effective_chat_options(...)` → `chat_controls=chat_controls`. I did NOT modify `_resolve_effective_chat_options` (it is deleted). No suspended-instance guard touched — #1975's guard slots in cleanly at the top of the function.

## IN PROGRESS — frontend (delegated to a sonnet sub-agent)
Regenerate `controlPlaneOpenApi.ts` + `runtimeOpenApi.ts`; build the composer
control slot (`features/capabilities/` chatTurnControlRegistry + host mirroring
sidePanelRegistry/CapabilitySidePanelHost) + stock kit extracted from
`SearchConfig` (enum/toggle/action rows); dynamic `mcp:<id>` widgets resolve via
a capability-agnostic stock-kit fallback registry (MCP ids are dynamic).
Rewire `useChatSse` / `useManagedChat` (eager prep at chat open) /
`useComposerSettings` (seed defaults from `search_policy`/`rag_scope` descriptor
params) / `ManagedChatPage`. Thread `turn_options` into the execute body.
Target: `make code-quality` + `make test` GREEN in apps/frontend.

## NOT STARTED / NEXT STEP if resuming
1. Verify the frontend sub-agent's output: `cd apps/frontend && make code-quality && make test`.
2. Commit frontend as `feat(CAPAB-01): composer control slot + stock kit; consume chat_controls, send turn_options (#1976)` (no AI trailers).
3. Push. Final history = 3 clean commits on top of `cd9ae992`.
