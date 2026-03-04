# fred_core/model/factory.py
#
# Copyright Thales 2025
# Licensed under the Apache License, Version 2.0

from __future__ import annotations

import asyncio
import logging
import os
import threading
from collections.abc import AsyncGenerator, Generator
from typing import Any, Dict, Iterable, Optional, Protocol, Sequence, Type, cast

import httpx
from langchain_core.embeddings import Embeddings as LCEmbeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_openai import (
    AzureChatOpenAI,
    AzureOpenAIEmbeddings,
    ChatOpenAI,
    OpenAIEmbeddings,
)
from pydantic import BaseModel

from fred_core.common.structures import ModelConfiguration
from fred_core.model.http_clients import get_shared_stack, strip_transport_settings
from fred_core.model.models import ModelProvider

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Vertex AI Model Garden auth hardening (token auto-refresh)
# ---------------------------------------------------------------------------

_GCP_CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"


class _GcpCredentials(Protocol):
    """
    Minimal protocol for google-auth credentials used by _GcpTokenAuth.
    """

    valid: bool
    token: str | None
    requires_scopes: bool

    def refresh(self, request: object) -> None: ...

    def with_scopes(self, scopes: Sequence[str]) -> "_GcpCredentials": ...


class _GcpTokenAuth(httpx.Auth):
    """
    Attach a valid GCP Bearer token on each request.

    Why this exists:
    - langchain-google-vertexai Model Garden classes currently initialize
      `httpx` clients with a static `Authorization: Bearer <token>` header.
    - token lifetime is short (~1h), which triggers ACCESS_TOKEN_EXPIRED in
      long-running Fred processes.
    """

    def __init__(
        self, credentials: object | None = None, request_adapter: object | None = None
    ):
        resolved_credentials = credentials
        resolved_request = request_adapter
        if resolved_credentials is None or resolved_request is None:
            try:
                import google.auth as google_auth
                from google.auth.transport import requests as google_auth_requests
            except ImportError as exc:
                raise ImportError(
                    "google-auth is required for Vertex AI providers."
                ) from exc

            if resolved_credentials is None:
                resolved_credentials = google_auth.default(
                    scopes=[_GCP_CLOUD_PLATFORM_SCOPE]
                )[0]
            if getattr(resolved_credentials, "requires_scopes", False) and hasattr(
                resolved_credentials, "with_scopes"
            ):
                resolved_credentials = cast(
                    _GcpCredentials, resolved_credentials
                ).with_scopes([_GCP_CLOUD_PLATFORM_SCOPE])
            resolved_request = google_auth_requests.Request()

        if resolved_credentials is None or resolved_request is None:
            raise ValueError(
                "Unable to initialize GCP auth credentials/request adapter."
            )
        if not callable(getattr(resolved_credentials, "refresh", None)):
            raise TypeError("GCP credentials object does not expose refresh().")

        self._credentials = cast(_GcpCredentials, resolved_credentials)
        self._request = resolved_request

        self._lock = threading.Lock()

    def _refresh_if_needed(self) -> None:
        with self._lock:
            valid = bool(getattr(self._credentials, "valid", False))
            token = getattr(self._credentials, "token", None)
            if valid and token:
                return
            refresh = getattr(self._credentials, "refresh", None)
            if not callable(refresh):
                raise TypeError("GCP credentials object does not expose refresh().")
            refresh(self._request)
            refreshed_token = getattr(self._credentials, "token", None)
            if not refreshed_token:
                raise ValueError("Could not retrieve a refreshed GCP access token.")

    def auth_flow(
        self, request: httpx.Request
    ) -> Generator[httpx.Request, httpx.Response, None]:
        self._refresh_if_needed()
        token = self._credentials.token
        if not token:
            raise ValueError("Could not retrieve a valid GCP access token.")
        request.headers["Authorization"] = f"Bearer {token}"
        yield request

    async def async_auth_flow(
        self, request: httpx.Request
    ) -> AsyncGenerator[httpx.Request, httpx.Response]:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._refresh_if_needed)
        token = self._credentials.token
        if not token:
            raise ValueError("Could not retrieve a valid GCP access token.")
        request.headers["Authorization"] = f"Bearer {token}"
        yield request


def _patch_vertex_maas_auth(model: Any) -> None:
    """
    Replace static Authorization header with auto-refreshing auth object.

    This patch is best-effort and only applies when the model exposes both
    `client` and `async_client` as `httpx` clients.
    """

    sync_client = getattr(model, "client", None)
    async_client = getattr(model, "async_client", None)
    if not isinstance(sync_client, httpx.Client) or not isinstance(
        async_client, httpx.AsyncClient
    ):
        logger.warning(
            "[MODEL][VERTEX_MAAS] Unable to patch auto-refresh auth for %s: model does not expose expected httpx clients.",
            type(model).__name__,
        )
        return

    auth = _GcpTokenAuth(credentials=getattr(model, "credentials", None))
    for client in (sync_client, async_client):
        client.auth = auth
        client.headers.pop("Authorization", None)
    logger.info(
        "[MODEL][VERTEX_MAAS] Enabled auto-refreshing GCP auth for %s.",
        type(model).__name__,
    )


# ---------------------------------------------------------------------------
# Logging hygiene
# ---------------------------------------------------------------------------

_REDACT_SUBSTRINGS = ("key", "token", "secret", "password", "authorization")


def _redact_settings(d: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in (d or {}).items():
        lk = k.lower()
        if any(s in lk for s in _REDACT_SUBSTRINGS):
            out[k] = "***REDACTED***"
        else:
            out[k] = v
    return out


def _info_provider(cfg: ModelConfiguration, settings: Dict[str, Any]) -> None:
    logger.info(
        "[MODEL] Provider=%s Name=%s Settings=%s",
        cfg.provider,
        cfg.name,
        _redact_settings(settings),
    )


# ---------------------------------------------------------------------------
# Small shared helpers (DRY)
# ---------------------------------------------------------------------------


def _require_env(var: str) -> str:
    v = os.getenv(var, "")
    if not v:
        raise ValueError(f"Missing required environment variable: {var}")
    return v


def _require_settings(
    settings: Dict[str, Any], required: Iterable[str], context: str
) -> None:
    missing = [k for k in required if not settings.get(k)]
    if missing:
        raise ValueError(f"Missing {missing} in {context} settings")


# ---------------------------------------------------------------------------
# Defaults: model behavior (NOT transport)
# Keep transport defaults in http_clients.py only.
# ---------------------------------------------------------------------------

_DEFAULT_CHAT_BEHAVIOR: Dict[str, Any] = {
    "temperature": 0.0,
    "max_retries": 0,
}


def _apply_chat_defaults(settings: Dict[str, Any]) -> None:
    for k, v in _DEFAULT_CHAT_BEHAVIOR.items():
        settings.setdefault(k, v)


def _apply_embedding_defaults(settings: Dict[str, Any]) -> None:
    # Embeddings do not use temperature; keep only retry default.
    settings.pop("temperature", None)
    settings.setdefault("max_retries", 0)


def _normalize_openai_compat(settings: Dict[str, Any]) -> None:
    """
    Users often write base_url in YAML. LangChain/OpenAI wrappers typically use openai_api_base.
    We accept both and normalize to openai_api_base.
    """
    if "base_url" in settings and "openai_api_base" not in settings:
        settings["openai_api_base"] = settings.pop("base_url")


def _apply_openai_stream_usage_default(settings: Dict[str, Any]) -> None:
    """
    Enforce usage reporting for streamed chat responses across OpenAI-compatible wrappers.

    Rationale:
    - In Fred we inject shared HTTP clients, which bypasses wrapper auto-defaults.
    - The websocket telemetry contract expects token usage whenever upstream supports it.

    Opt-out:
    - Set `stream_usage: false` explicitly in model settings when a gateway/provider
      does not support usage-in-stream responses.
    """
    if "stream_usage" in settings:
        return
    settings["stream_usage"] = True


# ---------------------------------------------------------------------------
# Chat model factory
# ---------------------------------------------------------------------------


def get_model(cfg: Optional[ModelConfiguration]) -> BaseChatModel:
    if cfg is None:
        raise ValueError("Model configuration is None")
    if not cfg.provider:
        raise ValueError("Model configuration provider is required")

    provider = cfg.provider.lower()
    settings: Dict[str, Any] = dict(cfg.settings or {})

    # Prevent user from injecting their own clients and breaking lifecycle.
    settings.pop("http_client", None)
    settings.pop("http_async_client", None)

    # Provider-specific and type-specific defaults
    _apply_chat_defaults(settings)
    if provider in (
        ModelProvider.OPENAI.value,
        ModelProvider.AZURE_OPENAI.value,
        ModelProvider.AZURE_APIM.value,
    ):
        _normalize_openai_compat(settings)
    if provider in (
        ModelProvider.OPENAI.value,
        ModelProvider.AZURE_OPENAI.value,
        ModelProvider.AZURE_APIM.value,
    ):
        _apply_openai_stream_usage_default(settings)

    # Extract an optional request-level timeout (applied at OpenAI client level)
    request_level_timeout = settings.get("request_timeout", None)

    # Allocate / reuse shared HTTP clients based on (possibly empty) settings
    # IMPORTANT: strip transport keys before forwarding to LangChain wrappers.
    tuning, h_client, a_client = get_shared_stack(cfg, settings=settings)
    strip_transport_settings(settings)

    # Determine effective timeout to pass to the SDK wrapper.
    # If request_timeout is explicit, use it. Otherwise, enforce the transport timeout.
    # This prevents the OpenAI SDK from overriding our strict httpx client timeout with its default (600s).
    effective_timeout = (
        request_level_timeout if request_level_timeout is not None else tuning.timeout
    )

    base_kwargs = {
        "http_client": h_client,
        "http_async_client": a_client,
        "timeout": effective_timeout,
    }

    # --- Provider: OpenAI ---
    if provider == ModelProvider.OPENAI.value:
        _require_env("OPENAI_API_KEY")
        if not cfg.name:
            raise ValueError(
                "OpenAI chat requires 'name' (model id, e.g., gpt-4o-mini)."
            )
        _info_provider(cfg, settings)
        logger.info(
            "[MODEL][OPENAI] Constructing ChatOpenAI model=%s with explicit timeout=%s stream_usage=%s (overriding SDK default)",
            cfg.name,
            base_kwargs.get("timeout"),
            settings.get("stream_usage"),
        )
        return ChatOpenAI(
            model=cfg.name,
            **base_kwargs,
            **settings,
        )

    # --- Provider: Azure OpenAI ---
    if provider == ModelProvider.AZURE_OPENAI.value:
        _require_env("AZURE_OPENAI_API_KEY")
        _require_settings(
            settings, ["azure_endpoint", "azure_openai_api_version"], "Azure chat"
        )
        if not cfg.name:
            raise ValueError("Azure chat requires 'name' (deployment).")
        api_version = settings.pop("azure_openai_api_version")
        _info_provider(cfg, settings)
        logger.info(
            "[MODEL][AZURE_OPENAI] Constructing AzureChatOpenAI deployment=%s with explicit timeout=%s",
            cfg.name,
            base_kwargs.get("timeout"),
        )
        logger.info(
            "[MODEL][AZURE_OPENAI] stream_usage=%s",
            settings.get("stream_usage"),
        )
        return AzureChatOpenAI(
            azure_deployment=cfg.name,
            api_version=api_version,
            **base_kwargs,
            **settings,
        )

    # --- Provider: Azure APIM ---
    if provider == ModelProvider.AZURE_APIM.value:
        required = [
            "azure_ad_client_id",
            "azure_ad_client_scope",
            "azure_apim_base_url",
            "azure_apim_resource_path",
            "azure_openai_api_version",
            "azure_tenant_id",
        ]
        _require_settings(settings, required, "Azure APIM chat")
        _require_env("AZURE_APIM_SUBSCRIPTION_KEY")
        client_secret = _require_env("AZURE_AD_CLIENT_SECRET")

        base = settings["azure_apim_base_url"].rstrip("/")
        path = settings["azure_apim_resource_path"].rstrip("/")
        api_version = settings["azure_openai_api_version"]

        if not cfg.name:
            raise ValueError("Azure APIM chat requires 'name' (deployment).")

        from azure.identity import ClientSecretCredential

        credential = ClientSecretCredential(
            tenant_id=settings["azure_tenant_id"],
            client_id=settings["azure_ad_client_id"],
            client_secret=client_secret,
        )
        scope = settings["azure_ad_client_scope"]

        def _token_provider() -> str:
            return credential.get_token(scope).token

        passthrough = {k: v for k, v in settings.items() if k not in required}
        _info_provider(cfg, passthrough)
        logger.info(
            "[MODEL][AZURE_APIM] Constructing AzureChatOpenAI (APIM) deployment=%s with explicit timeout=%s",
            cfg.name,
            base_kwargs.get("timeout"),
        )
        logger.info(
            "[MODEL][AZURE_APIM] stream_usage=%s",
            passthrough.get("stream_usage"),
        )

        return AzureChatOpenAI(
            azure_endpoint=f"{base}{path}/deployments/{cfg.name}/chat/completions?api-version={api_version}",
            api_version=api_version,
            azure_ad_token_provider=_token_provider,
            default_headers={
                "TrustNest-Apim-Subscription-Key": os.environ[
                    "AZURE_APIM_SUBSCRIPTION_KEY"
                ]
            },
            **base_kwargs,
            **passthrough,
        )

    # --- Provider: Vertex AI (Gemini / GenAI) ---
    if provider == ModelProvider.VERTEX_AI.value:
        if not cfg.name:
            raise ValueError(
                "Vertex AI chat requires 'name' (model id, e.g., gemini-2.5-flash)."
            )
        _require_settings(settings, ["project", "location"], "Vertex AI chat")
        project = str(settings.pop("project"))
        location = str(settings.pop("location"))
        request_timeout = settings.pop("request_timeout", None)
        if request_timeout is not None and "timeout" not in settings:
            settings["timeout"] = request_timeout
        # Force Vertex backend path (not Google AI Studio API key mode).
        settings.setdefault("vertexai", True)
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as e:
            raise ImportError(
                "Provider 'vertex-ai' chat requires package 'langchain-google-genai'."
            ) from e

        log_settings = dict(settings)
        log_settings.update({"project": project, "location": location})
        _info_provider(cfg, log_settings)
        logger.info(
            "[MODEL][VERTEX_AI] Constructing ChatGoogleGenerativeAI model=%s project=%s location=%s",
            cfg.name,
            project,
            location,
        )
        return ChatGoogleGenerativeAI(
            model=cfg.name,
            project=project,
            location=location,
            **settings,
        )

    # --- Provider: Vertex AI Model Garden (generic) ---
    if provider == ModelProvider.VERTEX_AI_MODEL_GARDEN.value:
        if not cfg.name:
            raise ValueError("Vertex AI Model Garden requires 'name' (model id).")
        _require_settings(
            settings,
            ["project", "location", "model_family"],
            "Vertex AI Model Garden chat",
        )
        project = str(settings.pop("project"))
        location = str(settings.pop("location"))
        model_family = str(settings.pop("model_family")).strip().lower()
        request_timeout = settings.pop("request_timeout", None)
        if request_timeout is not None and "timeout" not in settings:
            settings["timeout"] = request_timeout
        model_cls: Any
        if model_family == "mistral":
            try:
                from langchain_google_vertexai.model_garden_maas.mistral import (
                    VertexModelGardenMistral,
                )
            except ImportError as e:
                raise ImportError(
                    "Provider 'vertex-ai-model-garden' with model_family='mistral' requires 'langchain-google-vertexai' and 'langchain-mistralai'."
                ) from e
            model_cls = VertexModelGardenMistral
        elif model_family == "llama":
            try:
                from langchain_google_vertexai.model_garden_maas.llama import (
                    VertexModelGardenLlama,
                )
            except ImportError as e:
                raise ImportError(
                    "Provider 'vertex-ai-model-garden' with model_family='llama' requires package 'langchain-google-vertexai'."
                ) from e
            model_cls = VertexModelGardenLlama
        elif model_family in {"anthropic", "claude"}:
            try:
                from langchain_google_vertexai.model_garden import ChatAnthropicVertex
            except ImportError as e:
                raise ImportError(
                    "Provider 'vertex-ai-model-garden' with model_family='anthropic' requires package 'langchain-google-vertexai'."
                ) from e
            model_cls = ChatAnthropicVertex
        else:
            raise ValueError(
                "Unsupported model_family for 'vertex-ai-model-garden'. Supported values: mistral, llama, anthropic."
            )

        ctor_candidates: list[Dict[str, Any]] = [
            {"model_name": cfg.name, "project": project, "location": location},
            {"model": cfg.name, "project": project, "location": location},
            {"model_id": cfg.name, "project": project, "location": location},
        ]
        log_settings = dict(settings)
        log_settings.update(
            {"project": project, "location": location, "model_family": model_family}
        )
        _info_provider(cfg, log_settings)
        logger.info(
            "[MODEL][VERTEX_AI_MODEL_GARDEN] Constructing %s model=%s family=%s project=%s location=%s",
            model_cls.__name__,
            cfg.name,
            model_family,
            project,
            location,
        )

        last_error: Optional[TypeError] = None
        constructed: Any | None = None
        for ctor_kwargs in ctor_candidates:
            try:
                constructed = model_cls(**ctor_kwargs, **settings)
                break
            except TypeError as e:
                last_error = e

        if constructed is None:
            raise TypeError(
                "Unable to construct Vertex AI Model Garden chat model with known model kwargs "
                "(tried model_name/model/model_id)."
            ) from last_error

        # LangChain Vertex MaaS currently builds static bearer headers at model
        # construction time. Patch mistral/llama clients to refresh tokens.
        if model_family in {"mistral", "llama"}:
            _patch_vertex_maas_auth(constructed)
        return constructed

    # --- Provider: Ollama ---
    if provider == ModelProvider.OLLAMA.value:
        if not cfg.name:
            raise ValueError("Ollama chat requires 'name' (model).")

        # Ollama transport differs: do not force OpenAI/Azure httpx client injection.
        # We only pass value objects (limits/timeout) via client_kwargs.
        base_url = settings.pop("base_url", None)
        settings.pop("max_retries", None)
        _info_provider(cfg, settings)

        # Depending on langchain_ollama version, the kwargs key can differ.
        # "client_kwargs" is supported by current releases; if your pinned version differs,
        # adapt here centrally.
        return ChatOllama(
            model=cfg.name,
            base_url=base_url,
            client_kwargs={
                "limits": tuning.limits,
                "timeout": tuning.timeout,
            },
            **settings,
        )

    raise ValueError(f"Unsupported chat provider: {provider}")


# ---------------------------------------------------------------------------
# Embeddings model factory
# ---------------------------------------------------------------------------


def get_embeddings(cfg: ModelConfiguration) -> LCEmbeddings:
    if not cfg.provider:
        raise ValueError("Embedding configuration provider is required")

    provider = cfg.provider.lower()
    settings: Dict[str, Any] = dict(cfg.settings or {})

    settings.pop("http_client", None)
    settings.pop("http_async_client", None)

    _apply_embedding_defaults(settings)
    if provider in (
        ModelProvider.OPENAI.value,
        ModelProvider.AZURE_OPENAI.value,
        ModelProvider.AZURE_APIM.value,
    ):
        _normalize_openai_compat(settings)

    tuning, h_client, a_client = get_shared_stack(cfg, settings=settings)
    strip_transport_settings(settings)

    base_kwargs = {
        "http_client": h_client,
        "http_async_client": a_client,
        # Explicitly pass the configured timeout to override the OpenAI SDK default.
        "timeout": tuning.timeout,
    }

    name = cfg.name

    if provider == ModelProvider.OPENAI.value:
        _require_env("OPENAI_API_KEY")
        if not name:
            raise ValueError(
                "OpenAI embeddings require 'name' (e.g., text-embedding-3-large)."
            )
        _info_provider(cfg, settings)
        return OpenAIEmbeddings(model=name, **base_kwargs, **settings)

    if provider == ModelProvider.AZURE_OPENAI.value:
        _require_env("AZURE_OPENAI_API_KEY")
        _require_settings(
            settings, ["azure_endpoint", "azure_openai_api_version"], "Azure embeddings"
        )
        if not name:
            raise ValueError("Azure embeddings require 'name' (deployment).")
        api_version = settings.pop("azure_openai_api_version")
        _info_provider(cfg, settings)
        return AzureOpenAIEmbeddings(
            azure_deployment=name,
            api_version=api_version,
            **base_kwargs,
            **settings,
        )

    if provider == ModelProvider.AZURE_APIM.value:
        required = [
            "azure_ad_client_id",
            "azure_ad_client_scope",
            "azure_apim_base_url",
            "azure_apim_resource_path",
            "azure_openai_api_version",
            "azure_tenant_id",
        ]
        _require_settings(settings, required, "Azure APIM embeddings")
        _require_env("AZURE_APIM_SUBSCRIPTION_KEY")
        client_secret = _require_env("AZURE_AD_CLIENT_SECRET")

        base = settings["azure_apim_base_url"].rstrip("/")
        path = settings["azure_apim_resource_path"].rstrip("/")
        api_version = settings["azure_openai_api_version"]

        if not name:
            raise ValueError("Azure APIM embeddings require 'name' (deployment).")

        from azure.identity import ClientSecretCredential

        credential = ClientSecretCredential(
            tenant_id=settings["azure_tenant_id"],
            client_id=settings["azure_ad_client_id"],
            client_secret=client_secret,
        )
        scope = settings["azure_ad_client_scope"]

        def _token_provider() -> str:
            return credential.get_token(scope).token

        passthrough = {k: v for k, v in settings.items() if k not in required}
        _info_provider(cfg, passthrough)

        return AzureOpenAIEmbeddings(
            azure_endpoint=f"{base}{path}/deployments/{cfg.name}/embeddings?api-version={api_version}",
            api_version=api_version,
            azure_ad_token_provider=_token_provider,
            default_headers={
                "TrustNest-Apim-Subscription-Key": os.environ[
                    "AZURE_APIM_SUBSCRIPTION_KEY"
                ]
            },
            **base_kwargs,
            **passthrough,
        )

    if provider == ModelProvider.VERTEX_AI.value:
        if not name:
            raise ValueError(
                "Vertex AI embeddings require 'name' (e.g., text-embedding-005)."
            )
        _require_settings(settings, ["project", "location"], "Vertex AI embeddings")
        project = str(settings.pop("project"))
        location = str(settings.pop("location"))
        # GoogleGenerativeAIEmbeddings does not use request_timeout directly.
        settings.pop("request_timeout", None)
        # Force Vertex backend path (not Google AI Studio API key mode).
        settings.setdefault("vertexai", True)
        try:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
        except ImportError as e:
            raise ImportError(
                "Provider 'vertex-ai' embeddings requires package 'langchain-google-genai'."
            ) from e

        log_settings = dict(settings)
        log_settings.update({"project": project, "location": location})
        _info_provider(cfg, log_settings)
        return GoogleGenerativeAIEmbeddings(
            model=name,
            project=project,
            location=location,
            **settings,
        )

    if provider == ModelProvider.OLLAMA.value:
        if not name:
            raise ValueError("Ollama embeddings require 'name' (model).")
        base_url = settings.pop("base_url", None)
        settings.pop("max_retries", None)
        _info_provider(cfg, settings)
        return OllamaEmbeddings(
            model=name,
            base_url=base_url,
            client_kwargs={"timeout": tuning.timeout, "limits": tuning.limits},
            **settings,
        )

    raise ValueError(f"Unsupported embeddings provider: {provider}")


# ---------------------------------------------------------------------------
# Structured chain helper
# ---------------------------------------------------------------------------


def get_structured_chain(schema: Type[BaseModel], model_config: ModelConfiguration):
    model = get_model(model_config)
    provider = (model_config.provider or "").lower()

    passthrough = ChatPromptTemplate.from_messages([MessagesPlaceholder("messages")])

    if provider in {
        ModelProvider.OPENAI.value,
        ModelProvider.AZURE_OPENAI.value,
        ModelProvider.AZURE_APIM.value,
        ModelProvider.VERTEX_AI.value,
        ModelProvider.VERTEX_AI_MODEL_GARDEN.value,
    }:
        try:
            structured = model.with_structured_output(schema, method="function_calling")
            return passthrough | structured
        except Exception as e:
            # Do not silently swallow operational errors without breadcrumbs.
            logger.debug(
                "Structured output unavailable (%s): %s; falling back to prompt-based parsing",
                type(e).__name__,
                e,
            )

    parser = PydanticOutputParser(pydantic_object=schema)
    prompt = ChatPromptTemplate.from_messages(
        [
            MessagesPlaceholder("messages"),
            (
                "system",
                "Return ONLY JSON that conforms to this schema:\n{schema}\n\n{format}",
            ),
        ]
    ).partial(
        schema=schema.model_json_schema(), format=parser.get_format_instructions()
    )

    return prompt | model | parser
