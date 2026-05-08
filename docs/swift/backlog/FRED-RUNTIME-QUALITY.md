# fred-runtime Quality Backlog

**Last updated:** 2026-04-27
**Scope:** `libs/fred-runtime` only
**Reference standard:** `apps/control-plane-backend` (structure, DI, typing, test conventions)

---

## 0 — Background and Goals

A code-quality audit identified five structural problems in `fred-runtime`.
This backlog documents the full remediation plan, phased so that each step
merges independently and leaves the codebase working.

**Non-negotiable rules for every phase:**

- **Full async everywhere.** No blocking I/O (`requests.*`, `time.sleep`,
  `open()`) on any async call path. Synchronous utilities must either be
  converted to `async`/`httpx` or explicitly wrapped with
  `asyncio.to_thread()` with a comment explaining why sync is acceptable.
- **No unwarranted `Any`.** Every function boundary, Pydantic model field,
  and return type must use a concrete type. `Any` is allowed only for
  genuinely opaque external payloads (e.g. `resume_payload` from graph
  agents) and must be accompanied by a one-line comment explaining why.
- **>70% offline unit test coverage per phase.** Coverage is measured by
  `uv run pytest --cov=fred_runtime --cov-report=term-missing` after each
  phase. The 70% threshold applies to new and modified files only.
  Integration-only paths (SQL engine init, Keycloak login) are exempted and
  must be marked `@pytest.mark.integration`.

---

## Current State Snapshot

| File | Lines | Problem |
|---|---|---|
| `fred_runtime/client.py` | 3 880 | 8 concerns in one module |
| `fred_runtime/app/agent_app.py` | 2 756 | No container, 14 `Any` usages, module globals |
| `fred_runtime/common/kf_workspace_client.py` | 535 | Dead `requests` import, wrong exception types |
| `fred_runtime/runtime_support/user_token_refresher.py` | ~50 | Blocking `requests.post()` on async path |
| `fred_runtime/app/config.py` | 417 | `Any | None` for MCP configuration |
| `tests/` | 6 files | No `conftest.py`, 3× duplicated fixture code, no coverage target |

---

## Phase 1 — Fix Async/Sync Correctness

**Status:** `[x]` ✅ Complete — 2026-04-27
**Effort:** ~1 h
**Risk:** Low — purely mechanical exception-type fix + one sync→async migration

### Problem A: dead `requests` import in `kf_workspace_client.py`

`import requests` is present but `requests` is never called. Its exception
type `requests.exceptions.HTTPError` appears in three `except` clauses
alongside `httpx.HTTPStatusError`. Because `httpx` raises
`httpx.HTTPStatusError` and never `requests.exceptions.HTTPError`, the
`requests` branch is dead code. One site also uses `.reason` (requests API)
instead of `.reason_phrase` (httpx API).

#### Changes

**File:** `fred_runtime/common/kf_workspace_client.py`

- Remove line: `import requests`
- Remove `from typing import Optional` → replace all `Optional[X]` with `X | None`
- Line ~169: `except (requests.exceptions.HTTPError, httpx.HTTPStatusError) as e:`
  → `except httpx.HTTPStatusError as e:`
- Line ~258: same replacement
- Line ~347: `except requests.exceptions.HTTPError as e:` → `except httpx.HTTPStatusError as e:`
  and `e.response.reason` → `e.response.reason_phrase`

### Problem B: blocking `requests.post()` in `user_token_refresher.py`

`fred_runtime/runtime_support/user_token_refresher.py` calls
`requests.post(token_url, ...)` synchronously. This file is used by the
runtime token-refresh background loop. Blocking I/O on a token-refresh path
inside an async runtime is a latency and correctness issue.

#### Changes

**File:** `fred_runtime/runtime_support/user_token_refresher.py`

- Replace `import requests` with `import httpx`
- Replace `requests.post(token_url, data=form, timeout=10)` with
  `await httpx.AsyncClient().post(token_url, data=form, timeout=10.0)`
- Change the calling function to `async def` if it is not already
- Replace `requests.exceptions.HTTPError` with `httpx.HTTPStatusError`
- Remove `from typing import Any, Dict` → use `dict[str, str]` directly

### Tests to write

**File:** `tests/test_kf_workspace_client.py` *(new)*

```
test_fetch_text_raises_workspace_retrieval_error_on_http_error
  — mock httpx.AsyncClient to raise httpx.HTTPStatusError(404)
  — assert WorkspaceRetrievalError is raised with status_code=404

test_upload_blob_raises_workspace_upload_error_on_http_error
  — mock httpx.AsyncClient to raise httpx.HTTPStatusError(413)
  — assert WorkspaceUploadError is raised

test_fetch_blob_returns_bytes_on_success
  — mock httpx.Response with content=b"hello"
  — assert fetch_user_blob returns b"hello"

test_list_user_blobs_returns_file_entries
  — mock JSON response with known entries
  — assert correct WorkspaceEntry list

test_delete_user_blob_does_not_raise_on_success
  — mock 204 response
  — assert no exception
```

**File:** `tests/test_user_token_refresher.py` *(new)*

```
test_refresh_returns_new_token_on_success
  — mock httpx.AsyncClient.post with 200 + JSON token
  — assert returned token matches

test_refresh_raises_on_http_error
  — mock httpx.AsyncClient.post to raise httpx.HTTPStatusError(401)
  — assert the correct domain exception is raised
```

**Coverage target:** 100% of both files (small, fully mockable).

### Validation

```bash
cd libs/fred-runtime
python -c "import fred_runtime.common.kf_workspace_client; print('ok')"
python -c "import fred_runtime.runtime_support.user_token_refresher; print('ok')"
make code-quality
uv run pytest tests/test_kf_workspace_client.py tests/test_user_token_refresher.py -q
```

---

## Phase 2 — Shared Test Fixtures (`conftest.py`)

**Status:** `[x]` ✅ Complete — 2026-04-27
**Effort:** ~1 h
**Risk:** Very low — pure refactor, zero logic change

### Problem

`ToolFriendlyFakeChatModel`, `StaticChatModelFactory`, and
`_make_minimal_config()` / `AgentPodConfig.model_validate(...)` stubs are
copy-pasted into `test_agent_app.py`, `test_history.py`, and
`test_openai_compat_router.py`. Each copy drifts independently.

### Changes

**File:** `tests/conftest.py` *(new)*

```python
"""Shared offline fixtures for fred-runtime tests."""

from __future__ import annotations

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from fred_runtime.app.config import AgentPodConfig


class ToolFriendlyFakeChatModel(FakeMessagesListChatModel):
    """FakeMessagesListChatModel that silently accepts tool binding."""

    def bind_tools(
        self,
        tools: object,
        *,
        tool_choice: object = None,
        **kwargs: object,
    ) -> "ToolFriendlyFakeChatModel":
        return self


class StaticChatModelFactory:
    """Always returns the same pre-built model regardless of definition."""

    def __init__(self, model: ToolFriendlyFakeChatModel) -> None:
        self._model = model

    def build(self, definition: object, binding: object) -> ToolFriendlyFakeChatModel:
        return self._model

    def build_for_operation(
        self,
        *,
        definition: object,
        binding: object,
        purpose: object,
        operation: object = None,
    ) -> ToolFriendlyFakeChatModel:
        return self._model


@pytest.fixture
def minimal_config() -> AgentPodConfig:
    """Minimal offline AgentPodConfig with security disabled."""
    return AgentPodConfig.model_validate({
        "security": {
            "m2m": {
                "enabled": False,
                "realm_url": "http://localhost/r",
                "client_id": "test-m2m",
            },
            "user": {
                "enabled": False,
                "realm_url": "http://localhost/r",
                "client_id": "test-user",
            },
            "authorized_origins": [],
        }
    })


@pytest.fixture
def fake_model() -> ToolFriendlyFakeChatModel:
    return ToolFriendlyFakeChatModel(responses=[AIMessage(content="done")])


@pytest.fixture
def static_factory(
    fake_model: ToolFriendlyFakeChatModel,
) -> StaticChatModelFactory:
    return StaticChatModelFactory(fake_model)
```

**Files to modify:**

- `tests/test_agent_app.py` — remove local `ToolFriendlyFakeChatModel`,
  `StaticChatModelFactory`, and all inline `AgentPodConfig.model_validate(...)`
  stubs; accept `minimal_config`, `fake_model`, `static_factory` as fixture
  parameters.
- `tests/test_history.py` — same removals.
- `tests/test_openai_compat_router.py` — same removals.

**Invariant:** All existing test function names and assertions are preserved
unchanged. Only setup boilerplate moves.

### Validation

```bash
cd libs/fred-runtime
uv run pytest tests/ -q --tb=short
# Pass count must be identical to pre-phase run.
```

---

## Phase 3 — Split `client.py` into `fred_runtime/cli/`

**Status:** `[x]` ✅ Complete — 2026-04-27
**Effort:** ~3 h
**Risk:** Medium — large mechanical move; mitigated by the shim

### Problem

`client.py` (3 880 lines) contains eight independent concerns. The file
cannot be tested in isolation, is impossible to import partially, and grows
with every new CLI feature.

### Target structure

```
fred_runtime/cli/
├── __init__.py            # re-exports everything in __all__ for the shim
├── pod_client.py          # AgentPodClient class + DEFAULT_AGENT_POD_BASE_URL
├── url_helpers.py         # default_agent_pod_base_url, default_agent_metrics_url,
│                          # normalize_base_url
├── completion.py          # completion_candidates, _complete_scenario_path,
│                          # install_readline_completion
├── repl_helpers.py        # print_help, _ask_cli_help, fmt_bytes,
│                          # execution_mode_label, parse_mode_command
├── kpi_display.py         # PrometheusSample, HistogramSeriesSummary,
│                          # parse_prometheus_text_exposition,
│                          # _parse_prometheus_labels,
│                          # summarize_prometheus_histograms,
│                          # filter_prometheus_samples, format_metric_value,
│                          # format_prometheus_labels, render_kpi_report
├── history_display.py     # print_history, print_runtime_event,
│                          # run_single_turn, build_hitl_resume_payload,
│                          # _HISTORY_ROLE_STYLE, _HISTORY_CHANNEL_LABELS
├── repl.py                # run_interactive_chat
├── scenario.py            # ScenarioSkipped, _scenario_resolve,
│                          # _scenario_apply_checks, _scenario_run_pause,
│                          # _scenario_run_turn, _scenario_run_hitl,
│                          # run_scenario_file
└── entrypoint.py          # build_parser, main, _COMMANDS
```

### Shim rule

`fred_runtime/client.py` is **not deleted**. Its entire body is replaced with
re-export statements:

```python
# fred_runtime/client.py — compatibility shim, do not add logic here.
from fred_runtime.cli.pod_client import AgentPodClient, DEFAULT_AGENT_POD_BASE_URL
from fred_runtime.cli.url_helpers import (
    default_agent_pod_base_url,
    default_agent_metrics_url,
    normalize_base_url,
)
from fred_runtime.cli.completion import completion_candidates
from fred_runtime.cli.kpi_display import (
    parse_prometheus_text_exposition,
    render_kpi_report,
    summarize_prometheus_histograms,
)
from fred_runtime.cli.repl import run_interactive_chat
from fred_runtime.cli.scenario import run_scenario_file, ScenarioSkipped
from fred_runtime.cli.history_display import run_single_turn
from fred_runtime.cli.entrypoint import build_parser, main
from fred_core.cli.auth import KeycloakLoginConfig, KeycloakUserSessionManager

__all__ = [
    "AgentPodClient",
    "DEFAULT_AGENT_POD_BASE_URL",
    "KeycloakLoginConfig",
    "KeycloakUserSessionManager",
    "build_parser",
    "completion_candidates",
    "default_agent_metrics_url",
    "default_agent_pod_base_url",
    "main",
    "normalize_base_url",
    "parse_prometheus_text_exposition",
    "render_kpi_report",
    "run_interactive_chat",
    "run_scenario_file",
    "run_single_turn",
    "summarize_prometheus_histograms",
]

if __name__ == "__main__":
    raise SystemExit(main())
```

### Circular import guard

Modules under `fred_runtime/cli/` must import **only** from:
- `fred_core.*`
- `fred_sdk.*`
- `httpx`, standard library, third-party
- Each other within `fred_runtime/cli/`

They must **never** import from `fred_runtime.app` or
`fred_runtime.runtime_context`. Verify with:

```bash
python -c "import fred_runtime.cli.repl; print('no circular')"
```

### Typing requirements for this phase

All functions in the new modules must have fully annotated signatures. In
particular:

- `AgentPodClient` methods: replace all `Optional[X]` with `X | None`
- `run_scenario_file`: replace `dict[str, Any]` step dicts with a typed
  `ScenarioStep` TypedDict (see below)
- `PrometheusSample`, `HistogramSeriesSummary`: already dataclasses, confirm
  all fields are typed
- `_HISTORY_ROLE_STYLE`, `_HISTORY_CHANNEL_LABELS`: use
  `dict[str, str]` literals, not `dict[str, Any]`

**`ScenarioStep` TypedDict** (new, in `scenario.py`):

```python
from typing import TypedDict, Required

class ScenarioStep(TypedDict, total=False):
    type: Required[str]        # "turn" | "hitl" | "pause" | "check"
    message: str
    expected_channel: str
    checks: list[str]
    pause_seconds: float
    agent_instance_id: str
```

### Tests to write

**File:** `tests/test_kpi_display.py` *(new)*

```
test_parse_prometheus_text_exposition_empty_input
test_parse_prometheus_text_exposition_counter
test_parse_prometheus_text_exposition_histogram_bucket
test_summarize_prometheus_histograms_returns_summary
test_format_metric_value_large_int
test_format_metric_value_sub_millisecond
test_filter_prometheus_samples_by_name_prefix
test_render_kpi_report_returns_non_empty_string
```

**File:** `tests/test_url_helpers.py` *(new)*

```
test_normalize_base_url_strips_trailing_slash
test_normalize_base_url_adds_http_scheme
test_default_agent_pod_base_url_uses_env_var
test_default_agent_pod_base_url_fallback
```

**File:** `tests/test_scenario.py` *(new)*

```
test_scenario_resolve_replaces_env_var
test_scenario_resolve_unknown_var_raises
test_scenario_apply_checks_passes_when_predicate_true
test_scenario_apply_checks_fails_raises_assertion
test_run_scenario_file_skips_when_env_var_missing
  — mark @pytest.mark.integration (requires live pod)
```

**Coverage target:** ≥ 75% on `cli/kpi_display.py`, `cli/url_helpers.py`,
`cli/scenario.py`. `cli/repl.py` and `cli/history_display.py` are I/O-heavy
and exempt from the coverage target (integration-only).

### Validation

```bash
cd libs/fred-runtime
python -c "from fred_runtime.client import AgentPodClient, run_scenario_file, main; print('shim ok')"
python -c "from fred_runtime.cli.pod_client import AgentPodClient; print('direct ok')"
python -c "from fred_runtime.cli.kpi_display import render_kpi_report; print('kpi ok')"
python -c "from fred_runtime.cli.scenario import ScenarioSkipped; print('scenario ok')"
make code-quality
uv run pytest tests/ -q
fred-agents-cli --help   # entrypoint must still resolve
```

---

## Phase 4 — Introduce `PodApplicationContext`

**Status:** `[x]` ✅ Complete — 2026-04-27
**Effort:** ~4 h
**Risk:** Medium — touches startup path; mitigated by existing lifespan tests

### Problem

`agent_app.py` contains module-level ring buffers, scattered startup helpers,
and no single composition root. There is no equivalent of
`control-plane-backend`'s `ApplicationContext`. Dependencies are resolved
ad-hoc inside `create_agent_app()` and its private helpers.

### Target structure

```
fred_runtime/app/
├── agent_app.py           # slimmed down; lifespan = 15 lines
├── config.py              # unchanged except Any fix (Phase 5)
├── config_loader.py       # unchanged
├── context.py             # PodApplicationContext  ← new
├── container.py           # build_pod_container()  ← new
├── dependencies.py        # get_pod_container(), attach_pod_container()  ← new
├── observability_factory.py  # unchanged
├── openai_compat_router.py   # unchanged
└── _catalogs.py           # unchanged
```

### `context.py` specification

```python
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from fred_core.kpi.base_kpi_writer import BaseKPIWriter
from fred_sdk.contracts.ports import HistoryStorePort
from sqlalchemy.ext.asyncio import AsyncEngine

from fred_runtime.app.config import AgentPodConfig

if TYPE_CHECKING:
    from fred_runtime.app.mcp_config import McpCatalogConfiguration


class PodApplicationContext:
    """
    Single composition root for one fred-runtime pod.

    All resource construction is lazy and side-effect-free in __init__.
    Call initialize() inside the FastAPI lifespan after log setup.
    """

    def __init__(self, configuration: AgentPodConfig) -> None:
        self.configuration = configuration
        self._sql_engine: AsyncEngine | None = None
        self._checkpointer: object | None = None
        self._history_store: HistoryStorePort | None = None
        self._kpi_writer: BaseKPIWriter | None = None
        self._metrics_exporter: object | None = None
        self._kpi_tasks: list[asyncio.Task[None]] = []

    async def initialize_sql(self) -> None:
        """Build SQL engine, checkpointer, and history store."""
        ...

    def initialize_kpi_writer(self) -> None:
        """Build the KPI writer from config."""
        ...

    def start_metrics_exporter(self) -> None:
        """Start the Prometheus metrics exporter if configured."""
        ...

    async def start_kpi_tasks(self) -> None:
        """Start background KPI flush tasks."""
        ...

    def get_sql_engine(self) -> AsyncEngine | None:
        return self._sql_engine

    def get_checkpointer(self) -> object | None:
        return self._checkpointer

    def get_history_store(self) -> HistoryStorePort | None:
        return self._history_store

    def get_kpi_writer(self) -> BaseKPIWriter:
        if self._kpi_writer is None:
            raise RuntimeError("KPI writer not initialized — call initialize_kpi_writer() first")
        return self._kpi_writer

    async def shutdown(self) -> None:
        """Cancel background tasks, dispose SQL engine, stop exporter."""
        for task in self._kpi_tasks:
            task.cancel()
        if self._kpi_tasks:
            await asyncio.gather(*self._kpi_tasks, return_exceptions=True)
        if self._sql_engine is not None:
            await self._sql_engine.dispose()
        self._stop_metrics_exporter()

    def _stop_metrics_exporter(self) -> None:
        ...
```

### `container.py` specification

```python
from fred_runtime.app.config import AgentPodConfig
from fred_runtime.app.context import PodApplicationContext

PodContainer = PodApplicationContext


def build_pod_container(configuration: AgentPodConfig) -> PodContainer:
    """Single composition-root factory — no side effects."""
    return PodApplicationContext(configuration)
```

### `dependencies.py` specification

```python
from fastapi import FastAPI, Request
from fred_runtime.app.config import AgentPodConfig
from fred_runtime.app.context import PodApplicationContext

_CONTAINER_STATE_KEY = "pod_container"


def attach_pod_container(app: FastAPI, container: PodApplicationContext) -> None:
    setattr(app.state, _CONTAINER_STATE_KEY, container)


def get_pod_container_from_app(app: FastAPI) -> PodApplicationContext:
    return getattr(app.state, _CONTAINER_STATE_KEY)


def get_pod_container(request: Request) -> PodApplicationContext:
    return get_pod_container_from_app(request.app)


def get_pod_configuration(request: Request) -> AgentPodConfig:
    return get_pod_container(request).configuration
```

### Slimmed lifespan (target shape in `agent_app.py`)

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    container = build_pod_container(config)
    bootstrap_observability(config)
    set_runtime_context(config)
    attach_pod_container(app, container)
    container.initialize_kpi_writer()
    await container.initialize_sql()
    container.start_metrics_exporter()
    await container.start_kpi_tasks()
    yield
    await container.shutdown()
```

### Ring buffer migration

`_KPI_TURNS_BUFFER` and `_AUDIT_EVENTS_BUFFER` move from module-level globals
in `agent_app.py` into `PodApplicationContext` as instance attributes:

```python
from collections import deque

class PodApplicationContext:
    def __init__(self, configuration: AgentPodConfig) -> None:
        ...
        self.kpi_turns_buffer: deque[KpiTurnRecord] = deque(maxlen=200)
        self.audit_events_buffer: deque[AuditEventRecord] = deque(maxlen=200)
```

Where `KpiTurnRecord` and `AuditEventRecord` are new typed `TypedDict`s:

```python
from typing import TypedDict

class KpiTurnRecord(TypedDict):
    exchange_id: str
    session_id: str
    agent_id: str
    turn_index: int
    input_tokens: int | None
    output_tokens: int | None
    tool_count: int | None
    latency_ms: float | None
    status: str
    timestamp: str

class AuditEventRecord(TypedDict):
    level: str
    name: str
    timestamp: str
    # remaining fields are open — use total=False for optional keys
```

These replace `dict[str, Any]` for the ring buffer entries.

### Tests to write

**File:** `tests/test_context.py` *(new)*

```
test_build_pod_container_returns_context_with_configuration
test_pod_context_get_kpi_writer_raises_before_initialize
test_pod_context_shutdown_cancels_kpi_tasks
test_pod_context_shutdown_handles_no_tasks_gracefully
test_attach_and_get_pod_container_roundtrip
test_get_pod_configuration_returns_config_from_container
```

**Add to `test_agent_app.py`:**

```
test_lifespan_attaches_container_to_app_state
test_lifespan_container_is_shut_down_on_exit
test_ring_buffers_are_instance_level_not_global
  — create two separate apps; assert buffers are independent
```

**Coverage target:** ≥ 80% on `context.py`, `container.py`, `dependencies.py`.

### Boot-order invariant

The initialization sequence must be:

```
1. bootstrap_observability()   — log setup must come first
2. set_runtime_context()       — langfuse / tracing context
3. attach_pod_container()      — container attached before any request
4. initialize_kpi_writer()     — sync, fast
5. initialize_sql()            — async, may take time
6. start_metrics_exporter()    — sync, starts thread
7. start_kpi_tasks()           — async, starts asyncio tasks
```

This order must be preserved in `lifespan`. Add an assertion or comment
explaining the constraint.

### Validation

```bash
cd libs/fred-runtime
python -c "from fred_runtime.app.context import PodApplicationContext; print('ok')"
python -c "from fred_runtime.app.dependencies import get_pod_container; print('ok')"
uv run pytest tests/test_agent_app.py tests/test_context.py -q
make code-quality
```

---

## Phase 5 — Eliminate `Any` at All Typed Boundaries

**Status:** `[x]` ✅ Complete — 2026-04-27
**Effort:** ~2 h
**Risk:** Low-medium — type narrowing only; runtime behaviour unchanged

### Inventory of `Any` in `agent_app.py` and `config.py`

| Location | Current type | Target type | Notes |
|---|---|---|---|
| `_build_sql_runtime_dependencies` return | `tuple[Any, Any, Any]` | `tuple[AsyncEngine, object, HistoryStorePort]` | checkpointer type is LangGraph internal, use `object` |
| `_start_runtime_metrics_exporter` return | `Any \| None` | `PrometheusMetricsExporter \| None` | import from `observability_factory` |
| `_stop_runtime_metrics_exporter` param | `Any \| None` | `PrometheusMetricsExporter \| None` | same |
| `_start_runtime_kpi_tasks` `sql_engine` | `Any \| None` | `AsyncEngine \| None` | already imported |
| `_build_chat_model_factory` return | `Any` | `ChatModelFactoryPort` | already imported from fred-sdk |
| `_write_turn_history` `history_store` | `Any` | `HistoryStorePort` | already imported |
| `_KPI_TURNS_BUFFER` element type | `dict[str, Any]` | `KpiTurnRecord` | moved to context in Phase 4 |
| `_AUDIT_EVENTS_BUFFER` element type | `dict[str, Any]` | `AuditEventRecord` | moved to context in Phase 4 |
| `AgentPodConfig._mcp_configuration` | `Any \| None` | `McpCatalogConfiguration \| None` | see below |
| `resume_payload` in `_AgentExecuteRequest` | `Any \| None` | keep `Any \| None` + comment | opaque graph-agent JSON blob |
| `context: dict[str, Any] \| None` in routes | `dict[str, Any] \| None` | keep — open runtime context bag | acceptable, document it |

### `McpCatalogConfiguration` (new file)

**File:** `fred_runtime/app/mcp_config.py`

```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class McpServerEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    url: str
    transport: str = "sse"
    description: str | None = None


class McpCatalogConfiguration(BaseModel):
    """
    Typed representation of mcp_catalog.yaml.
    extra="allow" is intentional: the catalog format is versioned externally.
    """
    model_config = ConfigDict(extra="allow")

    servers: list[McpServerEntry] = []
```

This replaces `Any | None` in:
- `AgentPodConfig._mcp_configuration: McpCatalogConfiguration | None`
- `AgentPodConfig.set_mcp_configuration(configuration: McpCatalogConfiguration | None) -> None`
- `AgentPodConfig.get_mcp_configuration() -> McpCatalogConfiguration | None`

### `user_token_refresher.py` typing

Also in scope for this phase (follow-up to Phase 1):
- `Any` and `Dict` imports → remove
- All function signatures must use concrete types: `dict[str, str]` for form
  data, `str` for token URL and return value

### Tests to write

**File:** `tests/test_mcp_config.py` *(new)*

```
test_mcp_catalog_configuration_parses_empty_servers
test_mcp_catalog_configuration_parses_server_entry
test_mcp_catalog_configuration_allows_extra_fields
test_agent_pod_config_set_and_get_mcp_configuration_roundtrip
test_agent_pod_config_mcp_configuration_defaults_to_none
```

**Coverage target:** 100% on `mcp_config.py` (pure Pydantic, trivially
testable).

### Validation

```bash
cd libs/fred-runtime
make code-quality   # basedpyright must report 0 new Any warnings at changed sites
uv run pytest tests/ -q
python -c "
from fred_runtime.app.config import AgentPodConfig
from fred_runtime.app.mcp_config import McpCatalogConfiguration
c = AgentPodConfig.model_validate({'security': {'m2m': {'enabled': False, 'realm_url': 'http://x', 'client_id': 'x'}, 'user': {'enabled': False, 'realm_url': 'http://x', 'client_id': 'x'}, 'authorized_origins': []}})
print(c.get_mcp_configuration())  # None
"
```

---

## Coverage Summary (target after all phases)

| Module / package | Target | Notes |
|---|---|---|
| `fred_runtime/common/kf_workspace_client.py` | 100% | Fully mockable |
| `fred_runtime/runtime_support/user_token_refresher.py` | 100% | Fully mockable |
| `fred_runtime/cli/pod_client.py` | ≥ 75% | HTTP paths need mock httpx |
| `fred_runtime/cli/kpi_display.py` | ≥ 80% | Pure functions, no I/O |
| `fred_runtime/cli/url_helpers.py` | 100% | Pure functions |
| `fred_runtime/cli/scenario.py` | ≥ 75% | Offline paths only |
| `fred_runtime/cli/completion.py` | ≥ 80% | Pure functions |
| `fred_runtime/cli/repl.py` | Exempt | Interactive I/O |
| `fred_runtime/cli/history_display.py` | Exempt | Terminal rendering |
| `fred_runtime/app/context.py` | ≥ 80% | Core container |
| `fred_runtime/app/container.py` | 100% | One function |
| `fred_runtime/app/dependencies.py` | ≥ 90% | Thin wiring |
| `fred_runtime/app/mcp_config.py` | 100% | Pure Pydantic |
| `fred_runtime/app/config.py` (changed lines) | ≥ 90% | Config model |

---

## Execution Order and Dependencies

```
Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4 ──► Phase 5
(1 h)       (1 h)       (3 h)       (4 h)       (2 h)
                        depends      depends
                        on P2        on P2, P3
                        conftest     conftest
```

Phases 1 and 2 are independent and can be done in either order.
Phase 3 must come after Phase 2 (uses shared conftest).
Phase 4 must come after Phase 2 (uses shared conftest) and can overlap with Phase 3.
Phase 5 can start in parallel with Phase 4 (touches different files).

**Total estimated effort:** 11 h

---

## Definition of Done

This backlog is closed when all of the following are true:

- `[x]` `make code-quality` passes with zero warnings in `libs/fred-runtime` ✅ Phase 1
- `[x]` New/modified files (P1–P5) report ≥ 70% coverage: `agent_app.py` 74%, `context.py` 95%, all new P4/P5 files 100% ✅ 2026-04-27
- `[x]` No `import requests` in any source file under `fred_runtime/` (excluding `.venv`) ✅ Phase 1
- `[x]` `from fred_runtime.client import AgentPodClient, run_scenario_file, main` still works (shim intact) ✅ 2026-04-27
- `[x]` `fred-agents-cli --help` resolves correctly ✅ 2026-04-27
- `[x]` All ring-buffer state is instance-level, not module-global ✅ Phase 4
- `[x]` `PodApplicationContext` is present and wired via `app.state` ✅ Phase 4
- `[ ]` `grep -r "Any" fred_runtime/ | grep -v "# opaque\|# open bag\|\.venv"` returns zero results on function boundaries — **deferred to R1b** (see below)
- `[ ]` No file in `fred_runtime/` exceeds 600 lines (excluding generated files) — **deferred to R1b** (see below)

---

## R1b — Remaining Quality Gates (Deferred)

**Status:** `[ ]` Not started
**Prerequisite:** R1 (P1–P5) complete ✅

Two DoD gates from R1 were not closed by P1–P5 and require dedicated follow-up work:

### Gate A — `Any` zero at function boundaries

Remaining `Any` usages after P5 (checked 2026-04-27):

| File | Location | Reason not fixed in P5 |
|---|---|---|
| `fred_runtime/runtime_context.py` | `chat_model_factory`, `checkpointer`, `history_store` fields | Typed as `Any` to avoid circular import; tracked comments in source |
| `fred_runtime/cli/pod_client.py` | `resume_payload`, return types for raw HTTP responses | Opaque JSON payloads — would need typed response DTOs |
| `fred_runtime/common/tool_node_utils.py` | `normalize_mcp_content(content: Any) -> Any` | Genuinely opaque MCP content bag |
| `fred_runtime/app/_catalogs.py` | `_load_yaml_mapping` | Raw YAML dict — `dict[str, Any]` is appropriate here |

**Fix approach:**
- `runtime_context.py`: Replace `Any | None` fields with proper types now that `HistoryStorePort`, `ChatModelFactoryPort`, and checkpointer protocols exist in `fred-sdk`. Needs careful circular-import analysis.
- `cli/pod_client.py`: Introduce response TypedDicts or dataclasses for `get_kpi_turns`, `get_audit_events`, `get_checkpoint_stats`.
- Utilities: Mark remaining `Any` with `# opaque` comment to satisfy the grep gate without removing them.

### Gate B — No file > 600 lines

Files currently over limit (checked 2026-04-27):

| File | Lines | Action needed |
|---|---|---|
| `fred_runtime/app/agent_app.py` | 2 578 | Split into router modules: `_execute_router.py`, `_session_router.py`, `_admin_router.py`; keep `agent_app.py` as composition root (< 200 lines) |
| `fred_runtime/integrations/v2_runtime/adapters.py` | 714 | Out of scope for R1; evaluate in a separate integrations quality pass |

**Fix approach for `agent_app.py`:**
1. Extract route handlers for `/agents/execute*` into `fred_runtime/app/routers/execute.py`
2. Extract `/agents/sessions*` into `fred_runtime/app/routers/sessions.py`
3. Extract `/agents/kpi-turns`, `/agents/audit-events` into `fred_runtime/app/routers/admin.py`
4. Keep `create_agent_app()` factory, lifespan, and shared helpers in `agent_app.py` (target: ~200 lines)
5. The OpenAI compat router is already separate (`openai_compat_router.py`) — no change needed there

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Circular import from `cli/` → `app/` | Medium | High | Rule: `cli/` imports only `fred_core`, `fred_sdk`, stdlib. Verify with `python -c "import fred_runtime.cli.repl"` before merge. |
| Boot-order regression in `lifespan` | Medium | High | The test `test_lifespan_attaches_container_to_app_state` must cover the full startup sequence. Do not reorder steps without updating the sequence comment. |
| `McpCatalogConfiguration` missing fields at runtime | Low | Medium | Use `extra="allow"` initially. After validating against a real catalog in staging, tighten to `extra="forbid"` in a follow-up. |
| Phase 4 makes ring buffers non-global → existing endpoints break | Low | High | The `/agents/kpi-turns` and `/agents/audit-events` endpoints must be updated to read from `get_pod_container(request).kpi_turns_buffer` instead of the module-level deque. Cover with `test_kpi_turns_endpoint_returns_buffer_contents`. |
