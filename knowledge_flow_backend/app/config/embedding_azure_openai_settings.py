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
from pydantic import Field

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class EmbeddingAzureOpenAISettings(BaseSettings):
    azure_openai_endpoint: str = Field(..., validation_alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_api_key: str = Field(..., validation_alias="AZURE_OPENAI_API_KEY")
    azure_api_version: str = Field(..., validation_alias="AZURE_API_VERSION")
    azure_deployment_llm: str = Field(..., validation_alias="AZURE_DEPLOYMENT_LLM")
    azure_deployment_embedding: str = Field(..., validation_alias="AZURE_DEPLOYMENT_EMBEDDING")

    model_config = {
        "extra": "ignore"  # allows unrelated variables in .env or os.environ
    }
