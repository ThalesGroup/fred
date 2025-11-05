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

from dataclasses import dataclass
from typing import Optional, Dict

from fred_core import ThreadSafeLRUCache

@dataclass
class AttachmentData:
    """
    Lightweight in-memory store of attached document.

    When a user uploads a document to a chat session, we process it
    (e.g., extract text, summarize) and keep a brief Markdown summary
    in memory for the duration of the session.

    This store is reusing Fred's ThreadSafeLRUCache utility.

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
    Lightweight in-memory store of attached document.

    When a user uploads a document to a chat session, we process it
    (e.g., extract text, summarize) and keep a brief Markdown summary
    in memory for the duration of the session.

    This is simple effective design to avoid external storage for
    transient data that is only needed during the chat session lifetime.
    """

    def __init__(self, max_sessions: int = 500, max_attachments_per_session: int = 4):
        self._max_sessions = max_sessions
        self._max_att_per_session = max_attachments_per_session
        # one LRU for sessions; each session holds a small dict of attachments
        self._sessions = ThreadSafeLRUCache[str, Dict[str, AttachmentData]](
            max_sessions
        )

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
