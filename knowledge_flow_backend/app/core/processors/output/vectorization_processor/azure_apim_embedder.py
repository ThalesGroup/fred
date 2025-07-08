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

from typing import List
from azure.identity import ClientSecretCredential
import httpx
import logging
from langchain.embeddings.base import Embeddings

from app.config.embedding_azure_apim_settings import EmbeddingAzureApimSettings

logger = logging.getLogger(__name__)


class AzureApimEmbedder(Embeddings):
    """
    LangChain-compatible embedder that sends requests to Azure OpenAI via APIM.
    Implements the required embed_documents and embed_query methods.
    """

    def __init__(self, settings: EmbeddingAzureApimSettings):
        logger.info("✅ Initializing Azure APIM Embedder")
        self.settings = settings

    def _get_bearer_token(self) -> str:
        try:
            credential = ClientSecretCredential(
                tenant_id=self.settings.azure_tenant_id,
                client_id=self.settings.azure_client_id,
                client_secret=self.settings.azure_client_secret,
            )
            token = credential.get_token(self.settings.azure_client_scope)
            return token.token
        except Exception as e:
            logger.exception("❌ Failed to retrieve Azure bearer token")
            raise RuntimeError(f"Authentication failure: {e}")

    def _build_embeddings_url(self) -> str:
        return (
            f"{self.settings.azure_apim_base_url}{self.settings.azure_resource_path_embeddings}"
            f"/deployments/{self.settings.azure_deployment_embedding}/embeddings"
            f"?api-version={self.settings.azure_api_version}"
        )

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        token = self._get_bearer_token()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "TrustNest-Apim-Subscription-Key": self.settings.azure_apim_key,
        }
        payload = {
            "input": texts,
            "input_type": "query",
            "model": self.settings.azure_deployment_embedding,
        }
        url = self._build_embeddings_url()

        try:
            response = httpx.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json().get("data", [])
            return [d["embedding"] for d in data]
        except Exception as e:
            logger.exception("❌ Azure APIM embedding failed")
            raise RuntimeError("Embedding error via Azure APIM") from e

    def embed_query(self, text: str) -> List[float]:
        return self.embed_documents([text])[0]
