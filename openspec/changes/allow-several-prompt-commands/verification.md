## Contract and runtime part (groups 1 to 3, task 7.3)

Run on 2026-10-13, branch `feat/composer-command-menu-sections`, with each
project's own `.venv` and no `make` target. The frontend behaviour (groups 4 to
6) is not built yet: nothing sends the list.

### Python

Commands, in each project: `VIRTUAL_ENV= .venv/bin/pytest -q -p no:cacheprovider
-m "not integration" --disable-socket --allow-unix-socket`, `.venv/bin/ruff
check .`, `.venv/bin/ruff check --select I .`, `.venv/bin/ruff format --check
.`, `.venv/bin/basedpyright --baseline-file .baseline/basedpyright-baseline.json`.

| Project | pytest | ruff check | import order | format | basedpyright |
| --- | --- | --- | --- | --- | --- |
| `libs/fred-sdk` | 647 passed, 3 skipped | passed | passed | 97 files formatted | 0 errors, 0 warnings |
| `libs/fred-core` | 1267 passed, 1 skipped, 42 deselected | passed | passed | 284 files formatted | 0 errors, 0 warnings |
| `libs/fred-runtime` | 2115 passed, 11 skipped, 22 deselected | passed | passed | 262 files formatted | 0 errors, 5 warnings |

The 5 basedpyright warnings of fred-runtime are in files this change does not
touch (none in `tests/test_turn_command_descriptor.py`).

Tests added: 13 cases in `libs/fred-sdk/tests/test_context.py` (5 functions,
two parametrised), 4 in `fred_core/tests/history/test_history_schema.py`, 2 in
`fred_core/tests/history/test_history_store_ui_parts_round_trip.py`, 4 in
`libs/fred-runtime/tests/test_turn_command_descriptor.py`.

Proven by tests:

- a descriptor without `prompts` validates and dumps as before, on both models;
- 1 and 16 entries validate and survive `RuntimeContext.model_dump(exclude_none=True)`;
- an empty list, 17 entries, a negative offset, a zero `text_length`, an empty
  command, an entry without its positions and a non-list are refused by
  `RuntimeContext`;
- an unknown key inside an entry is ignored by fred-sdk and kept by fred-core;
- offsets are not measured against any text;
- a two-entry descriptor round-trips through `ChatMetadata` and through a
  save and read of the history store;
- a stored list over the bound reads back with empty metadata, no exception,
  and the turn's text intact;
- a dumped `RuntimeContext` listing two prompts gives a `CommandDescriptor`
  with the same entries and the single fields of the first;
- a malformed or 17-entry list on the internal context drops the whole
  descriptor;
- `TurnCommand` and `CommandDescriptor` give the same verdict on 16 and on 17
  entries;
- `_write_turn_history` stores the request text unchanged (surrounding
  whitespace, an emoji, accents) next to a descriptor that lists a prompt.

`agent_app.py` is unchanged.

### Generated files

| Command | Result |
| --- | --- |
| `cd libs/fred-runtime && .venv/bin/python scripts/generate_openapi.py` | `openapi.json` rewritten (ignored by git) |
| `cd apps/frontend && npx --no-install @rtk-query/codegen-openapi src/slices/runtime/runtimeOpenApiConfig.json` | `runtimeOpenApi.ts`: 19 lines added, none removed |
| `cd apps/control-plane-backend && .venv/bin/python ../../scripts/generate_openapi.py control_plane_backend`, then codegen with `controlPlaneOpenApiConfig.json` | `controlPlaneOpenApi.ts` unchanged |
| `cd apps/knowledge-flow-backend && .venv/bin/python ../../scripts/generate_openapi.py knowledge_flow_backend`, then codegen with `knowledgeFlowOpenApiConfig.json` | `knowledgeFlowOpenApi.ts` unchanged |

The `runtimeOpenApi.ts` diff holds only the two new types
(`TurnCommandPrompt`, `CommandPromptDescriptor`) and the two `prompts` fields.
No unrelated drift appeared in any of the three clients.

### Frontend, after the regeneration

| Check | Result |
| --- | --- |
| `npx --no-install tsc --noEmit -p .` | exit 0 |
| `npx --no-install prettier --check src/slices/runtime/runtimeOpenApi.ts` | formatted |
| `npx --no-install vitest run` (full suite) | 3985 tests passed, 7 skipped |

### Other checks

| Check | Result |
| --- | --- |
| `apps/control-plane-backend/.venv/bin/python scripts/migration_guides.py check-pr --base origin/swift --worktree` | valid, 1 new declaration |
| `openspec validate allow-several-prompt-commands --strict` | valid |

### Performance review (`fred-performance-reviewer` procedure, read-only)

Scope: the fred-sdk, fred-core and fred-runtime diff. Classification of the
touched paths: per-request validation and the per-turn history write
(category "per-turn orchestration"); no LLM call site, no tool invocation, no
KPI or log emission, no shared client, cache or module-level state.

Path walked:

1. FastAPI validates `RuntimeExecuteRequest`, so `TurnCommand`
   (`libs/fred-sdk/fred_sdk/contracts/context.py:424`) and at most 16
   `TurnCommandPrompt` (`:409`, bound at `:440`). Six scalar fields each, no
   validator function, no I/O. A longer list is refused there with a 422,
   before any work.
2. `to_legacy_context()` dumps the context into the internal request
   (`libs/fred-runtime/fred_runtime/app/agent_app.py:1280`): at most 16 small
   dicts more.
3. The `RuntimeContext` the pod rebuilds for the run
   (`agent_app.py:4579` onwards) does not copy `command`, so the list never
   reaches the agent loop, a model call or a tool call.
4. `_turn_command` (`agent_app.py:2917`, called at `:3801`, `:6247` and
   `:6353`) validates `CommandDescriptor`
   (`libs/fred-core/fred_core/history/history_schema.py:413`). Synchronous,
   CPU only, bounded by the same 16; at `:3801` it runs after the stream has
   been sent to the client.
5. The existing asynchronous history save writes the descriptor inside
   `metadata_json`; the row grows by a few kilobytes at most. The read path
   validates it with the `ChatMetadata` validation it already ran per row.

Invariants checked: no blocking I/O added inside a coroutine; no sequential
awaits added; no new metric, label, timer, logger or sink
(`PROMETHEUS_ALLOWED_LABELS` untouched); no outbound call, so no timeout to
bound; no new in-memory state, so nothing pod-local to declare; the added CPU
work is a bounded pydantic validation of scalars.

Findings: none. Confirmed from the code, not load-tested, and a load test
would not be informative for a bounded validation of this size.

To review when the frontend part is built (not in this diff): the send then
waits for one prompt read per distinct prompt, up to 16, which must run in
parallel and not one after the other.

### Not verified

- No end-to-end run against the local services: no turn was sent with a
  `prompts` list, since no client builds one yet.
- The behaviour of a pod on an older fred-sdk is read from the models' extra
  policy and from the unknown-key test, not exercised against an old build.
- The tests and quality checks of the other projects that depend on fred-core
  and fred-sdk (control-plane, knowledge-flow, fred-agents, capabilities) were
  not run; the change is additive and none of them reads the descriptor.
