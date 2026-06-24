# Native `anthropic` Model Provider Implementation Plan

## Overview

Add a first-class `anthropic` model provider to `fred-core`'s chat-model factory,
backed by `langchain_anthropic.ChatAnthropic`. This makes "Claude through an
Anthropic-native gateway" (bearer token, e.g. Synapse / LiteLLM) **and** "direct
Anthropic API" (`x-api-key`) supported, documented paths — replacing the current
`openai`-provider-with-base-URL shim and the `vertex-ai-model-garden` ADC workaround.

The change is purely additive: one new enum member, one new factory branch, one new
auth helper, the `langchain-anthropic` dependency, and tests. No existing provider's
behaviour changes; no frozen type is modified.

## Fred Task ID

RUNTIME-07

## RFC & Backlog References

- RFC: `docs/swift/rfc/ANTHROPIC-NATIVE-PROVIDER-RFC.md` (status: **Proposed — awaiting
  developer confirmation 2026-06-22**; this plan assumes it is confirmed)
- Backlog: not yet created. Plan adds a `§RUNTIME-07` entry to
  `docs/swift/backlog/FRED-RUNTIME-QUALITY.md` (alongside RUNTIME-05/06 — see note in
  *Workflow prerequisites* about the file's stated scope)
- id-legend: not yet registered. Plan adds the `RUNTIME-07` row.
- GitHub issue: **TBD** — must be created before implementation (CLAUDE.md Step 3.5)

## Current State Analysis

`fred-core` builds chat models for six providers via a linear `if provider == ...`
chain in `get_model()` (`libs/fred-core/fred_core/model/factory.py:272-575`):

- **Enum** — `ModelProvider` (`libs/fred-core/fred_core/model/models.py:18-26`) lists
  six members, alphabetically ordered.
- **OpenAI branch** (`factory.py:321-339`) is the closest template: it calls
  `_require_env`, validates `cfg.name`, logs via `_info_provider`, and constructs the
  wrapper with `**base_kwargs` (shared httpx clients + timeout, built at
  `factory.py:315-319`) plus `**settings`.
- **OpenAI-compat normalizers** — `_normalize_openai_compat` and
  `_apply_openai_stream_usage_default` (`factory.py:239-264`) are gated to the
  OpenAI-family tuple (`factory.py:287-298`). Anthropic is excluded simply by **not**
  adding it to those tuples — `ChatAnthropic` streams token deltas natively and uses an
  Anthropic-native `base_url`, so the OpenAI shims must not touch it.
- **Lazy-import pattern** — Vertex branches (`factory.py:439-444`, `498-505`) import the
  provider package inside the branch and raise a clear `ImportError` if missing. The
  Anthropic branch follows this so `langchain-anthropic` stays optional at import time.
- **Auth helpers** — `_require_env(var)` (`factory.py:202-206`) raises `ValueError` on a
  missing env var. `_redact_settings` (`factory.py:174-185`) already redacts keys
  containing `token`/`authorization`/`key`, so a bearer header in `default_headers`
  logs safely *only if* the header key matches — verified below.
- **Structured chains** — `get_structured_chain` (`factory.py:768-805`) has a provider
  allowlist (`factory.py:774-780`) that opts a provider into native
  `with_structured_output(method="function_calling")`. Anthropic supports tool-calling,
  so it will be added to this set (confirmed in scope).
- **Dependency** — `libs/fred-core/pyproject.toml:28-33` pins `langchain-core>=1.3.0`
  and sibling `langchain-*` packages with `>=` lower bounds. `langchain-anthropic` is
  **not** declared. Latest release is `1.4.7` (requires `langchain-core>=1.4.7`).
- **Test pattern** — `libs/fred-core/fred_core/tests/model/test_embedding_factory.py`
  shows the offline pattern: build a fake module, inject via
  `monkeypatch.setitem(sys.modules, "<pkg>", fake_module)`, call the factory, assert on
  captured constructor kwargs. No network, no real SDK.
- **Existing Anthropic-via-Vertex path** (`factory.py:498-505`,
  `model_family: anthropic` → `ChatAnthropicVertex`) is untouched and stays.

## Desired End State

A model config of the following shape constructs a working `ChatAnthropic`:

```yaml
# Gateway (bearer auth)
chat_model:
  provider: anthropic
  name: claude-sonnet-4-5
  settings:
    base_url: https://llm.synapse.thalescloud.io
# env: ANTHROPIC_AUTH_TOKEN=<token>   (or ANTHROPIC_BASE_URL instead of settings.base_url)

# Direct Anthropic API (x-api-key auth)
chat_model:
  provider: anthropic
  name: claude-sonnet-4-5
# env: ANTHROPIC_API_KEY=<key>
```

Verifiable by: offline unit tests pass (`make test` in `libs/fred-core`), quality
checks pass, and the contract doc + tracking files reflect the new provider.

### Key Discoveries

- OpenAI branch template: `factory.py:321-339`.
- OpenAI-family gating tuples to leave unchanged: `factory.py:287-298`.
- Shared httpx stack assembled into `base_kwargs`: `factory.py:315-319`.
- Lazy-import + `ImportError` pattern: `factory.py:439-444`.
- `_require_env`: `factory.py:202-206`; `_info_provider`: `factory.py:188-194`.
- Redaction substrings include `"authorization"` and `"token"`: `factory.py:174`.
- Structured-output allowlist: `factory.py:774-780`.
- Offline test harness pattern: `test_embedding_factory.py:30-65`.

## What We're NOT Doing

- **No `auth_token_env` settings field** (RFC §3.4 open question) — env-var-only, per
  RFC default and confirmed decision. Bearer token comes from `ANTHROPIC_AUTH_TOKEN`
  only. An explicit `api_key` / `default_headers` in `settings` remains the escape hatch.
- **No Anthropic embeddings** — Anthropic ships no embeddings API. `get_embeddings` is
  untouched.
- **No Bedrock Claude** (`ChatBedrock`) — out of scope.
- **No change to `vertex-ai-model-garden` Anthropic support** — it stays as-is.
- **No frozen-type changes** — `ModelConfiguration` (`provider`/`name`/`settings`)
  already covers the new provider.
- **No OpenAI shim applied to Anthropic** — `_normalize_openai_compat` and
  `_apply_openai_stream_usage_default` stay OpenAI-family only.

## Implementation Approach

Five mechanical changes mirroring established factory patterns, then tests, then docs
and tracking sync. Auth resolution is the one piece of real logic, isolated in a small
testable helper `_apply_anthropic_auth(settings)`.

---

## Phase 0: Workflow prerequisites (tracking + dependency)

### Overview

Satisfy CLAUDE.md Steps 2–3.5 before code: register the ID, add the backlog entry,
create the GitHub issue, and declare the dependency. The RFC (Step 1) already exists.

### Changes Required

#### 1. Task ID registry
**File**: `docs/swift/data/id-legend.yaml`
**Changes**: Add a `RUNTIME-07` row after RUNTIME-06:

```yaml
  - id: RUNTIME-07
    title: "Native anthropic model provider — gateway base-URL + bearer-token auth"
    status: in-progress
    owner: Dimitri
    refs:
      rfc: "docs/swift/rfc/ANTHROPIC-NATIVE-PROVIDER-RFC.md"
      backlog: "docs/swift/backlog/FRED-RUNTIME-QUALITY.md §RUNTIME-07"
      issue: "<github issue URL once created>"
    notes: >
      Adds ANTHROPIC member to ModelProvider and an anthropic branch in
      fred-core get_model() backed by langchain_anthropic.ChatAnthropic. Supports
      an Anthropic-native gateway (ANTHROPIC_AUTH_TOKEN bearer) and direct Anthropic
      API (ANTHROPIC_API_KEY / x-api-key). base_url precedence: settings.base_url >
      ANTHROPIC_BASE_URL env > SDK default. Additive — no existing provider changes.
```

#### 2. Sprint registry
**File**: `docs/swift/data/sprint.yaml`
**Changes**: Add a RUNTIME-07 entry consistent with the existing format (id, title,
owner; `closed` added at close-out).

#### 3. Backlog entry
**File**: `docs/swift/backlog/FRED-RUNTIME-QUALITY.md`
**Changes**: Add a `## §RUNTIME-07 — Native anthropic provider` section after
RUNTIME-06, modelled on the RUNTIME-06 entry (ID / RFC / Status / Goal / Deliverables
checkboxes / Non-changes). **Scope note:** this file is headed *"Scope: libs/fred-core
… libs/fred-runtime only"*; RUNTIME-07 is a `libs/fred-core` change. It is placed here
for RUNTIME-track ID-lookup consistency (siblings RUNTIME-05/06 live here); add a
one-line note in the entry acknowledging the fred-core scope. *(If the developer
prefers `BACKLOG.md` per the RFC's reference, move it there instead — flagged for
confirmation.)*

#### 4. PMO board
**File**: `docs/swift/PMO-BOARD.md`
**Changes**: Add/sync a RUNTIME-07 row (owner, status, backlog ref, RFC ref, execution
ref = GitHub issue once known).

#### 5. GitHub issue
**Action**: Create an issue linking task ID RUNTIME-07, the RFC, and the backlog entry
(CLAUDE.md Step 3.5). Record the URL back into id-legend / backlog / PMO board.

#### 6. Dependency
**File**: `libs/fred-core/pyproject.toml`
**Changes**: Add to the dependency list (after `langchain-openai`):

```toml
    "langchain-anthropic>=1.0.0",
```

`>=1.0.0` matches the repo's `>=` lower-bound convention and stays within the
langchain-core 1.x line. The resolver will pull a compatible `langchain-core` (the
latest `langchain-anthropic` requires `>=1.4.7`, compatible with the existing
`>=1.3.0` floor). Run the project's lock/sync step and record the command used.

### Success Criteria

#### Automated Verification:
- [x] `langchain_anthropic` importable in the `fred-core` env after sync:
      `python -c "import langchain_anthropic; print(langchain_anthropic.__version__)"`
- [x] `id-legend.yaml` and `sprint.yaml` parse (no YAML errors): covered by
      `make code-quality` / existing yaml checks if present, else `python -c "import yaml,sys; yaml.safe_load(open('docs/swift/data/id-legend.yaml'))"`

#### Manual Verification:
- [ ] GitHub issue exists and is linked in id-legend / backlog / PMO board
- [ ] Developer has confirmed the RFC (status flipped from "Proposed")

**Implementation Note**: Pause here for confirmation that the RFC is approved and the
issue exists before writing code.

---

## Phase 1: Enum member

### Overview
Add the `ANTHROPIC` provider value.

### Changes Required

#### 1. ModelProvider enum
**File**: `libs/fred-core/fred_core/model/models.py`
**Changes**: Add `ANTHROPIC = "anthropic"` as the first member (alphabetical):

```python
class ModelProvider(Enum):
    """Enumeration of model providers available in the system."""

    ANTHROPIC = "anthropic"
    AZURE_APIM = "azure-apim"
    AZURE_OPENAI = "azure-openai"
    OLLAMA = "ollama"
    OPENAI = "openai"
    VERTEX_AI = "vertex-ai"
    VERTEX_AI_MODEL_GARDEN = "vertex-ai-model-garden"
```

### Success Criteria

#### Automated Verification:
- [x] `make code-quality` passes in `libs/fred-core`
- [x] `python -c "from fred_core.model.models import ModelProvider; assert ModelProvider.ANTHROPIC.value == 'anthropic'"`

---

## Phase 2: Auth helper + factory branch

### Overview
Add the `_apply_anthropic_auth` helper and the `anthropic` branch in `get_model()`.

### Changes Required

#### 1. Auth helper
**File**: `libs/fred-core/fred_core/model/factory.py` (near other small helpers,
after `_require_settings`, ~line 215)
**Changes**:

```python
def _apply_anthropic_auth(settings: Dict[str, Any]) -> None:
    """
    Resolve Anthropic auth into `settings`, in-place.

    Precedence:
    1. Explicit `api_key` or `default_headers` already in settings → leave as-is
       (escape hatch; caller knows what it's doing).
    2. ANTHROPIC_AUTH_TOKEN set → inject `Authorization: Bearer <token>` via
       default_headers (Anthropic-native gateway, e.g. Synapse/LiteLLM). No
       ANTHROPIC_API_KEY required.
    3. Else require ANTHROPIC_API_KEY (sent by the SDK as x-api-key) — direct
       Anthropic API mode.
    """
    if settings.get("api_key") or settings.get("default_headers"):
        return
    token = os.getenv("ANTHROPIC_AUTH_TOKEN", "")
    if token:
        settings["default_headers"] = {"Authorization": f"Bearer {token}"}
        return
    _require_env("ANTHROPIC_API_KEY")
```

#### 2. Factory branch
**File**: `libs/fred-core/fred_core/model/factory.py` (insert before the OpenAI
branch at `factory.py:321`, keeping provider order roughly alphabetical)
**Changes**:

```python
    # --- Provider: Anthropic (direct API or Anthropic-native gateway) ---
    if provider == ModelProvider.ANTHROPIC.value:
        if not cfg.name:
            raise ValueError(
                "Anthropic chat requires 'name' (model id, e.g., claude-sonnet-4-5)."
            )
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError as e:
            raise ImportError(
                "Provider 'anthropic' requires package 'langchain-anthropic'."
            ) from e

        # base_url: explicit setting wins, else ANTHROPIC_BASE_URL env, else SDK default.
        base_url = settings.pop("base_url", None) or os.getenv("ANTHROPIC_BASE_URL")
        if base_url:
            settings["base_url"] = base_url

        _apply_anthropic_auth(settings)
        _info_provider(cfg, settings)
        logger.info(
            "[MODEL][ANTHROPIC] Constructing ChatAnthropic model=%s base_url=%s timeout=%s",
            cfg.name,
            settings.get("base_url", "<sdk-default>"),
            base_kwargs.get("timeout"),
        )
        return ChatAnthropic(model=cfg.name, **base_kwargs, **settings)
```

**Note**: `anthropic` is deliberately absent from the OpenAI-family tuples at
`factory.py:287-298` — no change needed there. Confirm `_redact_settings` masks the
bearer header: the key `"Authorization"` contains `"authorization"` (lowercased match
at `factory.py:174`), so `default_headers` value is **not** auto-redacted because
redaction is keyed on the top-level setting name `default_headers`, which does not
match. **Action:** verify the logged line does not leak the token — if `default_headers`
is logged verbatim, add `"default_headers"` handling or pop it from the log copy.
(Tracked as an explicit check in this phase's manual verification.)

### Success Criteria

#### Automated Verification:
- [x] `make code-quality` passes in `libs/fred-core`
- [x] `make test` passes (existing tests unaffected)

#### Manual Verification:
- [x] `_info_provider` log uses a safe copy with `default_headers` replaced by `***REDACTED***` — bearer token does not leak.

**Implementation Note**: Pause after automated verification before Phase 3.

---

## Phase 3: Structured-output allowlist

### Overview
Opt Anthropic into native `with_structured_output(method="function_calling")`.

### Changes Required

#### 1. get_structured_chain allowlist
**File**: `libs/fred-core/fred_core/model/factory.py:774-780`
**Changes**: Add `ModelProvider.ANTHROPIC.value` to the provider set:

```python
    if provider in {
        ModelProvider.ANTHROPIC.value,
        ModelProvider.OPENAI.value,
        ModelProvider.AZURE_OPENAI.value,
        ModelProvider.AZURE_APIM.value,
        ModelProvider.VERTEX_AI.value,
        ModelProvider.VERTEX_AI_MODEL_GARDEN.value,
    }:
```

The existing `try/except` already falls back to prompt-based parsing if
`with_structured_output` raises, so this is safe.

### Success Criteria

#### Automated Verification:
- [x] `make code-quality` passes
- [x] `make test` passes

---

## Phase 4: Tests

### Overview
Offline unit tests for the new branch, modelled on `test_embedding_factory.py`
(fake module via `monkeypatch.setitem(sys.modules, "langchain_anthropic", ...)`).

### Changes Required

#### 1. New test file
**File**: `libs/fred-core/fred_core/tests/model/test_anthropic_factory.py`
**Changes**: Cover (RFC §6):

- Construction of `ChatAnthropic` for `provider: anthropic` with `name` (assert
  `model=` and presence of `base_kwargs` http clients/timeout).
- `base_url` precedence: explicit `settings.base_url` wins over `ANTHROPIC_BASE_URL`
  env; env used when settings omits it; neither → no `base_url` kwarg passed.
- Auth mode A: `ANTHROPIC_AUTH_TOKEN` set (no `ANTHROPIC_API_KEY`) → constructs and
  `default_headers == {"Authorization": "Bearer <token>"}`.
- Auth mode B: only `ANTHROPIC_API_KEY` set → constructs, no `Authorization` header.
- Escape hatch: explicit `settings.default_headers` / `api_key` preserved, no token
  injected.
- Missing both auth inputs → `ValueError` (from `_require_env`).
- Missing `name` → `ValueError`.
- `anthropic` does **not** receive OpenAI shims (no `openai_api_base`, no forced
  `streaming`/`stream_usage` keys in captured kwargs).

Each test sets/clears env via `monkeypatch.setenv` / `monkeypatch.delenv` so cases
don't leak. Inject a fake `ChatAnthropic` capturing `**kwargs`.

### Success Criteria

#### Automated Verification:
- [x] `make test` passes in `libs/fred-core` (13 new tests green, 198 total)
- [x] `make code-quality` passes

---

## Phase 5: Config sample + docs + tracking close-out

### Overview
Add a working catalog reference, the contract §8 entry, and sync all tracking docs.

### Changes Required

#### 1. Catalog profile (working reference)
**File**: `apps/fred-agents/config/models_catalog.yaml`
**Changes**: Add a `chat.anthropic.claude` profile (not set as a default; left as a
reference operators can point `default_profile_by_capability` at):

```yaml
  - profile_id: chat.anthropic.claude
    capability: chat
    description: "Claude via Anthropic-native gateway (bearer) or direct API (x-api-key)."
    model:
      provider: anthropic
      name: claude-sonnet-4-5
      # Gateway: set ANTHROPIC_AUTH_TOKEN (and base_url below or ANTHROPIC_BASE_URL env).
      # Direct API: set ANTHROPIC_API_KEY and omit base_url.
      settings:
        base_url: https://llm.synapse.thalescloud.io
```

#### 2. Contract doc — dated §8 entry
**File**: `docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md` (new subsection after §8.8)
**Changes**: Add `### 8.9 ✅ Native anthropic provider — RUNTIME-07 (June 2026)`
documenting the new provider value, the base_url precedence, the two auth modes, and
the explicit statement that no existing provider behaviour changed.

#### 3. Tracking close-out
**Files**: `docs/swift/data/id-legend.yaml` (status → done, `closed` date, issue URL),
`docs/swift/data/sprint.yaml` (`closed`), `FRED-RUNTIME-QUALITY.md §RUNTIME-07`
(check the `[ ]` deliverables `[x]`, set Status ✅ Complete), `docs/swift/STATUS.md`
(add/update row), `docs/swift/PMO-BOARD.md` (status + execution ref = PR).

### Success Criteria

#### Automated Verification:
- [x] `make code-quality` and `make test` pass repo-wide for touched modules
- [x] YAML files parse

#### Manual Verification:
- [ ] (If a live stack is available) constructing the `chat.anthropic.claude` profile
      against a real gateway with `ANTHROPIC_AUTH_TOKEN` returns a Claude completion.
- [ ] Direct-API mode with `ANTHROPIC_API_KEY` returns a completion.
- [ ] All tracking docs agree on status (convergence check).

---

## Testing Strategy

### Unit Tests (offline, no network — primary)
All in `libs/fred-core/fred_core/tests/model/test_anthropic_factory.py`, per Phase 4.
Fake `ChatAnthropic` module injected via `sys.modules`; assert on captured kwargs.
Edge cases: base_url precedence (3 cases), auth mode A/B, escape hatch, missing auth,
missing name, no-OpenAI-shim.

### Integration Tests
None automated (would require a live Anthropic gateway / API key). Covered by the
manual verification steps in Phase 5.

### Manual Testing Steps
1. Set `ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN`, configure the
   `chat.anthropic.claude` profile, send a chat turn → expect a Claude response over
   the gateway, no `OPENAI_API_KEY` needed.
2. Unset gateway vars, set `ANTHROPIC_API_KEY`, omit `base_url` → expect direct-API
   completion via `x-api-key`.
3. Unset both → expect a clear `ValueError` naming `ANTHROPIC_API_KEY`.

## Doc Update Checklist (from CLAUDE.md §Step 6)
- [x] Backlog item marked `[x]` (`FRED-RUNTIME-QUALITY.md §RUNTIME-07`)
- [x] Contract doc updated — `RUNTIME-EXECUTION-CONTRACT.md §8.9`
- [x] `docs/swift/STATUS.md` row — no row existed; N/A
- [x] `docs/swift/data/id-legend.yaml` status → done
- [x] `docs/swift/data/sprint.yaml` `closed` set
- [x] `docs/swift/PMO-BOARD.md` row updated (execution ref = branch `1802-runtime-07`)
- [x] UX component status — N/A (no UI change)

## References
- RFC: `docs/swift/rfc/ANTHROPIC-NATIVE-PROVIDER-RFC.md`
- Template branch (OpenAI): `libs/fred-core/fred_core/model/factory.py:321-339`
- Lazy-import pattern: `libs/fred-core/fred_core/model/factory.py:439-444`
- OpenAI-family gating to leave unchanged: `factory.py:287-298`
- Structured-output allowlist: `factory.py:774-780`
- Offline test harness: `libs/fred-core/fred_core/tests/model/test_embedding_factory.py`
- Sibling backlog entries: `docs/swift/backlog/FRED-RUNTIME-QUALITY.md §RUNTIME-05/06`
