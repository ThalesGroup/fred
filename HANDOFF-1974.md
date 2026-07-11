# HANDOFF — issue #1974 (capability selection end-to-end), branch `feat/capab-1974-selection`

Status: **COMPLETE.** All acceptance criteria met; all four touched modules green
(tests + `make code-quality`). Nothing in progress; nothing left unstarted. Base:
`feat/agent-capability-1961` @ `7f1ec17e8` (capability track tip — do NOT rebase onto main).

## Commit stack (base → tip)
- `ec33aca2` feat: fred-sdk wire models (predecessor)
- `5904cf52` feat: runtime assembly + lazy upgrade (predecessor)
- `36b06069` feat: pod capability surface + execution assembly (predecessor)
- `dd386034` feat: control-plane capability catalog aggregation + save-time validation
  (clean replacement of the earlier wip commit; failing `test_main` payload fixed)
- `c506471b` chore: regenerate control-plane + runtime api clients
- `d5759897` feat: capability selection in the agent Tools tab (frontend)
- `4495a214` docs: #1974 as-implemented note in AGENT-CAPABILITY-RFC
- `6956d719` fix: drop unused ReActAgent import in runtime capability endpoint tests
- `a73111bd` fix: type-correct StoredCapabilityConfig construction in sdk tuning test
- `87cad3a0` style: ruff format + detect-secrets allowlist on runtime capability code

## Verification (all green)
- **control-plane-backend**: `make test` 250 passed; `make code-quality` clean.
- **fred-runtime**: `make test` 484 passed (2 integration deselected); `make code-quality`
  clean (exit 0 — ruff/format/detect-secrets/basedpyright all pass).
- **fred-sdk**: `make test` 210 passed; `make code-quality` clean (exit 0).
- **frontend**: `make test` 298 passed (26 files); `make code-quality` (tsc + prettier) clean.

## What landed this session (from the partial handoff)
1. Fixed `test_main.py::test_team_agent_instances_returns_managed_identity`
   (added `"capability_config": {}` to the expected payload) and squashed the wip
   control-plane commit into `dd386034`.
2. Regenerated BOTH generated clients (`controlPlaneOpenApi.ts`, `runtimeOpenApi.ts`)
   via `make update-control-plane-api` + `make update-runtime-api`. The backend
   `openapi.json` files are **gitignored** (build artifacts) — only the `.ts` clients
   are tracked/committed.
3. Frontend Tools tab now lists `selectedTemplate.available_capabilities`: new
   `CapabilityCard` (switch + metadata-driven `TuningFieldRenderer` for `config_fields`),
   capability selection/config state threaded through `AgentFormModal` → `AgentFormBody`,
   submit payload carries `capability_ids` + `capability_config_values`, edit form
   re-renders from `instance.capability_config[id].config` via
   `extractCapabilityConfigValues`. Config for unselected/undeclared capabilities is
   pruned in `buildAgentFormSubmitPayload`; capability fields are omitted for
   capability-less templates so a plain edit never triggers live-pod re-validation.
   6 new unit tests in `AgentFormModal.test.ts` (2 MCP-untouched + 4 capability).
4. RFC as-implemented note appended to `docs/swift/rfc/AGENT-CAPABILITY-RFC.md` (§3.9).
5. Cleaned pre-existing lint/type/format debt in #1973/#1974 files that blocked the
   per-module gates (unused import, raw-dict type mismatch, unformatted `agent_app.py`,
   a detect-secrets false positive in `test_capability_registry_1973.py`).

## Key frontend files
- `apps/frontend/src/rework/components/pages/TeamAgentsPage/AgentFormModal/CapabilityCard/`
  (new component + CSS)
- `.../AgentFormModal/AgentFormBody.tsx`, `.../AgentFormModal.tsx`,
  `.../AgentFormModal.test.ts`, `.../TeamAgentsPage.tsx`

## Design decisions (unchanged from partial handoff §d — recorded in the RFC note)
Wire models once in fred-sdk; catalog advertised per template (no new endpoint);
`selected_capability_ids=None` == no capabilities today; typed 422 (no field-error
envelope); asset-slot enforcement pod-side; control-plane upload forwarding deferred to
#1903; ReAct-only execution.

## Conflict notes vs #1977
- Generated `controlPlaneOpenApi.ts` / `runtimeOpenApi.ts` are now regenerated on this
  branch — if #1977 also regenerates, prefer regenerating once post-merge over merging
  generated diffs.
- `agent_app.py` — this branch reformatted it (whitespace) and touched `/templates`,
  the new validate-config endpoint, and execution threading; #1977 touches the
  runtime-events / UiPart union. Textual proximity risk in the import block and the
  `_AgentTemplateSummary` area.
- `fred_sdk/contracts/capability/__init__.py` + `manifest.py` — both branches add exports
  (`CapabilityCatalogEntry` here, `chat_part_kind` there); trivial merge.
- `fred_runtime/capabilities/demo.py` — untouched here; #1977 may add chat parts.
