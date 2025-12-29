# agentic_backend/core/agents/runtime_context.py
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


from typing import Callable, Literal, Optional

from pydantic import BaseModel


class RuntimeContext(BaseModel):
    """
    Properties that can be passed to an agent at runtime (with a message)
    """

    selected_document_libraries_ids: list[str] | None = None
    selected_chat_context_ids: list[str] | None = None
    search_policy: str | None = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    access_token_expires_at: Optional[int] = None
    attachments_markdown: Optional[str] = (
        None  # if the session has some attachement files, this will hold their markdown representation
    )
    search_rag_scope: Optional[Literal["corpus_only", "hybrid", "general_only"]] = None
    deep_search: Optional[bool] = None


# Type alias for context provider functions
RuntimeContextProvider = Callable[[], Optional[RuntimeContext]]


def set_attachments_markdown(context: RuntimeContext, markdown: str) -> None:
    """Helper to set attachments markdown in context."""
    if markdown is not None and len(markdown) > 0:
        context.attachments_markdown = markdown


def get_document_library_tags_ids(context: RuntimeContext | None) -> list[str] | None:
    """Helper to extract document library IDs from context."""
    if not context:
        return None
    return context.selected_document_libraries_ids


def get_search_policy(context: RuntimeContext | None) -> str:
    """Helper to extract search policy from context."""
    if not context:
        return "semantic"
    return context.search_policy if context.search_policy else "semantic"


def get_rag_knowledge_scope(context: RuntimeContext | None) -> str:
    """
    Decide how the agent should use the corpus vs. general knowledge.

    Order of precedence:
    1. Explicit search_rag_scope if provided (corpus_only | hybrid | general_only)
    2. Explicit rag_knowledge_scope (deprecated legacy)
    3. Legacy skip_rag_search flag -> general_only
    4. Default -> hybrid (corpus + general knowledge)
    """
    if not context:
        return "hybrid"

    scope = context.search_rag_scope
    if scope in {"corpus_only", "hybrid", "general_only"}:
        return scope

    return "hybrid"


def get_deep_search_enabled(context: RuntimeContext | None) -> bool:
    """
    Decide whether deep search delegation should be enabled for this request.
    Mirrors the runtime-context precedence style used for RAG scope.
    """
    if not context:
        return False
    return bool(context.deep_search)


def get_chat_context_libraries_ids(context: RuntimeContext | None) -> list[str] | None:
    """Helper to extract profile library IDs from context."""
    if not context:
        return None
    return context.selected_chat_context_ids


def get_access_token(context: RuntimeContext | None) -> Optional[str]:
    """Helper to extract access token from context."""
    if not context:
        return None
    return context.access_token


def get_refresh_token(context: RuntimeContext | None) -> Optional[str]:
    """Helper to extract refresh token from context."""
    if not context:
        return None
    return context.refresh_token


def should_skip_rag_search(context: RuntimeContext | None) -> bool:
    """Helper to check whether retrieval should be bypassed for this message."""
    scope = get_rag_knowledge_scope(context)
    if scope == "general_only":
        return True
    return False


def is_corpus_only_mode(context: RuntimeContext | None) -> bool:
    """Helper to check whether the agent must answer only from corpus documents."""
    return get_rag_knowledge_scope(context) == "corpus_only"
