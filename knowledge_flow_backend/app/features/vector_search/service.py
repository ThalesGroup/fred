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
# type: strict

import logging
from typing import List

from fred_core import KeycloakUser
from langchain.schema.document import Document

from app.application_context import ApplicationContext
from app.features.tag.service import TagService

logger = logging.getLogger(__name__)


class VectorSearchService:
    """
    Vector Search Service
    ------------------------------------------------------
    """

    def __init__(self):
        context = ApplicationContext.get_instance()
        embedder = context.get_embedder()
        self.tag_service = TagService()
        self.vector_store = context.get_vector_store(embedder)

    def similarity_search_with_score(self, question: str, user: KeycloakUser, k: int = 10, tags_ids: list[str] | None = None) -> List[tuple[Document, float]]:
        # todo: handle autorization (check if use can rag on listed tags OR restrict research to all document users has access to ?)

        documents_ids: set[str] | None = None
        if tags_ids is not None and len(tags_ids) >= 1:
            documents_ids = set()
            for tag_id in tags_ids:
                tag = self.tag_service.get_tag_for_user(tag_id, user)
                documents_ids.update(tag.document_ids)

        logger.debug("doing similartiy search on following document uids:", documents_ids)
        return self.vector_store.similarity_search_with_score(question, k=k, documents_ids=documents_ids)
