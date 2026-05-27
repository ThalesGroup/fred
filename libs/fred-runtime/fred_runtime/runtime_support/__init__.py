# Copyright Thales 2026
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
"""
Runtime support utilities for Fred v2 agents.
"""

from .request_context_helpers import (
    RuntimeContextProvider,
    get_access_token,
    get_chat_context_libraries_ids,
    get_deep_search_enabled,
    get_document_library_tags_ids,
    get_document_uids,
    get_language,
    get_rag_knowledge_scope,
    get_refresh_token,
    get_search_policy,
    get_vector_search_scopes,
    is_corpus_only_mode,
    set_attachments_markdown,
    should_skip_rag_search,
)
from .sql_checkpointer import FredSqlCheckpointer
from .user_token_refresher import refresh_user_access_token_from_keycloak

__all__ = [
    "FredSqlCheckpointer",
    "refresh_user_access_token_from_keycloak",
    "RuntimeContextProvider",
    "set_attachments_markdown",
    "get_document_library_tags_ids",
    "get_search_policy",
    "get_document_uids",
    "get_rag_knowledge_scope",
    "get_vector_search_scopes",
    "get_deep_search_enabled",
    "get_chat_context_libraries_ids",
    "get_access_token",
    "get_refresh_token",
    "get_language",
    "is_corpus_only_mode",
    "should_skip_rag_search",
]
