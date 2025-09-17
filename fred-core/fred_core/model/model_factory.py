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
from typing import Type

from fred_core.common.structures import ModelConfiguration
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_ollama import ChatOllama
from langchain_openai import AzureChatOpenAI, ChatOpenAI
from azure.identity import ClientSecretCredential
from pydantic import BaseModel, SecretStr


logger = logging.getLogger(__name__)


def get_model(model_config: ModelConfiguration | None):
    """
    Factory function to create a model instance based on configuration.

    Args:
        config (dict): Configuration dict with keys 'model_type' and model-specific settings.
                       Example:
                       {
                         "provider": "azure",  # or "openai"
                         "azure_deployment": "fred-gpt-4o",
                         "api_version": "2024-05-01-preview",
                         "temperature": 0,
                         "max_retries": 2
                       }

    Returns:
        An instance of a Chat model.
    """

    assert model_config is not None, "Model configuration should not be `None` here"
    provider = model_config.provider

    if not provider:
        logger.error(
            "Missing mandatory model_type property in model configuration: %s",
            model_config,
        )
        raise ValueError("Missing mandatory model type in model configuration.")
    settings = (model_config.settings or {}).copy()

    if provider == "azure":
        logger.info("Creating Azure Chat model instance with config %s", model_config)
        return AzureChatOpenAI(
            azure_deployment=model_config.name,
            api_version=settings.pop("api_version", "2024-05-01-preview"),
            **settings,
        )

    elif provider == "azureapim":
        logger.info("Creating Azure Chat model instance with config %s", model_config)
        return AzureChatOpenAI(
            azure_deployment=model_config.name,
            api_version=settings.pop("api_version", "2024-05-01-preview"),
            **settings,
        )

    elif provider == "azureapim":
        logger.info(
            "Creating Azure APIM Chat model instance with config %s", model_config
        )
        if not model_config.settings:
            logger.error(
                "Missing settings for Azure APIM provider in model configuration: %s",
                model_config,
            )
            raise ValueError(
                "Missing settings for Azure APIM provider in model configuration."
            )
        azure_apim_base_url = model_config.settings.get("azure_apim_base_url")
        if not azure_apim_base_url:
            logger.error(
                "Missing azure_apim_base_url in settings for Azure APIM provider in model configuration: %s",
                model_config,
            )
            raise ValueError(
                "Missing azure_apim_base_url in settings for Azure APIM provider in model configuration."
            )
        azure_resource_path_llm = model_config.settings.get("azure_resource_path_llm")
        if not azure_resource_path_llm:
            logger.error(
                "Missing azure_resource_path_llm in settings for Azure APIM provider in model configuration: %s",
                model_config,
            )
            raise ValueError(
                "Missing azure_resource_path_llm in settings for Azure APIM provider in model configuration."
            )
        azure_deployment_llm = model_config.settings.get("azure_deployment_llm")
        if not azure_deployment_llm:
            logger.error(
                "Missing azure_deployment_llm in settings for Azure APIM provider in model configuration: %s",
                model_config,
            )
            raise ValueError(
                "Missing azure_deployment_llm in settings for Azure APIM provider in model configuration."
            )
        azure_api_version = model_config.settings.get("azure_api_version")
        if not azure_api_version:
            logger.error(
                "Missing azure_api_version in settings for Azure APIM provider in model configuration: %s",
                model_config,
            )
            raise ValueError(
                "Missing azure_api_version in settings for Azure APIM provider in model configuration."
            )
        full_url = (
            f"{azure_apim_base_url.rstrip()}"
            f"{azure_resource_path_llm}"
            f"/deployments/{azure_deployment_llm}/chat/completions"
            f"?api-version={azure_api_version}"
        )
        azure_api_version = model_config.settings.get("azure_api_version")
        if not azure_api_version:
            logger.error(
                "Missing azure_api_version in settings for Azure APIM provider in model configuration: %s",
                model_config,
            )
            raise ValueError(
                "Missing azure_api_version in settings for Azure APIM provider in model configuration."
            )
        azure_apim_key = os.environ.get("AZURE_APIM_KEY")
        if not azure_apim_key:
            logger.error(
                "Missing AZURE_APIM_KEY environment variable for Azure APIM provider."
            )
            raise ValueError("Missing AZURE_APIM_KEY environment variable.")
        azure_tenant_id = model_config.settings.get("azure_tenant_id")
        if not azure_tenant_id:
            logger.error(
                "Missing azure_tenant_id in settings for Azure APIM provider in model configuration: %s",
                model_config,
            )
            raise ValueError(
                "Missing azure_tenant_id in settings for Azure APIM provider in model configuration."
            )
        azure_client_id = model_config.settings.get("azure_client_id")
        if not azure_client_id:
            logger.error(
                "Missing azure_client_id in settings for Azure APIM provider in model configuration: %s",
                model_config,
            )
            raise ValueError(
                "Missing azure_client_id in settings for Azure APIM provider in model configuration."
            )
        azure_client_secret = os.environ.get("AZURE_CLIENT_SECRET")
        if not azure_client_secret:
            logger.error(
                "Missing AZURE_CLIENT_SECRET environment variable for Azure APIM provider."
            )
            raise ValueError("Missing AZURE_CLIENT_SECRET environment variable.")
        credentials = ClientSecretCredential(
            tenant_id=azure_tenant_id,
            client_id=azure_client_id,
            client_secret=azure_client_secret,
        )
        azure_client_scope = model_config.settings.get("azure_client_scope")
        if not azure_client_scope:
            logger.error(
                "Missing azure_client_scope in settings for Azure APIM provider in model configuration: %s",
                model_config,
            )
            raise ValueError(
                "Missing azure_client_scope in settings for Azure APIM provider in model configuration."
            )
        
        # --- DÉBUT DE LA CORRECTION ---
        
        # 1. Obtenir le jeton d'authentification
        token = credentials.get_token(azure_client_scope).token

        return AzureChatOpenAI(
            # Utilisation de l'URL complète qui inclut déjà :
            # - l'endpoint de base
            # - le chemin vers le déploiement (azure_deployment_llm)
            # - la version d'API (azure_api_version)
            azure_endpoint=full_url,
            
            # Correction : Utiliser 'api_key' au lieu de 'openai_api_key' pour le champ Pydantic attendu.
            api_key=SecretStr(token),  

            # Suppression des arguments redondants/sources de warning Pydantic :
            # - 'openai_api_version' est dans l'URL
            # - 'deployment_name' est dans l'URL
            # - 'openai_api_type="azure"' est souvent implicite avec azure_endpoint et/ou api_key
            
            # Headers spécifiques pour l'APIM
            default_headers={
                "TrustNest-Apim-Subscription-Key": azure_apim_key
            },
            
            # Paramètres de base conservés
            temperature=0,
            max_retries=2,
            timeout=60,
        )

    elif provider == "openai":
        logger.info("Creating OpenAI Chat model instance with config %s", model_config)
        if not model_config.name:
            logger.error(
                "Missing model name for OpenAI provider in model configuration: %s",
                model_config,
            )
            raise ValueError(
                "Missing model name for OpenAI provider in model configuration."
            )
        return ChatOpenAI(model=model_config.name, **settings)
    elif provider == "ollama":
        logger.info("Creating Ollama Chat model instance with config %s", model_config)
        if not model_config.name:
            logger.error(
                "Missing model name for Ollama provider in model configuration: %s",
                model_config,
            )
            raise ValueError(
                "Missing model name for Ollama provider in model configuration."
            )
        return ChatOllama(
            model=model_config.name, base_url=settings.pop("base_url", None), **settings
        )
    else:
        logger.error("Unsupported model provider %s", provider)
        raise ValueError(f"Unknown model provider {provider}")


def get_structured_chain(schema: Type[BaseModel], model_config: ModelConfiguration):
    model = get_model(model_config)
    provider = (model_config.provider or "").lower()

    passthrough = ChatPromptTemplate.from_messages([MessagesPlaceholder("messages")])

    if provider in {"openai", "azure"}:
        try:
            structured = model.with_structured_output(schema, method="function_calling")
            return passthrough | structured
        except Exception:
            logger.debug(
                "Function calling not supported, falling back to prompt-based parsing"
            )
            pass  # fall back below

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
