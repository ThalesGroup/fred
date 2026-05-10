# fred-core Quality Backlog

**Last updated:** 2026-05-10
**Scope:** `libs/fred-core` only
**Reference standard:** `apps/control-plane-backend` for structure and validation discipline, plus `docs/swift/platform/DEVELOPER_CONTRACT.md`

---

## 0 — Background and Goals

After the `fred-runtime` quality hardening track, `fred-core` should receive the
same kind of explicit audit instead of relying on scattered observations across
feature backlogs.

This document is the implementation-facing remediation plan for `fred-core`.
It focuses on structural quality, validation discipline, typing, coverage, and
module boundaries. It is not a feature backlog.

**Non-negotiable rules for every phase:**

- **Default validation stays fully offline.** `make test` must remain the
  canonical default path and must not require Keycloak, OpenFGA, MinIO,
  Postgres, Temporal, or any other third-party service. Tests that need those
  services must stay marked `@pytest.mark.integration`.
- **Coverage commands must also stay offline by default.** A coverage run that
  silently exercises integration tests is not a valid default quality signal.
- **Do not let baselines hide debt.** `make code-quality` passing is not enough
  when a package keeps a non-empty `basedpyright` baseline. Raw
  `basedpyright` must be tracked separately.
- **No unwarranted `Any`.** `Any` and `dict[str, Any]` are not acceptable at
  contract, service, CLI, or persistence boundaries. If an external payload is
  genuinely opaque, keep it local to the adapter and mark it with a short
  `# opaque` or `# open bag` comment.
- **Uniform logs only.** Prefer deferred formatting in log calls, reuse the
  existing logger families, and do not add new `logger.*(f"...")` calls.
- **Module size must stay intentional.** If a file is already around `600+`
  lines, do not add another concern to it before extracting a focused module.
- **Blocking behavior must stay explicit.** Blocking I/O is acceptable only on
  clearly synchronous or thread-owned paths. Do not let sync helpers leak into
  async call paths by accident.

---

## 1 — Current State Snapshot (2026-05-10)

| File | Lines | Problem |
|---|---|---|
| `fred_core/cli/auth.py` | 1 039 | Shared CLI seam packs PKCE browser flow, cache file IO, token refresh, YAML discovery, and bearer-token helpers into one file; fully omitted from default coverage |
| `fred_core/model/factory.py` | 805 | Provider selection, defaults, auth patching, embeddings, streaming, and transport config live together; highest `Any` concentration in the package |
| `fred_core/kpi/kpi_writer.py` | 755 | Event shaping, sink fan-out, summary rollups, background thread loop, and formatting all live together; fully omitted from default coverage |
| `fred_core/security/rebac/rebac_engine.py` | 629 | Large authorization seam with team/document/resource helper logic concentrated in one engine file; offline coverage is acceptable but the module is too large |
| `fred_core/model/http_clients.py` | 387 | Pure transport-tuning logic still has broad `Any` usage, but offline coverage is now `91%`; the remaining work here is typing cleanup, not confidence |
| `fred_core/security/outbound.py` | 129 | Sync `requests`-based token provider is an explicit sync seam; safe only while it stays isolated from async paths; fully omitted from default coverage |
| Package-level validation | — | Raw `basedpyright` is clean, the baseline file is empty, `make code-quality` passes, `make test` passes offline, and offline package coverage is now `84%`; ad hoc `pytest --cov` without the offline marker filter is still not a valid default signal because it incorrectly pulls OpenFGA integration tests and fails against `localhost:7080` |

### Cross-cutting inventory

- `4` source files in `fred_core/` exceed `600` lines:
  `cli/auth.py`, `model/factory.py`, `kpi/kpi_writer.py`,
  `security/rebac/rebac_engine.py`
- `0` eager f-string logger calls remain in `fred_core/`
- `116` `Any` / `dict[str, Any]` matches still exist in source files
- The default offline test suite is healthy; the main validation gap is that
  coverage discipline is not explicit enough, and whole files are currently
  omitted even when they contain pure logic worth testing

### Validation snapshot

Validation run on 2026-05-10:

- raw `basedpyright` in `libs/fred-core`: `0 errors, 0 warnings, 0 notes`
- `.baseline/basedpyright-baseline.json`: `{ "files": {} }`
- `make code-quality` in `libs/fred-core`: passes
- `make test` in `libs/fred-core`: `137 passed, 11 deselected`
- offline coverage command
  `.venv/bin/uv run pytest -m "not integration" --disable-socket --allow-unix-socket --cov=fred_core --cov-report=term-missing -q`:
  `84%` total
- naive coverage command `.venv/bin/uv run pytest --cov=fred_core --cov-report=term-missing -q`:
  invalid as a default quality signal; it pulled OpenFGA integration tests and
  failed with connection attempts to `localhost:7080`

---

## 2 — Phase 1: Validation Contract and Coverage Hygiene

**Status:** `[~]` In progress — canonical offline coverage target added 2026-05-10
**Effort:** ~1 h
**Risk:** Very low

### Problem

`fred-core` already has the right default test behavior through `make test`,
but the package still lacks one obvious, canonical offline coverage path.

Today:

- `make test` correctly runs `pytest -m "not integration"` with sockets
  disabled
- a generic `pytest --cov` run can accidentally execute integration tests
- `tool.coverage.run.omit` hides large files that mix genuine live-service
  adapters with pure helper logic

The audit goal is not to delete the omit list blindly. The goal is to ensure
that the default coverage signal is valid and that pure logic is extracted from
currently omitted files when practical.

### Changes

- `[x]` Add one explicit developer-facing offline coverage command or
  `Makefile` target for `fred-core` — `make coverage-offline`
- `[x]` Document the target in `libs/fred-core/README.md`
- Keep the canonical offline flags:
  `-m "not integration" --disable-socket --allow-unix-socket`
- `[ ]` Review the coverage omit list and keep only genuinely external or
  interactive surfaces omitted
- `[ ]` When an omitted file mixes pure logic and live adapters, extract the
  pure helpers into testable modules rather than expanding the omit list

### Validation

```bash
cd libs/fred-core
make code-quality
make test
.venv/bin/uv run pytest -m "not integration" --disable-socket --allow-unix-socket --cov=fred_core --cov-report=term-missing -q
```

---

## 3 — Phase 2: Logging Uniformity

**Status:** `[x]` Complete — eager log interpolation removed 2026-05-10
**Effort:** ~1 h
**Risk:** Low

### Problem

`fred-core` still has eager f-string log calls and a few ad hoc prefix styles in
shared modules. This is below the logging bar already set for `fred-runtime`.

Resolved on 2026-05-10:

- `[x]` `fred_core/filesystem/minio_filesystem.py`
- `[x]` `fred_core/store/opensearch_mapping_validator.py`
- `[x]` `fred_core/kpi/kpi_writer.py`
- `[x]` `fred_core/kpi/opensearch_kpi_store.py`
- `[x]` `fred_core/common/fastapi_handlers.py`
- `[x]` `fred_core/common/utils.py`
- `[x]` `fred_core/logs/opensearch_log_store.py`
- `[x]` OpenSearch log-store `print(...)` fallbacks replaced with logger calls

### Changes

- Convert eager log f-strings to deferred formatting
- Keep existing logger names and channels stable
- Avoid inventing new local prefixes when a module already has a visible log
  convention
- When touching OpenSearch-backed stores, keep the log shape consistent between
  log and KPI variants

### Validation

```bash
cd libs/fred-core
rg -n 'logger\.[a-z]+\(".*%|logger\.[a-z]+\(f"' fred_core -g '*.py'
make code-quality
make test
```

---

## 4 — Phase 3: Tighten Type Boundaries

**Status:** `[ ]` Not started
**Effort:** ~3 h
**Risk:** Medium

### Problem

The package is raw-type-clean today, but that does not mean it is boundary-clean.
`Any` remains concentrated in a small number of shared seams.

Largest current concentrations:

| File | Approx. `Any` matches | Notes |
|---|---|---|
| `fred_core/model/factory.py` | 17 | Provider settings and constructor plumbing stay too loose |
| `fred_core/kpi/opensearch_kpi_store.py` | 13 | OpenSearch query/aggregation shapes still broad |
| `fred_core/cli/auth.py` | 9 | Session payload and config discovery shapes can be narrowed |
| `fred_core/logs/opensearch_log_store.py` | 8 | Similar issue to KPI OpenSearch store |
| `fred_core/model/http_clients.py` | 8 | Transport tuning parsers should accept narrower typed input |
| `fred_core/history/history_schema.py` | 6 | Message-part argument bags are still open |
| `fred_core/security/oidc.py` | 5 | JWT header/claim payloads should be typed or explicitly opaque |
| `fred_core/portable/observability.py` | 5 | Pure observability seam should use `object` or concrete types where possible |

### Fix approach

- Replace payload `dict[str, Any]` session/cache shapes in `cli/auth.py` with
  `TypedDict` payloads
- Narrow `model/factory.py` and `model/http_clients.py` away from package-wide
  `Dict[str, Any]` settings threading where a smaller typed surface is possible
- Keep truly open JSON bags local to the adapter edge and mark them
  `# opaque` or `# open bag`
- For OpenSearch and OIDC payloads, prefer small typed helper aliases or
  `TypedDict`s over broad `Any` returns
- Do not treat raw `basedpyright` success as a substitute for better boundary
  contracts

### Important nuance

Not every `Any` must disappear from the package. Some external payloads are
genuinely open-ended. The bar is:

- no unnecessary `Any` at function boundaries
- no `dict[str, Any]` escaping into shared contracts by default
- remaining opaque bags documented at the exact adapter boundary

### Validation

```bash
cd libs/fred-core
.venv/bin/basedpyright
rg -n '\bAny\b|dict\[str, Any\]' fred_core -g '*.py'
make code-quality
make test
```

---

## 5 — Phase 4: Split Oversized Modules

**Status:** `[ ]` Not started
**Effort:** ~1-2 days
**Risk:** Medium

### Problem

Four `fred-core` modules are already beyond the repository's practical size
limit for focused maintenance:

| File | Lines | Split direction |
|---|---|---|
| `fred_core/cli/auth.py` | 1 039 | PKCE browser flow, session cache IO, config discovery, and token-refresh helpers should not live in one module |
| `fred_core/model/factory.py` | 805 | Provider defaults, auth patching, and provider-specific builders should be separated |
| `fred_core/kpi/kpi_writer.py` | 755 | Event emission, rollups, summary loop, and formatting should be decomposed |
| `fred_core/security/rebac/rebac_engine.py` | 629 | Keep the public engine stable, but extract focused helper modules for traversal or batch-relation logic |

### Split rules

- Keep public import surfaces stable where possible
- Prefer extraction by concern, not by arbitrary line count
- Do not invent a new architecture or extra abstraction layer just to move code
- When splitting, move pure helpers first because they are the easiest to test
- Preserve existing behavior and tests before adding new capability

### Suggested first split order

1. `cli/auth.py`
2. `model/factory.py`
3. `kpi/kpi_writer.py`
4. `security/rebac/rebac_engine.py`

### Validation

```bash
cd libs/fred-core
.venv/bin/basedpyright
make code-quality
make test
```

---

## 6 — Phase 5: Coverage Hardening for Pure and Shared Seams

**Status:** `[~]` In progress — first quick-win batch landed 2026-05-10
**Effort:** ~3 h
**Risk:** Low to medium

### Problem

Package-level offline coverage is already `82%`, which is healthier than the
previous `fred-runtime` baseline. The remaining issue is not the total number
alone. The issue is that several pure or shared modules are still under-tested,
and some large omitted files hide logic that should be extracted and exercised
offline.

Quick wins completed on 2026-05-10:

- `[x]` `fred_core/portable/observability.py` raised from `0%` to `97%`
- `[x]` `fred_core/common/fastapi_handlers.py` raised from `38%` to `100%`
- `[x]` `fred_core/filesystem/local_filesystem.py` raised from `28%` to `95%`
- `[x]` `fred_core/store/local_content_store.py` raised from `33%` to `96%`
- `[x]` `fred_core/security/authorization_decorator.py` raised from `30%` to `100%`
- `[x]` `fred_core/model/http_clients.py` raised from `53%` to `91%`

Current remaining offline coverage hotspots from the 2026-05-10 run:

| File | Coverage | Risk |
|---|---|---|
| `fred_core/security/rebac/rebac_factory.py` | `47%` | Small factory seam still has low confidence |
| `fred_core/scheduler/temporal_client_provider.py` | `50%` | Small provider wrapper with easy mock seams |
| `fred_core/cli/ui.py` | `52%` | Shared CLI rendering helper |
| `fred_core/kpi/kpi_phase_metric.py` | `53%` | Small KPI helper with easy unit-test seams |
| `fred_core/security/keycloak/keycloack_admin_client.py` | `57%` | Shared auth adapter is still thinly tested offline |
| `fred_core/kpi/prometheus_kpi_store.py` | `68%` | Core KPI surface should be brought above the file target |
| `fred_core/kpi/log_kpi_store.py` | `67%` | Structured log KPI path still below target |
| `fred_core/logs/base_log_store.py` | `67%` | Shared log-store contract surface still under-tested |

### Fix approach

- Add direct offline tests for pure shared helpers first:
  `portable/observability.py`, `fastapi_handlers.py`, `local_filesystem.py`,
  `local_content_store.py`, `authorization_decorator.py`, `cli/ui.py`
- Raise coverage on `model/http_clients.py` with focused settings/limits/timeout
  parsing tests
- When splitting large omitted files, extract pure logic into new testable
  modules instead of leaving the whole original file excluded forever
- Keep the package-level offline floor at `>= 80%` during the remaining work
- Require every file touched by these quality phases to reach at least `70%`
  offline coverage

### Validation

```bash
cd libs/fred-core
.venv/bin/uv run pytest -m "not integration" --disable-socket --allow-unix-socket --cov=fred_core --cov-report=term-missing -q
```

---

## 7 — Definition of Done

This backlog is closed when all of the following are true:

- `[x]` `make code-quality` passes in `libs/fred-core` — confirmed 2026-05-10
- `[x]` Raw `basedpyright` passes with zero errors, warnings, and notes in
  `libs/fred-core`, and the baseline file is empty — confirmed 2026-05-10
- `[x]` `make test` passes in `libs/fred-core` with offline tests only
  (`137 passed, 11 deselected`) — confirmed 2026-05-10
- `[x]` One canonical offline coverage command or target exists and is
  documented for `fred-core` — `make coverage-offline` ✅ 2026-05-10
- `[x]` No default validation path attempts to connect to OpenFGA, Keycloak,
  MinIO, Postgres, Temporal, or other third-party services ✅ 2026-05-10
- `[ ]` Remaining `Any` / `dict[str, Any]` function-boundary usages are either
  removed or explicitly marked `# opaque` / `# open bag` at the adapter edge
- `[x]` `rg -n 'logger\.[a-z]+\(f"' fred_core -g '*.py'` returns zero matches ✅ 2026-05-10
- `[ ]` No file in `fred_core/` exceeds `600` lines, excluding generated
  artifacts only
- `[x]` Offline package coverage reaches at least `80%`, and every file touched
  by the quality phases is at or above `70%` ✅ 2026-05-10
- `[ ]` Large omitted files no longer hide pure logic that should be unit-tested

---

## 8 — Suggested Execution Order

To keep risk low and avoid churn, work in this order:

1. **Phase 1 first** — freeze the canonical offline coverage signal before
   using coverage numbers to drive decisions
2. **Phase 5 quick wins** — add direct tests for `portable/observability.py`,
   `common/fastapi_handlers.py`, `local_filesystem.py`, and
   `local_content_store.py`
3. **Phase 4A + Phase 3A** — split `cli/auth.py` and tighten its cache/session
   payload typing in the same track
4. **Phase 4B + Phase 3B + Phase 5B** — split `model/factory.py`, tighten
   `model/http_clients.py`, and add focused tests for the extracted pure logic
5. **Phase 4C + Phase 2C + Phase 5C** — split `kpi/kpi_writer.py`, normalize
   its logging, and test extracted summary/formatting helpers
6. **Phase 4D** — split `security/rebac/rebac_engine.py` last, preserving the
   current public engine surface and behavior

**Rule while this backlog is open:** do not add new concerns to
`cli/auth.py`, `model/factory.py`, `kpi/kpi_writer.py`, or
`security/rebac/rebac_engine.py` without paying down the seam you are extending.

---

## 9 — Related Docs

- `docs/swift/backlog/FRED-RUNTIME-QUALITY.md` — sister quality track for
  `fred-runtime`
- `docs/swift/backlog/CONTROL-PLANE-CLI-BACKLOG.md` — documents why shared CLI
  primitives belong in `fred-core`
- `docs/swift/backlog/RUNTIME-FEATURE-AUDIT.md` — runtime-side inventory of
  features that consume `fred-core` helpers
- `docs/swift/backlog/BACKLOG.md` — feature backlogs that still reference
  future `fred-core` KPI and CLI changes
