## 1. Capability SDK and runtime (PR 1)

- [x] 1.1 Add the `ScopePrivate`, `AssetKey` and explicit `Public` field markers to fred-sdk with a helper that resets scope-private fields to their defaults recursively; verify with unit tests on flat, list and nested models
- [x] 1.2 Add `POST /agents/capabilities/{id}/copy-config` to the runtime: reset scope-private fields when the scopes differ, read the source `AssetKey` files through `AgentAssetPort` in the source context, run `validate_config` in the destination context with them as uploads; verify with runtime tests for same-team, cross-team, asset copy and typed rejection
- [x] 1.3 Classify settings: document-access `library_tag_ids` and `document_uids` scope-private, ppt-filler `folder_tag_id` scope-private (nested), `template_key` asset key, `key` and `folder` public, MCP `bound_library_ids` (`scope_private: true` in `mcp_catalog.yaml`); verify each capability's tests pass
- [x] 1.4 Add the guard test that fails on identifier-like config fields neither scope-private, asset key nor public across installed capabilities and the MCP catalogs (bundled and chart); verify it fails on a deliberately unmarked field and passes on the real tree
- [x] 1.5 Regenerate the runtime OpenAPI and add the dated §8 entry to `RUNTIME-EXECUTION-CONTRACT.md`; update `capabilities/AUTHORING.md` (the scope-private / public rule and why it is scope-based) and the `add-fred-capability` skill; add the PR 1 migration note; verify `make code-quality` and `make test` in fred-sdk and fred-runtime

## 2. Control plane (PR 2)

- [x] 2.1 Add the copy-targets preview (personal space plus every `team_editor` team, `template_enabled`, `missing_capabilities`) guarded by `CAN_UPDATE_AGENTS` on the source; verify API tests for template disabled, missing capability, non-editor source (403)
- [x] 2.2 Add the copy endpoint: per destination, `CAN_UPDATE_AGENTS` with the canonical team id, new instance id, `copy-config` per usable capability (rejection or 404 drops it), name rule, row creation through the enroll store path, bounded concurrency, per-destination results; verify tests for multi-target partial failure, personal space id, dropped capability, name conflict `_imported-2`, duplicate with chosen name
- [x] 2.3 Record the `agent.copied` audit event; verify a test asserts its fields
- [x] 2.4 Add the endpoints to `authz-endpoint-matrix.yaml` and the contract section of `CONTROL-PLANE-PRODUCT-CONTRACT.md`; regenerate the OpenAPI and `controlPlaneOpenApi.ts`; add the PR 2 migration note; verify `make code-quality` and `make test` in the control plane

## 3. Frontend and Help Center (PR 3)

- [x] 3.1 Move `ImportPromptDialog` to `shared/organisms/CopyToTeamsDialog` with optional per-team status, explanation and info tooltip; keep the prompt marketplace behaviour; verify the prompt import tests pass unchanged
- [x] 3.2 Add "Copy to…" to the agent card menu, wired to the preview and copy endpoints: greyed team with "Agent template not enabled", warning icon + label + tooltip listing missing capabilities, explanation paragraph, info tooltip (AgentCard label/value style), per-team toasts naming dropped capabilities; verify component tests for each state
- [x] 3.3 Switch "Duplicate" to the copy endpoint and delete its browser-side rebuild; verify a test that duplicate calls the copy with the source team and chosen name
- [x] 3.4 Add fr and en strings; verify tsc, eslint, prettier and the touched vitest suites pass
- [x] 3.5 Update the Help Center fr and en agent pages (copy an agent, what travels and what is reset, in plain words) and add the PR 3 migration note; verify `make migration-check` and the Help Center tests pass

## 4. Close-out

- [x] 4.1 Manual check in the running app: copy an agent with a library restriction and a ppt-filler template to another team and to the personal space; the copy has no library restriction, fills a presentation without re-upload, and is usable by another editor of the destination
- [x] 4.2 Run `/code-review` on each PR's diff and record the verification evidence in `verification.md`
