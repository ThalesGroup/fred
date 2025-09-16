# Copyright Thales 2025
# Apache-2.0

"""
Fred rationale:
- Knowledge Flow sometimes needs a small generative model (utility tasks: summary/keywords/titles).
- We keep a tiny factory here, mirroring the agentic side, so providers/config live in one place.
- The rest of the pipeline depends only on this module, not on provider SDKs.
"""

import logging
from typing import Optional

from app.common.structures import ModelConfiguration

# Providers: mirror agentic-side imports to keep parity
from langchain_openai import ChatOpenAI, AzureChatOpenAI
from langchain_ollama import ChatOllama

logger = logging.getLogger(__name__)


def get_utility_model(model_config: Optional[ModelConfiguration]):
    """
    Create a small chat model used for utility tasks (summaries/keywords).
    - If config is missing, return None and let callers pick a fallback (e.g., TF-IDF).
    - We intentionally don't couple this to the embedder configuration.
    """
    if not model_config or not model_config.provider:
        logger.info("No utility model configured; downstream should use fallback.")
        return None

    provider = (model_config.provider or "").lower()
    settings = (model_config.settings or {}).copy()

    if provider == "openai":
        if not model_config.name:
            raise ValueError("OpenAI model.name is required")
        # Tip: keep temperature low for deterministic summaries
        return ChatOpenAI(model=model_config.name, temperature=settings.pop("temperature", 0.2), **settings)

    if provider in {"azure", "azureopenai"}:
        if not model_config.name:
            raise ValueError("Azure model.name must be the deployment name")
        return AzureChatOpenAI(
            azure_deployment=model_config.name,
            api_version=settings.pop("api_version", "2024-05-01-preview"),
            temperature=settings.pop("temperature", 0.2),
            **settings,
        )

    if provider == "ollama":
        if not model_config.name:
            raise ValueError("Ollama model.name is required")
        return ChatOllama(
            model=model_config.name,
            base_url=settings.pop("base_url", None),
            temperature=settings.pop("temperature", 0.2),
            **settings,
        )

    if provider == "azureapim":
        # Optional: parity with agentic side if you expose an APIM wrapper
        from app.core.model.azure_apim_model import AzureApimModel
        return AzureApimModel().get_llm()

    raise ValueError(f"Unsupported model provider: {model_config.provider}")

