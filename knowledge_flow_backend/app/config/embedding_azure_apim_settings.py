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


class EmbeddingAzureApimSettings(BaseSettings):
    azure_tenant_id: str = Field(..., validation_alias="AZURE_TENANT_ID")
    azure_client_id: str = Field(..., validation_alias="AZURE_CLIENT_ID")
    azure_client_secret: str = Field(..., validation_alias="AZURE_CLIENT_SECRET")
    azure_client_scope: str = Field(..., validation_alias="AZURE_CLIENT_SCOPE")

    azure_apim_base_url: str = Field(..., validation_alias="AZURE_APIM_BASE_URL")
    azure_resource_path_embeddings: str = Field(..., validation_alias="AZURE_RESOURCE_PATH_EMBEDDINGS")
    azure_resource_path_llm: str = Field(..., validation_alias="AZURE_RESOURCE_PATH_LLM")
    azure_api_version: str = Field(..., validation_alias="AZURE_API_VERSION")
    azure_apim_key: str = Field(..., validation_alias="AZURE_APIM_KEY")
    azure_deployment_llm: str = Field(..., validation_alias="AZURE_DEPLOYMENT_LLM")
    azure_deployment_embedding: str = Field(..., validation_alias="AZURE_DEPLOYMENT_EMBEDDING")

    model_config = {
        "extra": "ignore"  # allows unrelated variables in .env or os.environ
    }
