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

# knowledge_flow_app/services/vector_search_service.py
from typing import List
from langchain.schema.document import Document
from knowledge_flow_app.application_context import ApplicationContext


class VectorSearchService:
    """
    Vector Search Service
    ------------------------------------------------------
    """

    def __init__(self):
        context = ApplicationContext.get_instance()
        embedder = context.get_embedder()
        self.vector_store = context.get_vector_store(embedder)

    def similarity_search_with_score(self, question: str, k: int = 10) -> List[tuple[Document, float]]:
        return self.vector_store.similarity_search_with_score(question, k=k)
