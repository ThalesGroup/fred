# Copyright Thales 2025
# Apache-2.0

from dataclasses import dataclass
from typing import Optional, Dict

from fred_core import ThreadSafeLRUCache

# Reuse your existing ThreadSafeLRUCache
# from fred_core.utils.lru_cache import ThreadSafeLRUCache   # if stored elsewhere
# For this snippet we assume it's already imported in context.

@dataclass
class AttachmentData:
    """
    Lightweight in-memory view of an attached document.

    Fred rationale:
    - Only keeps what the agent needs for *retrieval-implicit reasoning*:
      a Markdown summary and minimal metadata.
    - No binary content or embeddings stored here.
    """
    name: str
    mime: Optional[str]
    size_bytes: Optional[int]
    summary_md: str


class SessionInMemoryAttachments:
    """
    Holds in-RAM attachment summaries per session.
    Fred rationale:
    - Temporary, session-scoped cache for implicit retrieval.
    - Built on the same LRU utility already used elsewhere in Fred
      → consistent behaviour, no extra complexity.
    """

    def __init__(self, max_sessions: int = 500, max_attachments_per_session: int = 4):
        self._max_sessions = max_sessions
        self._max_att_per_session = max_attachments_per_session
        # one LRU for sessions; each session holds a small dict of attachments
        self._sessions = ThreadSafeLRUCache[str, Dict[str, AttachmentData]](max_sessions)

    # --------------------------------------------------------------
    # CRUD
    # --------------------------------------------------------------

    def put(
        self,
        session_id: str,
        attachment_id: str,
        name: str,
        summary_md: str,
        mime: Optional[str] = None,
        size_bytes: Optional[int] = None,
    ) -> None:
        """
        Store or replace a Markdown summary for an attachment.
        Evicts oldest attachment if the session exceeds its cap.
        """
        bucket = self._sessions.get(session_id) or {}
        # manual per-session cap
        if len(bucket) >= self._max_att_per_session and attachment_id not in bucket:
            oldest_key = next(iter(bucket))
            bucket.pop(oldest_key, None)
        bucket[attachment_id] = AttachmentData(name, mime, size_bytes, summary_md)
        self._sessions.set(session_id, bucket)

    def get(self, session_id: str, attachment_id: str) -> Optional[AttachmentData]:
        """Return the attachment summary if present."""
        bucket = self._sessions.get(session_id)
        if not bucket:
            return None
        return bucket.get(attachment_id)

    def delete(self, session_id: str, attachment_id: str) -> bool:
        """Remove a specific attachment from a session."""
        bucket = self._sessions.get(session_id)
        if not bucket or attachment_id not in bucket:
            return False
        del bucket[attachment_id]
        if not bucket:
            self._sessions.delete(session_id)
        else:
            self._sessions.set(session_id, bucket)
        return True

    def clear_session(self, session_id: str) -> None:
        """Remove all attachments for a session."""
        self._sessions.delete(session_id)

    def list_ids(self, session_id: str) -> list[str]:
        """List all attachment IDs for a session."""
        bucket = self._sessions.get(session_id)
        return list(bucket.keys()) if bucket else []

    def get_session_attachments_markdown(self, session_id: str) -> str:
        """Concatenate all attachment summaries for a session."""
        bucket = self._sessions.get(session_id)
        if not bucket:
            return ""
        return "\n\n".join(att.summary_md for att in bucket.values())
    
    def get_session_attachment_names(self, session_id: str) -> list[str]:
        """List all attachment names for a session."""
        bucket = self._sessions.get(session_id)
        if not bucket:
            return []
        return [att.name for att in bucket.values()]

    def stats(self) -> dict:
        """Basic observability hook."""
        return {
            "sessions": len(self._sessions.keys()),
            "max_sessions": self._max_sessions,
            "max_attachments_per_session": self._max_att_per_session,
        }
