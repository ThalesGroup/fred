# CodeQL "Code quality" — triage & cleanup tracker

**Branch:** `fixes` · **Source:** GitHub → Security and quality → Standard findings → Code quality
**Reproduced locally:** CodeQL 2.25.6, suite `python-code-quality.qls`, over the tracked Python tree.
**Totals:** 196 findings locally (GitHub shows ~205; delta = slightly later commit + a couple extended-suite rules).
**Nature:** all severity "Note" (Maintainability / Reliability). **None are security issues.**

> How this was produced: built a CodeQL DB over a `git archive` export of the tree and ran the
> exact quality suite behind the GitHub page. Toolchain + DBs live in the session scratchpad;
> can re-run to confirm the delta once cleanups land.

---

## Status legend
- `[x]` done · `[ ]` open · `MOOT` no longer applies (code being removed) · `FP` false positive / intentional (dismiss on GitHub)

---

## 1. Real bug — FIXED
- [x] **`py/unreachable-statement`** — `features/model/service.py:271` — dead `try: pass / except: return points`
  guard; the scikit-learn fallback could never fire. Fixed via `importlib.util.find_spec("sklearn")`
  (commit `93b2b94a`). **Note: `model/` folder is being removed entirely by another assistant → whole area MOOT.**

## 2. MOOT — inside `model/` (folder being deleted, do not spend effort)
- MOOT `py/unreachable-statement` — `features/model/service.py:379` (second `try: pass` in `_predict_cluster_vector`, same pattern)
- MOOT `py/unused-local-variable` — `features/model/service.py:293`, `:399`
- (Any other `features/model/**` findings below are also MOOT.)

---

## 3. Worth fixing (real, low severity)

- [x] **`py/multiple-definition`** — `features/scheduler/pull_files_activities.py:77` — DONE (commit `efe5e392`).
  Removed the dead `ingestion_service = get_ingestion_service()` (reassigned before use) and tidied the imports.
- [x] **`py/file-not-closed`** — `core/stores/content/filesystem_content_store.py:178` — **FALSE POSITIVE, dismiss on GitHub.**
  Verified: `get_content_range` → `content_service.get_range_stream`/`get_full_stream` → `content_controller`
  streams via `StreamingResponse(..., background=BackgroundTask(raw_stream.close))` (lines 347 & 392). Both the
  200 and 206 paths close the stream after the response, which calls `RangeStreamWrapper.close()` → closes the
  file. CodeQL can't trace the close across wrapper→service→controller→BackgroundTask. No code change.
- [ ] **`py/empty-except` ×10** — all catch *specific* exceptions with clear intent; rule fires only
  because there's no explanatory comment. Add a one-line comment (or `# noqa`) where you want silence.
  None swallows a broad `Exception` blindly.
  - `scripts/check_route_security.py:88,114,143`
  - `core/stores/vector/chromadb_vector_store.py:148` (JSON parse fallback)
  - `libs/fred-runtime/.../common/context_aware_tool.py:62,90`
  - `libs/fred-core/.../filesystem/gcs_filesystem.py:230` (idempotent delete, `except NotFound`)
  - `docs/postgres-migration/generate_graph.py:68`, `scripts/generate_openapi.py:76`
  - `features/scheduler/workflow.py:121` (int-parse fallback — genuinely fine)
- [ ] **`py/commented-out-code`** — `application_context.py:726` — delete the commented block.
- [ ] **`py/use-of-exit-or-quit`** — `common/utils.py:45` — use `sys.exit()` instead of `exit()`.

## 4. Safe mechanical cleanups (real, zero-risk — likely also catchable by ruff)

- [ ] **`py/unused-import` (16)** — worth removing the genuine ones:
  - `knowledge_flow_backend/main.py:52`
  - `libs/fred-runtime/.../react/react_stream_adapter.py:52`
  - `libs/fred-sdk/.../authoring/authored_tool_runtime.py:137`
  - `libs/fred-core/.../tests/logs/test_memory_log_store.py:27`
  - ⚠️ `apps/*/alembic/env.py:*` (12 of the 16) — **check before removing**; Alembic `env.py` often
    imports for framework side effects / `target_metadata` wiring. Many are FP.
- [x] **`py/unnecessary-pass` — DONE across the monorepo.**
  - `ed4b9890` — knowledge-flow: autofixed 48 PIE790 hits (12 CodeQL + redundant `...`/`pass` after docstrings).
  - `6abfcaf3` — fred-core (13) + control-plane (3): autofixed the remaining placeholders (code only).
  - `5a699fe8` — **shared root `/ruff.toml`**: single source of truth for lint policy. Enables PIE790 for ALL
    six python projects (config-less ones inherit via upward discovery; knowledge-flow opts in via
    `extend = "../../ruff.toml"`, keeps its line-length 200). Also sets `target-version = "py312"` (matches
    requires-python; cleared a pre-existing F821 `ExceptionGroup` in fred-runtime). Lint-only — verified zero
    formatting churn across all projects. **Recurrence now prevented everywhere; adding the next shared lint
    rule is a one-line edit in `/ruff.toml`.**
- [ ] **`py/unused-local-variable` (4, minus model/)** — `core/stores/vector/clickhouse_vector_store.py:503` ·
  `features/resources/utils.py:38`
- [ ] **`py/repeated-import` (2)** — `features/content/content_controller.py:65` · `libs/fred-core/.../logs/log_setup.py:47`
- [ ] **`py/import-and-import-from` (2)** — `tests/core/test_application_context_crossencoder.py:20` ·
  `libs/fred-core/.../tests/security/test_whitelist_access_control.py:30`
- [ ] **`py/unnecessary-lambda` (14)** — mostly in tests (`test_main.py`, `test_lifecycle_actions.py`) as mock
  return values; low priority, some needed for mock signatures. `common/structures.py:849` is the one prod hit.

---

## 5. False positives / intentional — dismiss or ignore (≈135 of 196)

- **FP `py/ineffectual-statement` (78)** — the single biggest bucket, all noise. Verified every one:
  **66 are `...` (Ellipsis) bodies** of `Protocol` / `@abstractmethod` / `@overload` stubs (idiomatic);
  **12 are `await task`** statements (awaited for completion / exception propagation — that *is* the effect).
  **Zero** were a `==`-instead-of-`=` typo (grepped all 78). Safe to bulk-dismiss.
- **FP `py/unused-global-variable` (22)** — **~16 are Alembic migration globals**
  (`revision`, `down_revision`, `branch_labels`, `depends_on` in `alembic/versions/*.py`) — **required by
  the Alembic framework**, read via introspection CodeQL can't see. Dismiss those. Remaining ~6 to check:
  `core/stores/vector/clickhouse_vector_store.py:39–43`, `libs/fred-core/.../documents/document_models.py:46`.
- **FP `py/non-iterable-in-for-loop` (1)** — `features/tag/tag_service.py:308` iterates `UserTagRelation`,
  a `class(str, Enum)`. Iterating an Enum class is valid; CodeQL doesn't model the Enum metaclass. Dismiss.
- **Ignore `py/mixed-returns` (22)** — standard guard-clause idiom in FastAPI controllers
  (`mcp_fs_controller.py` ×15, `corpus_manager_controller.py` ×7, `metadata/service.py:307`). Only a bug if a
  function is contractually non-optional — none here are. Bulk-ignore.
- **Minor `py/side-effect-in-assert` (2)** — both in `libs/fred-core/.../tests/common/test_lru_cache.py:48,53`;
  test code never run under `python -O`. Low priority.
- **Mostly-FP `py/unreachable-statement` (remaining, excl. model/)** —
  `features/scheduler/in_memory_scheduler.py:107,158` (const-propagation FP on a `simulated_delay_seconds`
  debug branch); rest in tests.

---

## Suggested order to proceed
1. §4 safe mechanical cleanups (fast, low-risk; verify each isn't an Alembic/framework FP first).
2. §3 real low-severity items (empty-except comments, redundant call, file-stream verify).
3. Bulk-dismiss §5 on GitHub with the reasons above (especially the 78 ineffectual + Alembic globals).
4. Re-run CodeQL quality suite to confirm the score moves.
