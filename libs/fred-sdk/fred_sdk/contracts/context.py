# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Context and capability payloads shared by the v2 runtime surface.

Why this module exists:
- keep portable execution context and typed capability payloads explicit
- give v2 runtimes one Fred-owned contract for tool calls, artifact publication,
  and resource reads
- make the current migration state visible: `portable_context` is the preferred
  long-term contract, while `runtime_context` remains a transitional compatibility
  bridge for existing Fred behavior that has not been ported yet

How to use:
- prefer `PortableContext` when propagating tracing, identity, and small portable
  execution metadata
- prefer explicit request/result models (e.g. `ToolInvocationRequest`) over direct
  service or storage client access
- use `BoundRuntimeContext.runtime_context` only when one existing Fred behavior
  still depends on legacy runtime fields and no narrower v2 capability exists yet

Example:
- `binding.portable_context.session_id`
- `await services.workspace_fs.read_text("shared/templates/template.md")`
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Dict, Literal, Optional
from urllib.parse import urlsplit

from fred_core.model.models import ModelProvider
from fred_core.store import VectorSearchHit
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

# NOTE: This module is the canonical home for portable context + UI parts.
# Keep Link/Geo parts and RuntimeContext here to avoid circular imports.


class LinkKind(str, Enum):
    citation = "citation"  # source supporting the answer
    download = "download"  # file to fetch (pdf, csv, etc.)
    external = "external"  # generic external link
    dashboard = "dashboard"  # e.g., Grafana, Kibana
    related = "related"  # further reading
    view = "view"  # for pdf preview


class LinkPart(BaseModel):
    """
    Why this exists:
      - The UI needs a typed, explicit way to render links without parsing free text.
      - Lets agents express intent (citation/download/etc.) so the UI can group + style.
    """

    type: Literal["link"] = "link"
    href: Optional[str] = None  # absolute URL
    title: Optional[str] = None  # human label; fallback to href if None
    kind: LinkKind = LinkKind.external
    rel: Optional[str] = None  # e.g. "noopener", "noreferrer", "ugc"
    mime: Optional[str] = None  # e.g. "application/pdf"
    source_id: Optional[str] = None
    # ^ if this link corresponds to a VectorSearchHit (metadata.sources),
    #   set source_id = hit.id so the UI can cross-highlight.
    document_uid: Optional[str] = None
    file_name: Optional[str] = None


class GeoPart(BaseModel):
    """
    Why this exists:
      - Maps shouldn't be 'imagined' from text. We carry real data (GeoJSON FeatureCollection)
        so the UI can render it with Leaflet immediately.
      - Optional presentation hints keep style logic minimal in the UI.
    """

    type: Literal["geo"] = "geo"
    # Strict GeoJSON to avoid format proliferation; agents must normalize before emitting.
    # Expecting: {"type":"FeatureCollection","features":[...]}
    geojson: Dict[str, Any]
    # Optional UI hints; the UI should treat all as best-effort:
    popup_property: Optional[str] = None  # property to show in popups if present
    fit_bounds: bool = True  # auto-fit map to the features
    style: Optional[Dict[str, Any]] = None
    # e.g. {"weight":2,"opacity":0.8,"fillOpacity":0.1}


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)


class ModelCapability(str, Enum):
    """
    Capability = technical model family.

    `chat` is the active agent-routing capability. `embedding` is retained for
    consumers that require an embeddings client and for a future dedicated
    policy surface. `language` is a legacy value kept for public-contract
    compatibility; first-party catalogs no longer publish it. `image` remains
    reserved until a typed production consumer exists.

    Canonical home for this enum (relocated from
    `fred_runtime.model_routing.contracts`, which re-imports and re-exports it
    unchanged): `fred_runtime`'s model-routing catalog/resolver classify
    `kind="model"` capability entries by this enum across the deployment.
    Control-plane's platform-model-binding admin surface (`ModelBinding`
    below) does NOT use this enum — that API is chat-only and represents its
    one capability as a route-local `Literal["chat"]` constant, not this
    type.
    """

    CHAT = "chat"
    LANGUAGE = "language"
    EMBEDDING = "embedding"
    IMAGE = "image"


def _validate_http_url_no_userinfo(value: str) -> str:
    """Shared validator for every URL field a `ModelBinding` can carry.

    Structural, not heuristic: only `http`/`https` schemes are accepted, and a
    URL carrying `user:pass@host` userinfo is rejected outright — one of the
    structural guarantees `ModelBindingSettings` makes (see `ModelBinding`
    below for the exact boundary this does and does not close).
    """
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise ValueError(f"Malformed URL: {value!r} ({exc})") from exc
    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"URL must use http or https, got scheme {parsed.scheme!r}: {value!r}"
        )
    if not parsed.hostname:
        raise ValueError(f"URL must have a host: {value!r}")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"URL must not contain username/password userinfo: {value!r}")
    return value


HttpUrlNoUserinfo = Annotated[str, AfterValidator(_validate_http_url_no_userinfo)]


def _validate_supported_chat_provider(value: str) -> str:
    """AfterValidator restricting `ModelBinding.provider` to a provider
    `fred_core.model.factory.get_model()` can actually construct a chat
    client for — the canonical `fred_core.model.models.ModelProvider` enum,
    not a hand-maintained duplicate allowlist. Kept as a `str` field (not
    the enum type itself) so the wire/JSON shape is unchanged; this
    validator is the only place the allowlist is enforced. An unsupported
    value (e.g. a typo, or a stale/forged provider name) is rejected here,
    before persistence — not left to fail at runtime model construction on
    every subsequent managed turn.
    """
    supported = {p.value for p in list(ModelProvider)}
    if value not in supported:
        raise ValueError(
            f"Unsupported provider {value!r}; must be one of {sorted(supported)}"
        )
    return value


SupportedChatProvider = Annotated[
    str, AfterValidator(_validate_supported_chat_provider)
]

# Shared numeric bounds for `ModelBindingSettings` — strict (no bool/str
# coercion into int/float/bool):
# - `max_tokens` has no meaningful non-positive value to forward to a chat
#   completion call.
# - `top_p` is the standard nucleus-sampling domain shared by every
#   OpenAI-compatible provider `get_model()` supports.
# - `max_retries` and `request_timeout` have no meaningful negative value.
_StrictNonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
_StrictPositiveInt = Annotated[int, Field(strict=True, gt=0)]
_StrictFiniteFloat = Annotated[float, Field(strict=True, allow_inf_nan=False)]
_StrictNonNegativeFiniteFloat = Annotated[
    float, Field(strict=True, ge=0, allow_inf_nan=False)
]
_StrictUnitIntervalFloat = Annotated[
    float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)
]


class ModelBindingSettings(FrozenModel):
    """
    Strict settings a platform-operator `ModelBinding` may carry — every
    field is a named, typed generation knob (see `ModelBinding`'s docstring
    for the exact credential-shape guarantee this type does and does not
    make).

    Every field here is evidenced by `fred_core.model.factory.get_model()`:
    either a key that function reads/pops explicitly for a supported chat
    provider, or a generation knob (`temperature`/`max_tokens`/`top_p`) it
    forwards unchanged to the underlying LangChain chat-model wrapper.
    `extra="forbid"` (via `FrozenModel`) makes every other key — including a
    credential-designated name like `api_key`, or a generic passthrough
    container like `headers`/`cookies`/`auth`/`client` — a hard rejection at
    construction time, not a heuristic warning: there is no field shaped to
    receive one, so there is nothing for a word-list heuristic to police.
    Numeric and boolean fields are strict (no `"4096"` -> `4096`, no `1` ->
    `True`) and range-checked where a downstream consumer enforces a bound
    (see the field groups below) — the type a caller sends is the type
    persisted and returned, never silently rewritten.

    `timeout` and `http_client_limits` are deliberately not fields here.
    `fred_core.model.http_clients.get_shared_stack()` builds one process-wide
    HTTP client stack on its first call and logs-and-ignores every later
    tuning request from a subsequent call — an admin changing either value
    through this binding would look accepted but never actually take effect
    on an already-running pod, contradicting the "takes effect on the very
    next turn" guarantee the rest of this binding makes. Process-wide
    transport tuning stays pod-local, set once at pod boot through
    `ModelConfiguration.settings` in `models_catalog.yaml`. `request_timeout`
    stays here because `get_model()` applies it fresh at every model
    construction, not through the shared singleton.

    Field groups (by the provider(s) that read them in `get_model()`):
    - OpenAI / Azure OpenAI / Ollama / Anthropic: `base_url`
    - Azure OpenAI: `azure_endpoint`, `azure_openai_api_version`
    - Azure APIM: `azure_ad_client_id`, `azure_ad_client_scope`,
      `azure_apim_base_url`, `azure_apim_resource_path`, `azure_tenant_id`,
      `azure_openai_api_version`
    - Vertex AI / Vertex AI Model Garden: `project`, `location`
    - Vertex AI Model Garden only: `model_family`
    - Generation behavior (all OpenAI-compatible providers):
      `temperature`, `max_tokens` (must be positive), `top_p` (0-1),
      `max_retries` (>= 0), `streaming`, `stream_usage`, `request_timeout`
      (>= 0)

    A provider with additional required settings (`azure-openai`,
    `azure-apim`, `vertex-ai`, `vertex-ai-model-garden`) is enforced by
    `ModelBinding`'s own cross-field validator, not by making any field here
    unconditionally required — most of these fields are only meaningful for
    a subset of providers.
    """

    base_url: HttpUrlNoUserinfo | None = None
    azure_endpoint: HttpUrlNoUserinfo | None = None
    azure_openai_api_version: str | None = None
    azure_ad_client_id: str | None = None
    azure_ad_client_scope: str | None = None
    azure_apim_base_url: HttpUrlNoUserinfo | None = None
    azure_apim_resource_path: str | None = None
    azure_tenant_id: str | None = None
    project: str | None = None
    location: str | None = None
    model_family: Literal["mistral", "llama", "anthropic", "claude"] | None = None
    temperature: _StrictFiniteFloat | None = None
    max_tokens: _StrictPositiveInt | None = None
    top_p: _StrictUnitIntervalFloat | None = None
    max_retries: _StrictNonNegativeInt | None = None
    streaming: bool | None = Field(default=None, strict=True)
    stream_usage: bool | None = Field(default=None, strict=True)
    request_timeout: _StrictNonNegativeFiniteFloat | None = None


# Extra settings `fred_core.model.factory.get_model()` requires per provider
# beyond `provider` + a non-empty `name` — evidenced by that function's own
# `_require_settings(...)` calls, one entry per provider that has any.
# `openai`, `ollama`, and `anthropic` need nothing beyond `name` and are
# absent from this mapping on purpose.
_PROVIDER_REQUIRED_SETTINGS: dict[str, tuple[str, ...]] = {
    ModelProvider.AZURE_OPENAI.value: ("azure_endpoint", "azure_openai_api_version"),
    ModelProvider.AZURE_APIM.value: (
        "azure_ad_client_id",
        "azure_ad_client_scope",
        "azure_apim_base_url",
        "azure_apim_resource_path",
        "azure_openai_api_version",
        "azure_tenant_id",
    ),
    ModelProvider.VERTEX_AI.value: ("project", "location"),
    ModelProvider.VERTEX_AI_MODEL_GARDEN.value: (
        "project",
        "location",
        "model_family",
    ),
}


def _is_blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _advertise_provider_enum(schema: dict[str, Any], model: type[BaseModel]) -> None:
    """`model_config.json_schema_extra` hook: injects the canonical supported
    providers into the generated `provider` property as a JSON Schema `enum`.
    `provider` stays a plain `str` field (see `SupportedChatProvider` above)
    so the wire shape and every existing consumer are unchanged; this only
    makes the already-enforced restriction visible in OpenAPI/generated
    TypeScript instead of advertising `provider: string`. Computed from
    `list(ModelProvider)` on every schema generation, not a hand-maintained
    copy, so it can never drift from the enum `SupportedChatProvider`
    actually validates against.
    """
    schema.setdefault("properties", {}).setdefault("provider", {})["enum"] = [
        p.value for p in list(ModelProvider)
    ]


class ModelBinding(FrozenModel):
    """
    A platform-operator-asserted concrete model binding for the `chat`
    capability: a supported provider + name + a strict, typed settings
    allowlist (`ModelBindingSettings`).

    Deliberately NOT `ModelConfiguration` — it's a narrower sibling used only
    for this binding. Unlike most per-turn context, it never transits the
    browser: control-plane persists it, and the runtime pod fetches it
    directly from control-plane on its existing per-turn, server-to-server
    `ManagedAgentRuntimeBinding` lookup (see `BoundRuntimeContext.
    platform_chat_model_binding` below) — the same trust boundary as
    `reasoning_enabled_model_ids`, not the client-forwarded
    `chat_default_profile_id` one. `ModelConfiguration.settings` is already
    used in-tree to carry a literal `api_key` for pod-local, non-transiting
    catalog entries (e.g. `apps/fred-agents/config/models_catalog.yaml`'s
    mock provider profiles) — attaching this allowlist to `ModelConfiguration`
    itself would break those at pod boot.

    `provider` is restricted to `fred_core.model.models.ModelProvider` (the
    same enum `get_model()` switches on), so an unsupported or misspelled
    provider is rejected at write time instead of persisting a binding every
    subsequent managed chat turn would then fail to construct against. A
    provider with additional required settings (`azure-openai`,
    `azure-apim`, `vertex-ai`, `vertex-ai-model-garden`) is validated the
    same way: `_validate_provider_required_settings` below checks the exact
    fields `get_model()`'s own `_require_settings(...)` calls for that
    provider, so a binding missing one is rejected here too, before
    persistence, instead of failing every subsequent managed turn at runtime
    model construction. `model_config.json_schema_extra` publishes the
    supported-provider list as a JSON Schema `enum` on the generated OpenAPI
    and TypeScript client, computed from `list(ModelProvider)` so it can
    never drift from the validator above.

    What this type's settings boundary actually guarantees, precisely:
    - `ModelBindingSettings` has no credential-designated field (`api_key`,
      `token`, ...) and no generic auth/header/cookie/client passthrough
      container — there is no field shaped to carry one.
    - `extra="forbid"` rejects any key outside that named allowlist, and
      every URL-typed field rejects non-`http(s)` schemes and userinfo
      (`user:pass@host`).
    - What it does NOT do: inspect whether an arbitrary *value* placed in an
      allowed field (e.g. a string field like `azure_tenant_id`) is itself a
      secret. Operators must never place a credential in an allowed value —
      this type only closes the field-shape channel, not value content.

    Real credentials stay pod-local, resolved via
    `fred_core.model.factory._require_env(...)` from the pod's own process
    environment — never part of this type, never sent over the wire.

    Freshness: resolved fresh on every managed turn (including HITL resume)
    by the runtime's per-turn control-plane lookup — never a session-open
    snapshot. An admin changing or clearing the binding takes effect on the
    very next turn.
    """

    model_config = ConfigDict(json_schema_extra=_advertise_provider_enum)

    provider: SupportedChatProvider
    name: str = Field(..., min_length=1)
    settings: ModelBindingSettings = Field(default_factory=ModelBindingSettings)

    @model_validator(mode="after")
    def _validate_provider_required_settings(self) -> ModelBinding:
        """Mirrors `fred_core.model.factory.get_model()`'s own
        `_require_settings(...)` calls: a provider with additional required
        settings must have every one of them present and non-blank, or the
        binding is rejected here — before persistence — instead of
        persisting a binding every subsequent managed chat turn would then
        fail to construct against. No network call, no environment lookup,
        no reachability check: purely structural, same as every other
        `ModelBindingSettings` validator.
        """
        required = _PROVIDER_REQUIRED_SETTINGS.get(self.provider, ())
        missing = [
            field_name
            for field_name in required
            if _is_blank(getattr(self.settings, field_name))
        ]
        if missing:
            raise ValueError(
                f"Provider {self.provider!r} requires settings {missing} to "
                "construct a chat model."
            )
        return self


class RuntimeContext(BaseModel):
    """
    Runtime-scoped context passed with a request.

    Why: carry per-request identity, selection, auth, and observability data to
    runtime services.
    How: attach a RuntimeContext to the runtime binding or execution request.
    Example:
        >>> ctx = RuntimeContext(session_id="s-1", user_id="u-1")

    Field groups:
    - Group A (identity): session_id, user_id, team_id, exchange_id, checkpoint_id,
      agent_instance_id, template_agent_id, trace_id, correlation_id, execution_action.
      For managed execution the frontend MUST set team_id (and user_id): the pod
      authorizes the caller against OpenFGA on team_id (RUNTIME-07 rev. 2 — no grant).
    - Group B (auth delegation): access_token, refresh_token, access_token_expires_at.
      Required when the runtime calls knowledge-flow backend on behalf of the user.
      These fields are mutable (refreshed in place by the token refresh logic).
    - Group C (per-turn retrieval selections): selected_document_libraries_ids,
      selected_document_uids, context_prompt_text, search_policy, search_rag_scope,
      include_session_scope, include_corpus_scope, deep_search, selected_chat_context_ids,
      chat_default_profile_id, agent_profile_overrides,
      reasoning_enabled_model_ids, reasoning.
      These are the core fields — set by the frontend per turn, read by retrieval logic.
      The platform-operator chat model binding is NOT here — it is never
      client-forwarded; see `BoundRuntimeContext.platform_chat_model_binding`.
    - Group D (content/preferences): language, attachments_markdown. Will
      migrate to session preferences / identity over time.
    """

    # Group A — Identity (managed execution authorizes on team_id via pod-side OpenFGA)
    session_id: Optional[str] = None
    exchange_id: Optional[str] = None
    checkpoint_id: Optional[str] = None
    user_id: Optional[str] = None
    team_id: Optional[str] = None
    trace_id: Optional[str] = None
    correlation_id: Optional[str] = None
    agent_instance_id: Optional[str] = None
    template_agent_id: Optional[str] = None
    execution_action: Optional[Literal["execute", "resume"]] = None

    # Group B — Auth delegation (mutable; refreshed in place by token refresh logic)
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    access_token_expires_at: Optional[int] = None

    # Group C — Per-turn retrieval selections (core; set by frontend, read by retrieval)
    selected_document_libraries_ids: list[str] | None = None
    selected_document_uids: list[str] | None = None
    context_prompt_text: str | None = None
    search_policy: Literal["strict", "hybrid", "semantic"] | None = None
    search_rag_scope: Optional[Literal["corpus_only", "hybrid", "general_only"]] = None
    include_session_scope: Optional[bool] = None
    include_corpus_scope: Optional[bool] = None
    deep_search: Optional[bool] = None
    selected_chat_context_ids: list[str] | None = None
    chat_default_profile_id: str | None = Field(
        default=None,
        description=(
            "Team-chosen default chat model profile id, resolved by control-plane "
            "from the team's TeamRoutingPolicy at prepare-execution and forwarded "
            "unchanged for the rest of the session — same channel as "
            "context_prompt_text, not re-fetched per turn. Applied by "
            "RoutedChatModelFactory only when no static models_catalog.yaml "
            "agent_profile_overrides entry matches — the static YAML override "
            "remains an ops-level override this can never beat."
        ),
    )
    agent_profile_overrides: dict[str, str] | None = Field(
        default=None,
        description=(
            "Team-authored per-agent model-profile overrides (`agent_id -> "
            "profile_id`), same resolution/precedence notes as "
            "chat_default_profile_id above. `None`, not `{}`, when unset — matches "
            "every other Group C field so `model_dump(exclude_none=True)` "
            "(`to_legacy_context`) omits it for the common case of no team policy. "
            "For the `chat` capability, a platform-operator binding "
            "(`BoundRuntimeContext.platform_chat_model_binding`, resolved "
            "trusted per turn — never on this client-forwarded context) wins "
            "over this field unconditionally when set — that is the feature's "
            "intended precedence, not a bug: the platform operator is the "
            "authority on what is actually reachable/licensed in a given "
            "deployment; a pod-local ops-authored override can never beat that."
        ),
    )
    reasoning_enabled_model_ids: list[str] | None = Field(
        default=None,
        description=(
            'kind="model" capability ids whose reasoning a platform admin has '
            "switched ON (`MODEL-REASONING-ENABLEMENT-RFC.md` §5, REASON-01), "
            "resolved by control-plane at prepare-execution and forwarded "
            "unchanged for the rest of the session — same channel and same "
            "'not re-fetched per turn' contract as chat_default_profile_id "
            "above. GLOBAL, not per team: this is an activation ('does this "
            "model run with reasoning'), not a permission — per-team model "
            "authorization is the separate, untouched `usable_model_ids` "
            "(§5.1/§5.4).\n\n"
            "OFF BY DEFAULT, and this is a real semantic difference from "
            "`usable_model_ids`: there, `None` means 'unrestricted'; here "
            "`None` and `[]` mean the same thing as any absent id — reasoning "
            "does NOT run. A model reasons only by being named in this list "
            "(§5.6). RoutedChatModelFactory enforces it by STRIPPING the "
            "reasoning settings at client construction (§5.6.2).\n\n"
            "As BOUND, this is the EFFECTIVE ceiling, not the raw platform "
            "list: `agent_app` intersects it with level 3 (the agent's own "
            "`AgentTuning.reasoning_enabled`, resolved server-side) before "
            "building the RuntimeContext, so an agent whose author left "
            "reasoning off carries an empty list whatever the request said "
            "(§14.5). What the FRONTEND sends is the platform list alone — the "
            "two differ on purpose, and the pod-side one is the one that counts."
        ),
    )
    reasoning: bool | None = Field(
        default=None,
        description=(
            "The user's per-question reasoning choice (REASON-01 level 4, "
            "`MODEL-REASONING-ENABLEMENT-RFC.md` §7), set by the composer "
            "toggle. Travels per turn on this context exactly like "
            "`search_policy`/`search_rag_scope` — reasoning is a property of "
            "the model call, not a tool, so it is a platform chat option and "
            "NOT a capability's `turn_options` slice.\n\n"
            "TRI-STATE, and the distinction matters:\n"
            "- `None` — the agent does not offer the choice (its author left "
            "reasoning off), so no per-question decision was made and levels "
            "1-2 alone decide. This is the default and the pre-REASON-01 "
            "behaviour.\n"
            "- `False` — the agent offers it and the user left it off: the "
            "turn must NOT reason, even on a model whose reasoning is enabled "
            "platform-wide.\n"
            "- `True` — the user asked for it. Permission to reason, never a "
            "guarantee: level 2 remains a ceiling this cannot raise (§5.3)."
        ),
    )
    # NOTE (2026-08-12): a per-question `reasoning_effort` override was built
    # and withdrawn the same day — providers disagree on accepted values
    # (Mistral small 400s on low/medium), and the declaration machinery it
    # required wasn't worth the surface. The effort a reasoning turn runs
    # with is the ops-authored `settings.reasoning_effort` of the resolved
    # profile, full stop; the user's choice is the boolean above.

    # Group D — Content and preferences (will migrate to proper homes over time)
    language: Optional[str] = None
    attachments_markdown: Optional[str] = None


class ConversationTurn(FrozenModel):
    """
    One completed user–agent exchange for cross-turn memory.

    Kept deliberately narrow: the minimum a coordinator or sub-agent needs to
    understand what happened without embedding full message traces.
    ``agent_name`` is set when a named sub-agent produced the response.
    """

    user_message: str
    agent_response: str
    agent_name: str | None = None


class ConversationalState(BaseModel):
    """
    Opt-in mixin that grants a graph state class cross-turn memory.

    Compose this into any graph state class to get automatic carry-forward of
    ``conversation_history`` across turns via ``build_turn_state``.

    Example::

        class MyState(ConversationalState, BaseModel):
            user_message: str
            result: str = ""
    """

    conversation_history: tuple[ConversationTurn, ...] = ()


class PortableEnvironment(str, Enum):
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


JsonScalar = str | int | float | bool | None


class PortableContext(FrozenModel):
    """
    Portable cross-platform execution context.

    This is intentionally narrower than Fred RuntimeContext and aligns with the
    capability-oriented SDK shape: correlation, identity, environment, and small
    non-sensitive baggage.
    """

    request_id: str = Field(..., min_length=1)
    correlation_id: str = Field(..., min_length=1)
    actor: str = Field(..., min_length=1)
    tenant: str = Field(..., min_length=1)
    environment: PortableEnvironment
    trace_id: str | None = None
    client_app: str | None = None
    agent_id: str | None = None
    agent_name: str | None = None
    agent_version: str | None = None
    session_id: str | None = None
    user_id: str | None = None
    user_name: str | None = None
    team_id: str | None = None
    baggage: dict[str, str] = Field(default_factory=dict)


class ToolInvocationRequest(FrozenModel):
    tool_ref: str = Field(..., min_length=1)
    payload: dict[str, object] = Field(default_factory=dict)
    context: PortableContext
    timeout_ms: int = Field(default=5000, ge=100)
    idempotency_key: str | None = None


class ToolContentKind(str, Enum):
    TEXT = "text"
    JSON = "json"


class ToolContentBlock(FrozenModel):
    kind: ToolContentKind
    text: str | None = None
    data: dict[str, object] | None = None


# The frozen base union is link | geo. Capability chat parts extend it at
# registration time via `contracts.ui_part_union.rebuild_ui_part_union`
# (#1977, RFC AGENT-CAPABILITY-RFC §3.6/§4) — never by hand-editing this
# literal. Code building validators after registration must resolve the union
# lazily (`ui_part_union.current_ui_part_union()`), not freeze this name at
# import time.
UiPart = Annotated[LinkPart | GeoPart, Field(discriminator="type")]


class ToolInvocationResult(FrozenModel):
    tool_ref: str = Field(..., min_length=1)
    blocks: tuple[ToolContentBlock, ...] = ()
    sources: tuple[VectorSearchHit, ...] = ()
    ui_parts: tuple[UiPart, ...] = ()
    is_error: bool = False


class InvocationScope(FrozenModel):
    """
    Per-call narrowing of a callee agent's retrieval world (RFC AGENT-INVOKE).

    Why this model exists:
    - when one agent invokes another it often needs the callee to answer over a
      *specific* set of documents/libraries (e.g. "only these CMDB CSVs"), not the
      caller's ambient request scope
    - these fields already exist on ``RuntimeContext``; this model lets the *caller*
      set them for one invocation

    Safety:
    - scope can only *narrow*, never widen — the callee still runs under the caller's
      delegated identity and ReBAC/document permissions are enforced as usual
    """

    document_uids: list[str] | None = None
    """Restrict the callee's retrieval to these document UIDs."""

    library_ids: list[str] | None = None
    """Restrict the callee's retrieval to these document-library (tag) IDs."""

    search_policy: Literal["strict", "hybrid", "semantic"] | None = None
    """Override the callee's search policy for this call."""


class AgentInvocationRequest(FrozenModel):
    """
    Typed request to invoke a registered fred v2 agent from a graph node.

    Why this model exists:
    - gives the ``AgentInvokerPort`` a stable, versioned contract that is
      independent of transport (in-process, Temporal child workflow, HTTP)
    - keeps ``agent_id`` and ``message`` explicit rather than scattered kwargs

    How to use it:
    - constructed automatically by ``GraphNodeContext.invoke_agent``; authors
      do not need to build this directly
    """

    agent_id: str = Field(..., min_length=1)
    """Stable definition ref of the target agent (e.g. ``"v2.sample.resume_parser"``)."""

    message: str = Field(..., min_length=1)
    """The user-turn message sent to the target agent."""

    context: PortableContext
    """Propagated execution context (identity, tracing, tenant, session)."""

    prior_turns: tuple[ConversationTurn, ...] = ()
    """Prior conversation turns forwarded from the calling agent for context seeding."""

    scope: InvocationScope | None = None
    """Per-call narrowing of the callee's retrieval world (RFC AGENT-INVOKE). Optional."""

    output_schema: dict[str, Any] | None = None
    """JSON schema the callee output should conform to (RFC AGENT-INVOKE). Optional;
    informational for transports that can force structured output natively."""


class AgentInvocationResult(FrozenModel):
    """
    Typed output returned when one agent invokes another.

    Why this model exists:
    - agents return richer output than tools: structured text, optional UI
      parts (maps, links), and ranked sources
    - using ``content: str`` rather than ``blocks: tuple[ToolContentBlock, ...]``
      matches the agent output contract (``GraphExecutionOutput``) and gives
      callers a direct, readable field without block-list traversal
    - having a distinct type from ``ToolInvocationResult`` makes the call-site
      intent clear: this is an agent-to-agent interaction, not a tool call

    How to use it:
    - read ``result.content`` for the agent's primary text response
    - read ``result.ui_parts`` for any structured UI elements the agent produced
    - read ``result.sources`` for any knowledge sources the agent cited
    - check ``result.is_error`` before trusting ``content``

    Example::

        result = await context.invoke_agent(
            agent_id="v2.sample.screening.resume_parser",
            message=f"Parse this resume: {resume_text}",
        )
        if not result.is_error:
            parsed_json = result.content
    """

    agent_id: str = Field(..., min_length=1)
    """The agent that was invoked."""

    content: str = ""
    """Primary text response from the agent."""

    structured: dict[str, Any] | None = None
    """Validated structured payload when the caller passed ``output_schema`` to
    ``invoke_agent`` (RFC AGENT-INVOKE). Schema-conformant when present; ``None`` when
    no schema was requested or the callee's output could not be coerced."""

    sources: tuple[VectorSearchHit, ...] = ()
    """Knowledge sources cited by the agent, if any."""

    ui_parts: tuple[UiPart, ...] = ()
    """Structured UI elements produced by the agent (maps, download links, etc.)."""

    is_error: bool = False
    """True when the agent failed; ``content`` may contain an error description."""


class PublishedArtifact(FrozenModel):
    """
    Stable description of a file that Fred stored for an agent run.

    Returning this object instead of a raw URL keeps the capability explicit and
    makes it easy to convert the result into the UI-facing `LinkPart`.
    """

    key: str = Field(..., min_length=1)
    file_name: str = Field(..., min_length=1)
    size: int = Field(..., ge=0)
    href: str | None = None
    document_uid: str | None = None
    mime: str | None = None
    title: str | None = None
    link_kind: LinkKind = LinkKind.download

    def to_link_part(self) -> LinkPart:
        return LinkPart(
            href=self.href,
            title=self.title or self.file_name,
            kind=self.link_kind,
            mime=self.mime,
            document_uid=self.document_uid,
            file_name=self.file_name,
        )


class FsEntry(FrozenModel):
    """
    One entry returned when listing a team-rooted filesystem directory.

    Paths are author-relative (e.g. ``templates/deck.pptx`` or ``shared/...``); the team and
    user prefixes are injected by the runtime and never appear here.
    """

    path: str = Field(..., min_length=1)
    size: int | None = None
    is_dir: bool = False


class BoundRuntimeContext(FrozenModel):
    """
    Platform bind result combining the Fred RuntimeContext with a portable
    context that can be propagated through tracing, tool invocation, and
    future registry integrations.

    Important migration note:
    - `portable_context` is the preferred v2 contract for new code
    - `runtime_context` remains available because current production v2 runtimes
      still depend on legacy Fred fields for concerns such as language, auth token
      refresh, and some retrieval/session behavior
    - new helpers and new runtime capabilities should prefer explicit ports or
      `portable_context` instead of expanding direct `runtime_context` usage
    """

    runtime_context: RuntimeContext = Field(
        ...,
        description=(
            "Legacy Fred runtime context kept as a transitional compatibility bridge. "
            "New v2 code should prefer portable_context or explicit runtime ports when possible."
        ),
    )
    portable_context: PortableContext = Field(
        ...,
        description=(
            "Preferred portable execution context for v2 code. "
            "Use this for tracing, correlation, identity, and small non-sensitive execution metadata."
        ),
    )
    usable_model_ids: tuple[str, ...] | None = Field(
        default=None,
        description=(
            'kind="model" capability ids this turn\'s team may use (OBSERV-02 '
            "v3, AGENT-CAPABILITY-RFC.md §8.7), computed ONCE per turn by the "
            "caller (never inside model-routing resolution — that runs "
            "multiple times per turn and must never trigger a network call). "
            "None means ReBAC is disabled/unconfigured — no restriction, the "
            "same dev/identity-only posture every other pod-side check "
            "already applies. A non-None, possibly-empty tuple means ReBAC "
            "is active and this is exactly what is allowed; "
            "RoutedChatModelFactory fails closed against it."
        ),
    )
    platform_chat_model_binding: ModelBinding | None = Field(
        default=None,
        description=(
            "Platform-operator-asserted `chat` capability model binding, "
            "trusted and resolved fresh on every managed turn (including HITL "
            "resume) by the caller's per-turn control-plane "
            "`ManagedAgentRuntimeBinding` lookup — the same trust boundary as "
            "`reasoning_enabled_model_ids`, never a client-forwarded field. "
            "Direct (non-managed) `agent_id` execution never populates this: "
            "V1 platform binding applies to managed agent-instance execution "
            "only, and direct execution stays pod-local routing.\n\n"
            "When set, `RoutedChatModelFactory.select` returns it "
            "unconditionally for the `chat` capability, before the resolver "
            "(and therefore the static `agent_profile_overrides` / team-policy "
            "layers) is even consulted, and the resulting "
            "`ModelSelectionSource.PLATFORM_BINDING` selection is exempted "
            "from the `usable_model_ids` ReBAC gate above — the platform "
            "operator is the authority on what is actually "
            "reachable/licensed, so a team-level `can_use` restriction cannot "
            "veto it. `None` means no platform binding is set for `chat`, "
            "which is every deployment before this feature — routing falls "
            "through to `agent_profile_overrides`/team policy/pod default "
            "exactly as before."
        ),
    )
