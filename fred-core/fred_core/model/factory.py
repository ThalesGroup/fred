# Copyright Thales 2025
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

import logging
import os
from typing import Dict, Iterable, Optional, Type

from langchain_core.embeddings import Embeddings as LCEmbeddings

# Chat + Embeddings base types
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_ollama import ChatOllama, OllamaEmbeddings

# Provider implementations
from langchain_openai import (
    AzureChatOpenAI,
    AzureOpenAIEmbeddings,
    ChatOpenAI,
    OpenAIEmbeddings,
)
from pydantic import BaseModel

from fred_core.common.structures import ModelConfiguration

logger = logging.getLogger(__name__)


# ---------- Small shared helpers (DRY) ----------


def _require_env(var: str) -> str:
    v = os.getenv(var, "")
    if not v:
        raise ValueError(f"Missing required environment variable: {var}")
    return v


def _require_settings(settings: Dict, required: Iterable[str], context: str) -> None:
    missing = [k for k in required if not settings.get(k)]
    if missing:
        raise ValueError(f"Missing {missing} in {context} settings")


def _info_provider(cfg: ModelConfiguration) -> None:
    logger.info(
        "Provider=%s Name=%s Settings=%s", cfg.provider, cfg.name, cfg.settings or {}
    )


# =================================================
# =============== Chat model factory ===============
# =================================================


def get_model(cfg: Optional[ModelConfiguration]) -> BaseChatModel:
    if cfg is None:
        # In YAML, model can be omitted and replaced by default; we should never hit this.
        raise ValueError("Model configuration is None")
    """
    Fred rationale:
    - One place to instantiate chat models for all providers.
    - Only this function knows per-vendor auth/wiring.
    """
    assert cfg and cfg.provider, "Model configuration is required"
    provider = cfg.provider.lower()
    settings: Dict = dict(cfg.settings or {})

    if provider == "openai":
        _require_env("OPENAI_API_KEY")
        _info_provider(cfg)
        if not cfg.name:
            raise ValueError(
                "OpenAI chat requires 'name' (model id, e.g., gpt-4o-mini)."
            )
        return ChatOpenAI(model=cfg.name, **settings)

    if provider == "azure":
        _require_env("AZURE_OPENAI_API_KEY")
        _require_settings(settings, ["azure_endpoint", "azure_api_version"], "Azure chat")
        _info_provider(cfg)
        if not cfg.name:
            raise ValueError("Azure chat requires 'name' (deployment).")
        api_version = settings.pop("azure_api_version")
        return AzureChatOpenAI(
            azure_deployment=cfg.name, api_version=api_version, **settings
        )

    if provider == "azureapim":
        # Fred rationale (hover):
        # - Enterprise setup via APIM: APIM subscription header + AAD bearer.
        # - We DO NOT mint a static token here. We pass an azure_ad_token_provider
        #   callable so each request gets a fresh token (no 1h expiry issues).
        required = [
            "azure_apim_base_url",
            "azure_resource_path",
            "azure_api_version",
            "azure_tenant_id",
            "azure_client_id",
            "azure_client_scope",  # e.g., "https://cognitiveservices.azure.com/.default"
        ]
        _require_settings(settings, required, "Azure APIM chat")
        _require_env("AZURE_APIM_KEY")
        client_secret = _require_env("AZURE_CLIENT_SECRET")

        base = settings["azure_apim_base_url"].rstrip("/")
        path = settings["azure_resource_path"].rstrip("/")
        api_version = settings["azure_api_version"]

        if not cfg.name:
            raise ValueError("Azure APIM chat requires 'name' (deployment).")

        # Build a token *provider* (fresh token per call) instead of minting once.
        from azure.identity import ClientSecretCredential

        credential = ClientSecretCredential(
            tenant_id=settings["azure_tenant_id"],
            client_id=settings["azure_client_id"],
            client_secret=client_secret,
        )
        scope = settings["azure_client_scope"]

        def _token_provider() -> str:
            # Called by the SDK on each request → auto-refresh tokens.
            return credential.get_token(scope).token

        # Pass through any client kwargs that aren't our required keys.
        passthrough = {k: v for k, v in settings.items() if k not in required}
        _info_provider(cfg)

        # Important routing note:
        # Keep azure_endpoint as your APIM base + resource path.
        # The Azure client composes /openai/deployments/{deployment}/chat/completions
        # with api_version under the hood. Ensure your APIM route maps accordingly.
        return AzureChatOpenAI(
            azure_endpoint=f"{base}{path}",
            azure_deployment=cfg.name,
            api_version=api_version,
            azure_ad_token_provider=_token_provider,  # ← per-request AAD token
            default_headers={"TrustNest-Apim-Subscription-Key": os.environ["AZURE_APIM_KEY"]},
            **passthrough,
        )

    if provider == "ollama":
        if not cfg.name:
            raise ValueError("Ollama chat requires 'name' (model).")
        base_url = settings.pop("base_url", None)
        _info_provider(cfg)
        return ChatOllama(model=cfg.name, base_url=base_url, **settings)

    raise ValueError(f"Unsupported chat provider: {provider}")


# =================================================
# ============ Embeddings model factory ============
# =================================================


def get_embeddings(cfg: ModelConfiguration) -> LCEmbeddings:
    """
    Fred rationale:
    - Mirrors get_model() for embeddings.
    - Keeps auth rules consistent with our "env-only for secrets" policy.
    """
    assert cfg and cfg.provider, "Embedding configuration is required"
    provider = cfg.provider.lower()
    settings: Dict = dict(cfg.settings or {})
    name = cfg.name

    if provider == "openai":
        _require_env("OPENAI_API_KEY")
        if not name:
            raise ValueError(
                "OpenAI embeddings require 'name' (e.g., text-embedding-3-large)."
            )
        _info_provider(cfg)
        return OpenAIEmbeddings(model=name, **settings)

    if provider == "azure":
        _require_env("AZURE_OPENAI_API_KEY")
        _require_settings(
            settings, ["azure_endpoint", "azure_api_version"], "Azure embeddings"
        )
        if not name:
            raise ValueError("Azure embeddings require 'name' (deployment).")
        api_version = settings.pop("azure_api_version")
        _info_provider(cfg)
        return AzureOpenAIEmbeddings(
            azure_deployment=name, api_version=api_version, **settings
        )

    if provider == "azureapim":
        # Same token-provider logic as chat: per-request AAD token via APIM.
        required = [
            "azure_apim_base_url",
            "azure_resource_path",
            "azure_api_version",
            "azure_tenant_id",
            "azure_client_id",
            "azure_client_scope",
        ]
        _require_settings(settings, required, "Azure APIM embeddings")
        _require_env("AZURE_APIM_KEY")
        client_secret = _require_env("AZURE_CLIENT_SECRET")

        base = settings["azure_apim_base_url"].rstrip("/")
        path = settings["azure_resource_path"].rstrip("/")
        api_version = settings["azure_api_version"]
        if not name:
            raise ValueError("Azure APIM embeddings require 'name' (deployment).")

        from azure.identity import ClientSecretCredential

        credential = ClientSecretCredential(
            tenant_id=settings["azure_tenant_id"],
            client_id=settings["azure_client_id"],
            client_secret=client_secret,
        )
        scope = settings["azure_client_scope"]

        def _token_provider() -> str:
            return credential.get_token(scope).token

        passthrough = {k: v for k, v in settings.items() if k not in required}
        _info_provider(cfg)

        return AzureOpenAIEmbeddings(
            azure_endpoint=f"{base}{path}",
            azure_deployment=name,
            api_version=api_version,
            azure_ad_token_provider=_token_provider,  # ← per-request AAD token
            default_headers={"TrustNest-Apim-Subscription-Key": os.environ["AZURE_APIM_KEY"]},
            **passthrough,
        )

    if provider == "ollama":
        if not name:
            raise ValueError("Ollama embeddings require 'name' (model).")
        base_url = settings.pop("base_url", None)
        _info_provider(cfg)
        return OllamaEmbeddings(model=name, base_url=base_url, **settings)

    raise ValueError(f"Unsupported embeddings provider: {provider}")


# =================================================
# ===== Optional helper for image-aware routing ====
# =================================================


def get_structured_chain(schema: Type[BaseModel], model_config: ModelConfiguration):
    model = get_model(model_config)
    provider = (model_config.provider or "").lower()

    passthrough = ChatPromptTemplate.from_messages([MessagesPlaceholder("messages")])

    # Fred rationale (hover):
    # - Azure APIM uses the same Azure client; function calling is available if the model supports it.
    if provider in {"openai", "azure", "azureapim"}:
        try:
            structured = model.with_structured_output(schema, method="function_calling")
            return passthrough | structured
        except Exception:
            logger.debug(
                "Function calling not supported, falling back to prompt-based parsing"
            )
            # fall through to parser path

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
