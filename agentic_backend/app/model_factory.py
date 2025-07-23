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
from langchain_openai import AzureChatOpenAI, ChatOpenAI
from langchain_ollama import ChatOllama
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel
from typing import Type, Any

from app.common.structures import ModelConfiguration

logger = logging.getLogger(__name__)

def get_model(model_config: ModelConfiguration):
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
    provider = model_config.provider

    if not provider:
        logger.error("Missing mandatory model_type property in model configuration: %s", model_config)
        raise ValueError("Missing mandatory_model type in model configuration.")
    settings = (model_config.settings or {}).copy()

    if provider == "azure":
        logger.info("Creating Azure Chat model instance with config %s", model_config)
        return AzureChatOpenAI(
            azure_deployment=model_config.name,
            api_version=settings.pop("api_version", "2024-05-01-preview"),
            **settings
        )
    elif provider == "openai":
        logger.info("Creating OpenAI Chat model instance with config %s", model_config)
        return ChatOpenAI(
            model=model_config.name,
            **settings
        )
    elif provider == "ollama":
        logger.info("Creating Ollama Chat model instance with config %s", model_config)
        return ChatOllama(
            model=model_config.name,
            base_url=settings.pop("base_url", None),
            **settings
        )
    else:
        logger.error("Unsupported model provider %s", provider)
        raise ValueError(f"Unknown model provider {provider}")



def get_structured_chain(
    schema: Type[BaseModel],
    model_config: ModelConfiguration
) -> Any:
    """
    Returns a LangChain chain for structured output, with fallback for unsupported providers.

    Args:
        schema (Type[BaseModel]): The Pydantic schema to extract.
        model_config (ModelConfiguration): The model configuration object.

    Returns:
        A chain that extracts structured output as an instance of the schema.
    """
    model = get_model(model_config)
    provider = model_config.provider
    schema_name = schema.__name__

    if provider in {"openai", "azure"}:
        logger.debug(f"Using function_calling for schema {schema_name} with provider '{provider}'")
        return model.with_structured_output(schema, method="function_calling")

    logger.debug(f"Falling back to prompt-based structured output for schema {schema_name} with provider '{provider}'")

    field_names = list(schema.__fields__.keys())
    prompt = PromptTemplate(
        template=(
            "You are an assistant that extracts structured information.\n"
            "Based on the following input:\n\n"
            "{input}\n\n"
            "Please return a valid JSON with the following fields:\n"
            "{fields}"
        ),
        input_variables=["input", "fields"]
    )

    def parse_fallback(inputs):
        prompt_input = {
            "input": inputs["input"],
            "fields": ", ".join(field_names)
        }

        raw_response = model.invoke(prompt_input)
        try:
            return schema.model_validate_json(raw_response)
        except Exception as e:
            logger.warning(f"Failed to parse fallback structured output for {schema_name}")
            logger.warning("Raw model response: %s", raw_response)
            logger.exception(e)
            raise RuntimeError(f"Structured output parsing failed for schema: {schema_name}")

    return prompt | RunnableLambda(parse_fallback)
