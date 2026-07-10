# HANDOFF — #1977 chat parts (branch `feat/capab-1977-chat-parts`)

State at handoff: **all four acceptance criteria implemented, tested, green.**
No red tests. Work stopped on coordinator budget cut before the final docs
commit and root-level quality run.

## (a) DONE and verified

Commits (on top of `feat/agent-capability-1961` @ 7f1ec17e8):

1. `d29ed0ed6` feat(CAPAB-01): build UiPart union from registered capability chat parts
   - `libs/fred-sdk/fred_sdk/contracts/ui_part_union.py` (NEW):
     `rebuild_ui_part_union(extra)` = base(link,geo)+extras; swaps the alias in
     every importing module's globals, rewrites resolved `FieldInfo.annotation`
     objects (pydantic does NOT re-evaluate on `model_rebuild(force=True)` —
     verified empirically), topo-sorts affected models (children first, via
     `BaseModel.__subclasses__` walk + embeds-propagation) and force-rebuilds.
     `current_ui_part_union()` for lazily-built validators. No-op short-circuit
     when membership unchanged. Exported from `fred_sdk.contracts.__init__`.
   - `openai_compat._extract_ui_parts` now validates against the current union
     via cached-on-union-identity TypeAdapter (unknown kinds skipped) — the
     hand-listed link/geo switch is gone.
   - Tests: `libs/fred-sdk/tests/test_ui_part_union_1977.py` (13 tests).
     Full fred-sdk suite: 220 passed. ruff + basedpyright clean on touched files.

2. `8480c911c` feat(CAPAB-01): register capability chat parts on the UiPart union at boot
   - `registry.py`: `chat_parts()` (deterministic: sorted cap ids, manifest
     order); `validate()` calls `rebuild_ui_part_union(self.chat_parts())` at
     the end; `BUILTIN_CHAT_PART_KINDS` now derived from `BASE_UI_PARTS`.
   - `agent_app.py`: `boot_capability_registry()` moved lifespan → app
     CONSTRUCTION (before routes capture schemas ⇒ offline
     `generate_openapi.py`, which never runs lifespan, includes capability
     parts). `app.state.capability_registry` set at construction. Module-level
     `_EXECUTE_RESPONSE_ADAPTER` replaced by `_execute_response_adapter()`
     (cached, refreshed on union identity change).
   - `demo.py`: `DemoCardPart` (type "demo_card", title, body);
     `manifest.chat_parts=[DemoCardPart]`; `demo_echo` tool is now
     `response_format="content_and_artifact"` returning
     `(text, ToolInvocationResult(ui_parts=(DemoCardPart(...),)))` — with a
     documented `cast(UiPart, ...)` (reference pattern; static alias is the
     frozen base, runtime union is extended).
   - `libs/fred-runtime/pyproject.toml`: `[project.entry-points."fred.capabilities"]
     demo_echo = ...` — installing IS the registration.
   - Tests: `tests/test_capability_chat_parts_1977.py` (5, incl. OpenAPI
     document contains DemoCardPart with zero hand edits); conftest autouse
     fixture restores base union per test; 1973 tests updated (boot test now
     expects demo_echo discovered; defaults test adds `registry.validate()`).
     Full fred-runtime suite: 468 passed. ruff/format/basedpyright clean.

3. `f106deadd` feat(CAPAB-01): part-renderer registry and raw uiParts on ThreadMessage
   - `ThreadMessage.links: LinkPart[]` → `uiParts: RawUiPart[]`
     (`src/rework/types/parts.ts` NEW: `{type: string; [k]: unknown}`).
   - `toThreadMessages` extracted from `useManagedChat.ts` to
     `.../ManagedChatPage/toThreadMessages.ts` (pure, tested); `linksOf`
     replaced by `uiPartsOf` in `traceUtils.ts` (exclusion set of the 7
     message-body kinds ⇒ unknown kinds retained).
   - `src/rework/features/capabilities/`: `types.ts` (`CapabilityUiPlugin` —
     `partRenderers` typed; configWidgets/chatTurnControls/sidePanels loose,
     typed by their host slices later), `index.ts` (THE plugin index),
     `partRendererRegistry.ts` (builtins+plugins, first-wins + console.warn on
     duplicate — backend fails boot on real dupes), `builtinPartRenderers.tsx`
     (link → `ArtifactLinkChip` extracted from ArtifactLinks; geo → NEW summary
     chip, geo was silently dropped before), `demo_echo/plugin.ts` +
     `DemoCardPartRenderer.tsx` (+css).
   - `UiParts` molecule (shared/molecules/UiParts) dispatches via registry,
     skips unknown kinds; `AssistantTurn` prop `links` → `uiParts`, renders
     `<UiParts/>`; `ConversationThread` passes `msg.uiParts`.
   - `runtimeOpenApi.ts` regenerated (`make update-runtime-api`) — includes
     `DemoCardPart`, 11 generated lines, zero hand edits. i18n keys added
     (en+fr): `chatbot.uiParts.*`, `capability.demo_echo.cardAria`.
     `IconType` extended with `"map"`, `"graphic_eq"`.
   - `docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md`: UiPart extension rule +
     dated §8.13 entry (rode along in this commit).
   - Tests: `toThreadMessages.test.ts` (4), `partRendererRegistry.test.tsx`
     (4), `UiParts.test.tsx` (6), `AssistantTurn.test.tsx` (3). Full frontend:
     311 passed; `make code-quality` (tsc+prettier) green.

Acceptance criteria mapping: (1) demo part in regenerated OpenAPI/types with no
hand edits — `test_openapi_includes_demo_capability_part_with_no_hand_edits` +
regenerated `runtimeOpenApi.ts`; (2) uniform dispatch link/geo/capability —
registry tests; (3) unknown parts retained end-to-end, skip-not-drop —
toThreadMessages + UiParts + AssistantTurn tests; (4) demo tool emits → card
inline — `test_demo_tool_emits_demo_card_part_as_artifact` (backend emit) +
AssistantTurn inline test (frontend).

## (b) IN PROGRESS

Nothing broken. Only the RFC as-implemented note was being written when work
stopped (see (e)).

## (c) NOT STARTED

- RFC `docs/swift/rfc/AGENT-CAPABILITY-RFC.md` as-implemented note (#1977).
- Root `make code-quality` (per-module gates all green; root run not done).
- `apps/fred-agents` test suite not re-run after the `create_agent_app`
  boot-timing change (fred-runtime's own 468 tests cover the factory; low risk).
- Optional live-stack browser check of the inline card (component tests cover it).

## (d) Design decisions (do not re-derive)

- Union extension = alias swap + in-place annotation rewrite + topo rebuild;
  `model_rebuild(force=True)` alone does NOT pick up a swapped module global
  (pydantic 2.13 resolves annotations at class creation) — tested.
- Union is rebuilt from base+extras every time (never cumulative);
  `rebuild_ui_part_union(())` restores the frozen contract (tests rely on it).
- Boot at app construction (deviation from #1973's lifespan placement) is what
  makes offline OpenAPI export correct; failure is still "pod startup aborts".
- Validators must resolve the union lazily (`current_ui_part_union()` identity
  as cache key) — pattern used in agent_app and openai_compat.
- Frontend: unknown-kind policy is skip-at-render, retain-in-data; duplicate
  renderer kind = first-wins + warn (backend boot failure is the real guard).
- `uiPartsOf` uses an exclusion set of message-body kinds — intentionally open
  so future backend kinds flow through without frontend edits.

## (e) Exact next step

Append to `docs/swift/rfc/AGENT-CAPABILITY-RFC.md` (blockquote, same pattern as
the three "As implemented (2026-07-10, #1973 …)" notes at lines 142/517/704 —
put it after the §4 note at ~line 530) recording: (1) boot moved to
create_agent_app construction and why; (2) `rebuild_ui_part_union` mechanism in
fred-sdk `contracts/ui_part_union.py`; (3) geo got a builtin summary-chip
renderer (RFC assumed geo rendered; it didn't); (4) plugin index ships with
`partRenderers` typed and the other three slots typed loosely pending #1974+;
(5) `cast(UiPart, ...)` emission pattern. Commit as
`docs: record #1977 as-implemented chat-part decisions in AGENT-CAPABILITY-RFC`.
Then root `make code-quality`, then done.

## (f) Conflict points with #1974

- `libs/fred-runtime/fred_runtime/capabilities/demo.py` — #1974 likely touches
  the demo capability (catalog/tuning). My changes: DemoCardPart class,
  manifest `chat_parts`, tool signature (content_and_artifact tuple return).
- `libs/fred-runtime/pyproject.toml` — the `fred.capabilities` entry point;
  #1974 may add the same one. Keep ONE.
- `libs/fred-runtime/fred_runtime/app/agent_app.py` — registry boot moved to
  construction; if #1974 reads `app.state.capability_registry` in lifespan it
  still works (set before lifespan runs).
- `src/rework/features/capabilities/{types,index}.ts` — if #1974 also creates a
  plugin index, merge into THIS one (RFC mandates a single index);
  `CapabilityUiPlugin` here deliberately leaves configWidgets/chatTurnControls/
  sidePanels loosely typed for #1974 to tighten.
- Generated files (`runtimeOpenApi.ts`, `controlPlaneOpenApi.ts`): regenerate
  at integration, never hand-merge.
- `tests/test_capability_registry_1973.py`: boot test now expects `demo_echo`
  discovered (entry point installed) — #1974 may collide on the same test.
