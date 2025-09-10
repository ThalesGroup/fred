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
from app.core.model.azure_apim_model import AzureApimModel
from langchain_openai import AzureChatOpenAI, ChatOpenAI
from langchain_ollama import ChatOllama
from pydantic import BaseModel
from typing import Type
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import PydanticOutputParser


from app.common.structures import ModelConfiguration

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
        logger.info(
            "Creating Azure APIM Chat model instance with config %s", model_config
        )
        return AzureApimModel().get_llm()

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
