from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.chatbot.session_orchestrator import (
    _sanitize_runtime_context_for_debug,
)


def test_sanitize_runtime_context_for_debug_removes_sensitive_fields() -> None:
    runtime_context = RuntimeContext(
        language="fr",
        session_id="session-1",
        user_id="user-123",
        user_groups=["/admin"],
        selected_document_libraries_ids=["lib-a"],
        selected_document_uids=["doc-1"],
        selected_chat_context_ids=["ctx-1"],
        search_policy="semantic",
        access_token="secret-access",
        refresh_token="secret-refresh",
        access_token_expires_at=123456789,
        attachments_markdown="# very long attachment dump",
        search_rag_scope="hybrid",
        deep_search=True,
        include_session_scope=True,
        include_corpus_scope=False,
    )

    sanitized = _sanitize_runtime_context_for_debug(runtime_context)

    assert sanitized.language == "fr"
    assert sanitized.session_id == "session-1"
    assert sanitized.selected_document_libraries_ids == ["lib-a"]
    assert sanitized.selected_document_uids == ["doc-1"]
    assert sanitized.selected_chat_context_ids == ["ctx-1"]
    assert sanitized.search_policy == "semantic"
    assert sanitized.search_rag_scope == "hybrid"
    assert sanitized.deep_search is True
    assert sanitized.include_session_scope is True
    assert sanitized.include_corpus_scope is False

    assert sanitized.user_id is None
    assert sanitized.user_groups is None
    assert sanitized.access_token is None
    assert sanitized.refresh_token is None
    assert sanitized.access_token_expires_at is None
    assert sanitized.attachments_markdown is None
