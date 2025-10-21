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


from abc import ABC, abstractmethod
from typing import List

from langchain.embeddings.base import Embeddings


class BaseEmbeddingModel(Embeddings, ABC):
    """
    Interface for embedding models.
    This interface is designed to be implemented by various concrete classes that handle
    different embedding strategies (e.g., OpenAI, Azure, HuggingFace, etc.).
    """

    @abstractmethod
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Embed a list of documents into vectors.
        Returns a list of { 'embedding': List[float], 'document': Document }
        """
        pass
