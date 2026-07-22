# RFC: Native `anthropic` Model Provider (gateway base-URL + bearer-token auth)

**Status:** Done
**Author:** GOYAL Jaidev
**Task ID:** RUNTIME-07
**Scope:** `fred-core` model layer — `ModelProvider` enum
(`libs/fred-core/fred_core/model/models.py`), chat model factory
(`libs/fred-core/fred_core/model/factory.py`), `langchain-anthropic` dependency
(`libs/fred-core/pyproject.toml`)
**Related:** `docs/swift/backlog/BACKLOG.md` (RUNTIME track),
`docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md §8`,
`docs/swift/data/id-legend.yaml`

---

## 1. Problem

`fred-core` can construct chat models for six providers
(`azure-apim`, `azure-openai`, `ollama`, `openai`, `vertex-ai`,
`vertex-ai-model-garden`). Anthropic Claude models are reachable **only** through
`vertex-ai-model-garden` with `model_family: anthropic`, which builds
`ChatAnthropicVertex` and authenticates with Google Application Default
Credentials (`factory.py:498-505`).

This excludes a common deployment shape: an **Anthropic-native gateway** — e.g. the
Thales Synapse Gateway (a LiteLLM router) — that exposes the Anthropic Messages API
at a custom base URL and authenticates with a bearer token:

```
ANTHROPIC_BASE_URL=https://llm.synapse.thalescloud.io
ANTHROPIC_AUTH_TOKEN=<token>
```

There is no provider in fred that maps onto this. The only workaround today is to
declare `provider: openai` and point `base_url` at the gateway's
OpenAI-compatible route. That works but is a shim:

- Wrong API surface — Claude is driven through the OpenAI Chat Completions schema,
  not the Anthropic Messages schema.
- No access to Anthropic-specific behaviour the rest of fred already accounts for
  (extended-thinking blocks, prompt caching, Anthropic tool-use shape — see the
  thinking passthrough referenced in `id-legend.yaml` RUNTIME entries).
- Confusing configuration — operators must set `OPENAI_API_KEY` to an Anthropic
  gateway token and reason about which compatibility layer the gateway implements.

## 2. Goal

Make "Claude through an Anthropic-native gateway" a first-class, documented path by
adding an `anthropic` provider backed by `langchain_anthropic.ChatAnthropic`, with:

1. configurable base URL (gateway endpoint), and
2. auth that works for **both** a bearer-token gateway (`ANTHROPIC_AUTH_TOKEN`) and
   direct Anthropic API access (`ANTHROPIC_API_KEY`).

Non-goals:

- Anthropic embeddings (Anthropic ships no embeddings API — out of scope).
- Bedrock-hosted Claude (`ChatBedrock`) — a separate provider if ever required.
- Replacing or deprecating `vertex-ai-model-garden` Anthropic support — it stays.

## 3. Proposed solution

### 3.1 Dependency

Add `langchain-anthropic` to `libs/fred-core/pyproject.toml`. It is **not** currently
declared or installed (only appears in third-party docstrings under `.venv`). Pin to a
version aligned with the repo's existing `langchain-core`.

### 3.2 Enum

Add one member to `ModelProvider` (`models.py:18-26`):

```python
class ModelProvider(Enum):
    ANTHROPIC = "anthropic"          # new
    AZURE_APIM = "azure-apim"
    AZURE_OPENAI = "azure-openai"
    OLLAMA = "ollama"
    OPENAI = "openai"
    VERTEX_AI = "vertex-ai"
    VERTEX_AI_MODEL_GARDEN = "vertex-ai-model-garden"
```

### 3.3 Factory branch

Add a branch in `get_model()` (`factory.py`), modelled on the OpenAI branch
(`factory.py:321-339`) so it reuses the shared httpx stack (`base_kwargs`:
`http_client`, `http_async_client`, `timeout`) and the `settings` dict. Lazy import
keeps the dependency optional at import time, matching the Vertex pattern.

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

    # base_url: explicit setting wins, else ANTHROPIC_BASE_URL, else SDK default.
    base_url = settings.pop("base_url", None) or os.getenv("ANTHROPIC_BASE_URL")
    if base_url:
        settings["base_url"] = base_url

    _apply_anthropic_auth(settings)   # see §3.4
    _info_provider(cfg, settings)
    return ChatAnthropic(model=cfg.name, **base_kwargs, **settings)
```

Note: `base_url` is Anthropic-native, so this provider is **excluded** from the
OpenAI `_normalize_openai_compat` / `_apply_openai_stream_usage_default` passes
(`factory.py:287-298`) — those remain OpenAI-family only. `ChatAnthropic` streams
token deltas without the `streaming`/`stream_usage` shim.

### 3.4 Auth resolution — the one real design decision

`langchain_anthropic.ChatAnthropic` authenticates with `anthropic_api_key`
(env `ANTHROPIC_API_KEY`), which the Anthropic SDK sends as the **`x-api-key`**
header. Anthropic-native gateways such as Synapse/LiteLLM instead expect a
**bearer** `Authorization: Bearer <token>` header, which the SDK populates from
`ANTHROPIC_AUTH_TOKEN`. These are two distinct auth modes and must not be conflated.

Proposed precedence, implemented in a small helper `_apply_anthropic_auth(settings)`:

1. If `ANTHROPIC_AUTH_TOKEN` is set → pass it as a bearer header via
   `default_headers={"Authorization": f"Bearer {token}"}` and do **not** require
   `ANTHROPIC_API_KEY`. (Gateway mode.)
2. Else require `ANTHROPIC_API_KEY` via `_require_env` and let `ChatAnthropic`
   send it as `x-api-key`. (Direct Anthropic API mode.)
3. An explicit `api_key` / `default_headers` in `settings` always wins (escape hatch).

This keeps direct-to-Anthropic usage on the standard `x-api-key` path while making
the bearer-token gateway a supported first-class case. The env var names
deliberately match what the Anthropic SDK and tools like Claude Code already use, so
an existing `ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN` environment works unchanged.

> Open question for review: do we want to also accept the token via a model
> `settings` field (e.g. `auth_token_env`) for parity with the eval backend's
> `api_key_env` pattern, or is env-var-only sufficient for the runtime? Default
> proposal: env-var-only for now (smallest surface); add `auth_token_env` later if a
> multi-gateway need appears.

### 3.5 Target configuration (illustrative)

Gateway (Synapse / LiteLLM, bearer auth):

```yaml
chat_model:
  provider: anthropic
  name: claude-sonnet-4-5
  settings:
    base_url: https://llm.synapse.thalescloud.io
# env: ANTHROPIC_AUTH_TOKEN=<gateway token>
# (ANTHROPIC_BASE_URL env also honored if base_url omitted from settings)
```

Direct Anthropic API (x-api-key auth):

```yaml
chat_model:
  provider: anthropic
  name: claude-sonnet-4-5
# env: ANTHROPIC_API_KEY=<key>
```

## 4. Impact on existing contracts

- **`RUNTIME-EXECUTION-CONTRACT.md`** — adds one supported provider value; no change
  to any existing provider's behaviour. Requires a dated entry in §8.
- **`ModelConfiguration`** (`fred-core/common/structures.py`) — unchanged; the new
  provider uses the existing `provider` / `name` / `settings` fields.
- **No frozen type is modified.** The change is additive: a new enum member and a new
  factory branch. Existing configs and providers are untouched.

## 5. Alternatives considered

1. **Keep using the `openai` provider with a base URL (status quo).** Zero code, works
   today, but is a compatibility shim with the drawbacks in §1. Remains valid as an
   interim/escape path; this RFC does not remove it.
2. **Route everything through `vertex-ai-model-garden`.** Requires GCP project + ADC;
   does not serve an Anthropic-native gateway keyed by a bearer token. Wrong auth
   model for the target deployment.
3. **A dedicated `litellm` provider in the runtime** (as the eval backend has). More
   general, but heavier: it reintroduces an OpenAI-compatibility translation layer and
   does not give the native Anthropic Messages surface. A native `anthropic` provider
   is the smaller, more direct change and composes with any Anthropic-native gateway,
   LiteLLM included.

## 6. Testing

Offline unit tests in `libs/fred-core` (no network):

- Construction of `ChatAnthropic` for `provider: anthropic` with a `name`.
- `base_url` precedence: explicit `settings.base_url` > `ANTHROPIC_BASE_URL` env > none.
- Auth mode A: `ANTHROPIC_AUTH_TOKEN` set → bearer `default_headers` injected, no
  `ANTHROPIC_API_KEY` required.
- Auth mode B: only `ANTHROPIC_API_KEY` set → constructs, no bearer header.
- Missing both auth inputs → `ValueError` from `_require_env`.
- Missing `name` → `ValueError`.

## 7. Rollout / docs checklist

- [ ] `langchain-anthropic` added to `libs/fred-core/pyproject.toml`
- [ ] `ANTHROPIC` member added to `ModelProvider`
- [ ] `anthropic` branch + `_apply_anthropic_auth` helper in `factory.py`
- [ ] Unit tests (§6)
- [ ] Dated entry in `RUNTIME-EXECUTION-CONTRACT.md §8`
- [ ] Config example in the relevant `configuration.yaml` sample(s)
- [ ] `id-legend.yaml` RUNTIME-07 row + BACKLOG.md item marked done
- [ ] GitHub issue kept current (execution ref = PR → branch, closed on ship)
