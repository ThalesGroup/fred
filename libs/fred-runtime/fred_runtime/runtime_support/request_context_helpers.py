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

from __future__ import annotations

from typing import Callable, Optional

from fred_sdk.contracts.context import RuntimeContext

# Type alias for context provider functions
RuntimeContextProvider = Callable[[], Optional[RuntimeContext]]


def set_attachments_markdown(context: RuntimeContext, markdown: str) -> None:
    """Attach markdown content for session attachments to the runtime context.

    Why: centralize where attachment markdown is stored for runtime consumers.
    How: pass a RuntimeContext plus a non-empty markdown string.
    Example:
        >>> ctx = RuntimeContext()
        >>> set_attachments_markdown(ctx, "# Notes")
    """
    if markdown is not None and len(markdown) > 0:
        context.attachments_markdown = markdown


def get_document_library_tags_ids(context: RuntimeContext | None) -> list[str] | None:
    """Return document library tag ids for RAG scoping.

    Why: avoid scattering runtime_context field lookups across the codebase.
    How: pass a RuntimeContext (or None) to extract tag ids.
    Example:
        >>> get_document_library_tags_ids(RuntimeContext(selected_document_libraries_ids=["a"]))
        ['a']
    """
    if not context:
        return None
    return context.selected_document_libraries_ids


def get_search_policy(context: RuntimeContext | None) -> str:
    """Return the search policy with a stable default.

    Why: normalize the default search policy when the context omits it.
    How: pass a RuntimeContext (or None); "semantic" is used when missing.
    Example:
        >>> get_search_policy(RuntimeContext())
        'semantic'
    """
    if not context:
        return "semantic"
    return context.search_policy if context.search_policy else "semantic"


def get_document_uids(context: RuntimeContext | None) -> list[str] | None:
    """Return document UIDs selected for the current request.

    Why: provide a single helper to read document selection inputs.
    How: pass a RuntimeContext (or None) to extract document UIDs.
    Example:
        >>> get_document_uids(RuntimeContext(selected_document_uids=["d1"]))
        ['d1']
    """
    if not context:
        return None
    return context.selected_document_uids


def get_rag_knowledge_scope(context: RuntimeContext | None) -> str:
    """
    Decide how the agent should use the corpus vs. general knowledge.

    Why: normalize RAG scope handling to one shared place.
    How: pass a RuntimeContext (or None) and receive the resolved scope string.
    Example:
        >>> get_rag_knowledge_scope(RuntimeContext(search_rag_scope="corpus_only"))
        'corpus_only'

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


def get_vector_search_scopes(context: RuntimeContext | None) -> tuple[bool, bool]:
    """
    Resolve which vector search scopes to include for the current request.
    Returns (include_session_scope, include_corpus_scope).

    Why: keep scope decision logic consistent between callers.
    How: pass a RuntimeContext (or None) to compute the include flags.
    Example:
        >>> get_vector_search_scopes(RuntimeContext(search_rag_scope="corpus_only"))
        (False, True)
    """
    scope = get_rag_knowledge_scope(context)
    if scope == "corpus_only":
        default_session, default_corpus = False, True
    elif scope == "general_only":
        default_session, default_corpus = False, False
    else:
        default_session, default_corpus = True, True

    if not context:
        return default_session, default_corpus

    include_session_scope = (
        default_session
        if context.include_session_scope is None
        else bool(context.include_session_scope)
    )
    include_corpus_scope = (
        default_corpus
        if context.include_corpus_scope is None
        else bool(context.include_corpus_scope)
    )
    return include_session_scope, include_corpus_scope


def get_deep_search_enabled(context: RuntimeContext | None) -> bool:
    """
    Decide whether deep search delegation should be enabled for this request.

    Why: keep deep search enablement aligned with runtime context precedence.
    How: pass a RuntimeContext (or None); defaults to False when missing.
    Example:
        >>> get_deep_search_enabled(RuntimeContext(deep_search=True))
        True
    """
    if not context:
        return False
    return bool(context.deep_search)


def get_chat_context_libraries_ids(context: RuntimeContext | None) -> list[str] | None:
    """Return chat-context library ids for profile scoping.

    Why: avoid repeated attribute reads for profile library selection.
    How: pass a RuntimeContext (or None) to extract chat context ids.
    Example:
        >>> get_chat_context_libraries_ids(RuntimeContext(selected_chat_context_ids=["p1"]))
        ['p1']
    """
    if not context:
        return None
    return context.selected_chat_context_ids


def get_access_token(context: RuntimeContext | None) -> Optional[str]:
    """Return access token from runtime context when present.

    Why: standardize access token reads for client helpers.
    How: pass a RuntimeContext (or None); returns None when missing.
    Example:
        >>> get_access_token(RuntimeContext(access_token="token"))
        'token'
    """
    if not context:
        return None
    return context.access_token


def get_refresh_token(context: RuntimeContext | None) -> Optional[str]:
    """Return refresh token from runtime context when present.

    Why: standardize refresh token reads for auth refresh helpers.
    How: pass a RuntimeContext (or None); returns None when missing.
    Example:
        >>> get_refresh_token(RuntimeContext(refresh_token="refresh"))
        'refresh'
    """
    if not context:
        return None
    return context.refresh_token


def should_skip_rag_search(context: RuntimeContext | None) -> bool:
    """Return True when retrieval should be bypassed for this request.

    Why: encapsulate the skip logic behind one helper.
    How: pass a RuntimeContext (or None); returns True when scope is general_only.
    Example:
        >>> should_skip_rag_search(RuntimeContext(search_rag_scope="general_only"))
        True
    """
    scope = get_rag_knowledge_scope(context)
    if scope == "general_only":
        return True
    return False


def is_corpus_only_mode(context: RuntimeContext | None) -> bool:
    """Return True when the agent must answer only from corpus documents.

    Why: give downstream helpers a clear corpus-only check.
    How: pass a RuntimeContext (or None); returns True when scope is corpus_only.
    Example:
        >>> is_corpus_only_mode(RuntimeContext(search_rag_scope="corpus_only"))
        True
    """
    return get_rag_knowledge_scope(context) == "corpus_only"


def get_language(context: RuntimeContext | None) -> str:
    """Return preferred language if provided, otherwise empty string.

    Why: normalize language reads for UI and HITL messaging.
    How: pass a RuntimeContext (or None); returns "" when missing.
    Example:
        >>> get_language(RuntimeContext(language="fr"))
        'fr'
    """
    if not context:
        return ""
    return context.language or ""
