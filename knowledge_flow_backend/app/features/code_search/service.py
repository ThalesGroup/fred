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

# app/features/code_search/service.py
from app.application_context import ApplicationContext
from app.features.code_search.code_loader import load_code_documents


class CodeSearchService:
    def __init__(self):
        context = ApplicationContext.get_instance()
        embedder = context.get_embedder()
        self.vector_store = context.get_create_vector_store(embedder)

    def similarity_search_with_score(self, query: str, k: int = 10):
        return self.vector_store.similarity_search_with_score(query, k=k)

    def scan_codebase(self, path: str):
        return load_code_documents(path)

    def index_documents(self, docs: list):
        self.vector_store.add_documents(docs)
