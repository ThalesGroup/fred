# docs/CONVENTIONS.md

Coding style, typing, and testing rules for this repository. Applies to all
contributors and AI assistants. Source of truth for `CLAUDE.md §Step 4`.

---

## General

- **Minimal scope.** Implement exactly what the task requires. No refactors, no
  "while I'm here" cleanups, no abstraction for hypothetical future use.
- **Shared code first.** Before writing a new utility, check whether it exists in
  `fred-core`, `fred-sdk`, or the shared frontend design system. Duplicate code is
  a defect.
- **Fewer lines over more lines.** If two approaches produce the same result, choose
  the shorter one.
- **No new architecture.** Do not invent a new endpoint family, service boundary, or
  migration direction without an RFC (see `docs/swift/rfc/`).
- **No over-engineering.** No factory for a single implementation, no plugin system
  for a single case. Three similar lines is correct; premature abstraction is a bug.
- **Converge on the existing pattern before adding a new one.** Before writing a new
  function, look for its natural sibling already in the codebase (the existing
  union/aggregate/list function it's the dual or extension of) and place the new
  logic next to it, in the module that already owns that concern — not a new small
  helper scattered elsewhere. When two surfaces expose the same underlying setting
  or config (e.g. a listing/picker endpoint and its paired write-validation
  endpoint), both must read from one shared computation, never two independently
  derived views that can silently disagree — this matters most for anything exposed
  as a setting/config choice in the UI, where a silent mismatch reads as a bug
  ("the app offered this, then rejected it").

---

## Performance & concurrency

Applies to `fred-runtime`, `fred-core`, and any backend serving concurrent
requests. Production shape to design against: ~200 users hitting one
`fred-agents` instance at once, up to 4 replicas running concurrently, and
every agent turn calling a remote LLM API gateway — that call path is the
top priority; tool invocation is the second. This section carries the same
weight as code quality — a change that passes `make code-quality` but stalls
the event loop or goes dark in Grafana is not done. See the
`fred-performance-reviewer` skill for the full review checklist; the rules
below are what to follow while writing the code, not just at review time.

- **No blocking I/O inside `async def`.** No sync `requests`/`psycopg2`/`boto3`/
  sync SDK call made inline inside a coroutine on a request path. Offload via a
  thread executor if no async client exists — never call it inline "for now".
- **Independent async work runs concurrently, not sequentially.** Multiple tool
  calls, fetches, or lookups with no ordering dependency use
  `asyncio.gather`/`TaskGroup`. A sequential `await` in a `for` loop needs a real
  ordering reason, or it's a bug.
- **KPI/log emission never opens a synchronous network call in a hot path.**
  Emit through the existing `KPIWriter`/`kpi.timer(...)`/`emit_audit_log`
  machinery, which is backed by `ResilientSinkStore`
  (`libs/fred-core/fred_core/common/resilient_sink.py`) — a bounded queue drained
  by a background thread behind a circuit breaker. Do not add a new store or
  logger that talks to OpenSearch/an external sink directly from request code.
- **New LLM-call or tool-call code routes through the existing observability
  middlewares**, not a hand-rolled call: `TracingKpiMiddleware`
  (`libs/fred-runtime/fred_runtime/react/middleware/tracing_kpi.py`, emits
  `llm.call_latency_ms`) and `ToolObservabilityMiddleware`
  (`libs/fred-runtime/fred_runtime/react/middleware/tool_observability.py`,
  emits `agent.tool_latency_ms`/`agent.tool_failed_total`). Bypassing them makes
  the new path invisible in Grafana.
- **A new KPI dimension must be in `PROMETHEUS_ALLOWED_LABELS`**
  (`libs/fred-core/fred_core/kpi/prometheus_kpi_store.py`) to reach Grafana at
  all. Adding a label is a deliberate decision, not automatic — user, session,
  and team identity must never become a Prometheus label (see
  `docs/swift/platform/OBSERVABILITY-AND-AUDIT.md` §3).
- **Every outbound call to the remote LLM gateway or any external service has an
  explicit, bounded timeout.** An unbounded call under concurrent load can pin a
  shared connection-pool slot and stall unrelated requests.
- **Shared HTTP/model clients are process-wide singletons** built via
  `fred_core/model/http_clients.py` / `fred_core/model/factory.py` — never
  construct a new client per request. Note the existing "first caller wins" pool
  config behavior: a second model/gateway with different timeout/pool needs will
  have its config silently ignored — check this explicitly when adding one.
- **New in-memory state (cache, buffer, rate limiter) must state whether it's
  pod-local or shared.** `fred-agents` runs multiple replicas; anything whose
  correctness depends on seeing all traffic (not just one pod's share) needs a
  shared backing store, not a module-level dict/deque.

---

## Python

- **Pydantic models for all public contracts.** Request bodies, response bodies,
  config schemas: always `BaseModel`. Never raw `dict` or `TypedDict` at a service
  boundary.
- **No Pydantic for internal dataclasses.** Use `@dataclass` or plain classes for
  structures that never cross an HTTP or serialisation boundary.
- **No mutable default arguments.** No `def f(x=[])`. Use `Field(default_factory=...)`
  in Pydantic, `field(default_factory=...)` in dataclasses.
- **Type-annotate every function signature.** Return type included. `Any` is allowed
  only when the upstream contract forces it — document why.
- **No silent `except Exception`.** Catch specific exceptions. When a broad catch is
  genuinely needed, log and re-raise or return an explicit error value.
- **Use existing `fred-core` utilities.** `ThreadSafeLRUCache`, `read_env_bool`,
  `get_config`, logging setup — do not reimplement.
- **No new `[TAG]` message prefixes.** `[SECURITY]` (via `fred_core.logs.audit_log.
  emit_audit_log`) and `[KPI]` (via `logging.getLogger("KPI")`) are the only two
  reserved for a real routed channel — never reuse either string on a plain module
  logger. For everything else, the console formatter already includes `%(name)s`
  (the logger's dotted module path) and `CompactJsonFormatter` already includes
  `file`/`line`/`logger` — that's provenance enough. ~60 ad hoc `[VECTOR]`/
  `[SCHEDULER]`/`[MetadataService]`-style tags already exist from before this rule;
  don't add a new one, and don't mass-rename the old ones as a side effect of an
  unrelated change.
- **Never hand-edit generated files.** `openapi.json` — regenerate from source and
  document the regeneration command when you run it.
- **Wrap bare `for x in SomeEnum:` in `list(...)`.** `EnumMeta.__iter__` makes an
  `Enum` class itself iterable, but CodeQL's Python analysis doesn't model that and
  flags `for x in SomeEnum:` as "non-iterable used in for loop" — a false positive,
  not a bug. Write `for x in list(SomeEnum):` instead: same members, same order, but
  the explicit `list()` call reads as unambiguously iterable to the analyzer, so the
  finding never fires and there's nothing to dismiss on GitHub each scan.

### Testing (Python)

- **Tests offline by default.** All tests in `tests/` run without network, database,
  or external service. Tests requiring external dependencies are marked
  `@pytest.mark.integration` and excluded from `make test`.
- **One test file per module.** `tests/test_<module>.py` mirrors `package/<module>.py`.
  Do not pile unrelated tests into a single file.
- **Extend existing fixtures before adding new ones.** A new scenario for
  already-tested behavior reuses the existing test file's fixtures/fakes; stand up a
  new test file or a parallel fixture set only when the thing under test genuinely
  has no existing home yet.
- **`make code-quality && make test` must pass** before reporting any task done.

---

## Frontend (TypeScript / React)

- **Design system tokens only.** No hardcoded colours, sizes, or spacing. No
  `var(--token, fallback)` with colour or dimension fallbacks — add the missing token
  to the token file instead.
- **Every `background` has an explicit `color`.** Colour and background are always paired.
- **CSS modules only.** No inline styles, no `styled-components`, no MUI `sx` prop
  in rework components.
- **No MUI in `src/rework/`.** Use design system atoms (`Button`, `Icon`,
  `IconButton`, `Switch`, `TextInput`, `TextArea`, `ButtonGroup`, `Select`). If an
  atom is missing, add it — do not pull in MUI.
- **Strict icon typing.** Icon names must be in `MaterialIconType` (`Type.ts`). Add
  the name to the union rather than widening to `string`.
- **No `any` at component boundaries.** Props interfaces are typed. Internal state
  can use `unknown` with a guard; never `as any` at a prop or hook boundary.
- **Never hand-edit generated slices.** `runtimeOpenApi.ts`, `controlPlaneOpenApi.ts`,
  `knowledgeFlowOpenApi.ts` — regenerate from OpenAPI spec.
- **`tsc --noEmit` and Prettier must pass** before reporting any frontend task done.
  For files under `apps/frontend/src/rework/`, also read
  `docs/swift/platform/FRONTEND_CODING_GUIDELINES.md`.
