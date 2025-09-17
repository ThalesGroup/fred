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

# Copyright Thales 2025
# SPDX-License-Identifier: Apache-2.0

import logging
import os
from typing import Dict

from pydantic import SecretStr
from langchain_core.embeddings import Embeddings as LCEmbeddings
from langchain_openai import OpenAIEmbeddings, AzureOpenAIEmbeddings
from langchain_ollama import OllamaEmbeddings

from fred_core.common.structures import ModelConfiguration

logger = logging.getLogger(__name__)


def get_embeddings(model_config: ModelConfiguration) -> LCEmbeddings:
    """
    Fred rationale:
    - Single source of truth for embedding providers (symmetry with get_model()).
    - Callers stay provider-agnostic; only this function knows vendor specifics.
    - We keep secrets in env; all non-sensitive wiring lives in YAML.

    Expected ModelConfiguration:
      provider: "openai" | "azure" | "azureapim" | "ollama"
      name:     model/deployment name (e.g., "text-embedding-3-large", "fred-embed-3")
      settings: provider-specific dict (see branches below)
    """
    if not model_config:
        raise ValueError("Embedding model configuration must not be None.")

    provider = (model_config.provider or "").lower()
    name = model_config.name
    settings: Dict = dict(model_config.settings or {})

    if provider == "openai":
        if not name:
            raise ValueError("OpenAI embeddings require 'name' (model).")
        # OPENAI_API_KEY remains in env by design.
        logger.info("Creating OpenAIEmbeddings(model=%s)", name)
        return OpenAIEmbeddings(model=name, **settings)

    if provider == "azure":
        if not name:
            raise ValueError("Azure embeddings require 'name' (deployment).")
        api_version = settings.pop("api_version", "2024-05-01-preview")
        # Typical non-secret fields (endpoint, api_version) come from YAML.
        logger.info("Creating AzureOpenAIEmbeddings(deployment=%s)", name)
        return AzureOpenAIEmbeddings(
            azure_deployment=name,
            api_version=api_version,
            **settings,  # e.g., {"azure_endpoint": "...", "timeout": 60}
        )

    if provider == "azureapim":
        # APIM policy: non-sensitive wiring in YAML, secrets in env.
        required = [
            "azure_apim_base_url",       # e.g. https://acme-apim.azure-api.net
            "azure_resource_path_embed", # e.g. /openai
            "azure_deployment_embed",    # e.g. fred-embed-3
            "azure_api_version",         # e.g. 2024-05-01-preview
            "azure_tenant_id",
            "azure_client_id",
            "azure_client_scope",        # audience/scope for AAD token
        ]
        for k in required:
            if not settings.get(k):
                raise ValueError(f"Missing '{k}' in Azure APIM embeddings settings.")

        # Secrets from env only
        azure_client_secret = os.environ.get("AZURE_CLIENT_SECRET")
        if not azure_client_secret:
            raise ValueError("AZURE_CLIENT_SECRET env var is required for Azure APIM.")
        azure_apim_key = os.environ.get("AZURE_APIM_KEY")
        if not azure_apim_key:
            raise ValueError("AZURE_APIM_KEY env var is required for Azure APIM.")

        # Build full embeddings endpoint (APIM style)
        base = settings["azure_apim_base_url"].rstrip("/")
        path = settings["azure_resource_path_embed"].rstrip("/")
        dep  = settings["azure_deployment_embed"]
        ver  = settings["azure_api_version"]
        full_url = f"{base}{path}/deployments/{dep}/embeddings?api-version={ver}"

        # Acquire AAD token
        from azure.identity import ClientSecretCredential
        cred = ClientSecretCredential(
            tenant_id=settings["azure_tenant_id"],
            client_id=settings["azure_client_id"],
            client_secret=azure_client_secret,
        )
        token = cred.get_token(settings["azure_client_scope"]).token

        # Pass fully-qualified endpoint + bearer token + APIM header
        passthrough = {
            k: v for k, v in settings.items()
            if k not in required  # keep optional kwargs like timeout/max_retries
        }
        return AzureOpenAIEmbeddings(
            azure_endpoint=full_url,
            api_key=SecretStr(token),
            default_headers={"TrustNest-Apim-Subscription-Key": azure_apim_key},
            **passthrough,
        )

    if provider == "ollama":
        if not name:
            raise ValueError("Ollama embeddings require 'name' (model).")
        logger.info("Creating OllamaEmbeddings(model=%s)", name)
        base_url = settings.pop("base_url", None)
        return OllamaEmbeddings(model=name, base_url=base_url, **settings)

    raise ValueError(f"Unsupported embeddings provider: {provider}")
