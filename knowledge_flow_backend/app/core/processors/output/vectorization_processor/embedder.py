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
from langchain.embeddings.base import Embeddings


class Embedder(Embeddings):
    """
    Generic Embedder
    -------------------
    1. Generic wrapper around a LangChain-compatible embedding model.
    2. Conforms to LangChain's Embeddings interface.
    3. Can be passed directly to SearchEngineVectorSearch or any LangChain component.
    """

    def __init__(self, model: Embeddings):
        """
        Args:
            model (Embeddings): A LangChain-compatible embedding model (e.g., OpenAIEmbeddings, AzureOpenAIEmbeddings).
        """
        self.model = model

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Embed a list of text chunks (as required by LangChain's interface).

        Args:
            texts (List[str]): List of raw text strings to embed.

        Returns:
            List[List[float]]: List of embeddings.
        """
        return self.model.embed_documents(texts)

    def embed_query(self, text: str) -> List[float]:
        """
        Embed a single query (e.g., for similarity search).

        Args:
            text (str): The text to embed.

        Returns:
            List[float]: The embedding.
        """
        return self.model.embed_query(text)
