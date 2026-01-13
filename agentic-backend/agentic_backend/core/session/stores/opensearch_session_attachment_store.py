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

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from fred_core import ThreadSafeLRUCache, validate_index_mapping
from opensearchpy import NotFoundError, OpenSearch, RequestsHttpConnection

from agentic_backend.core.session.stores.base_session_attachment_store import (
    BaseSessionAttachmentStore,
    SessionAttachmentRecord,
)

logger = logging.getLogger(__name__)

MAPPING = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "refresh_interval": "1s",
    },
    "mappings": {
        "properties": {
            "session_id": {"type": "keyword"},
            "attachment_id": {"type": "keyword"},
            "name": {"type": "keyword"},
            "mime": {"type": "keyword"},
            "size_bytes": {"type": "long"},
            "summary_md": {"type": "text"},
            "document_uid": {"type": "keyword"},
            "created_at": {"type": "date"},
            "updated_at": {"type": "date"},
        }
    },
}


def _doc_id(session_id: str, attachment_id: str) -> str:
    return f"{session_id}::{attachment_id}"


def _parse_dt(value: Optional[str | datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        # OpenSearch returns ISO-8601 strings; fromisoformat handles tz offsets.
        return datetime.fromisoformat(value)
    except Exception:
        return None


class OpensearchSessionAttachmentStore(BaseSessionAttachmentStore):
    """
    OpenSearch-backed storage for session attachments summaries.
    Kept for backward compatibility with legacy deployments.
    """

    def __init__(
        self,
        host: str,
        index: str,
        username: str,
        password: str,
        secure: bool = False,
        verify_certs: bool = False,
    ):
        self.client = OpenSearch(
            host,
            http_auth=(username, password),
            use_ssl=secure,
            verify_certs=verify_certs,
            connection_class=RequestsHttpConnection,
        )
        self._cache: ThreadSafeLRUCache[str, List[SessionAttachmentRecord]] = (
            ThreadSafeLRUCache(max_size=1000)
        )
        self.index = index
        if not self.client.indices.exists(index=index):
            self.client.indices.create(index=index, body=MAPPING)
            logger.info("[SESSION][OS] Created attachments index %s", index)
        else:
            validate_index_mapping(self.client, index, MAPPING)
            logger.info("[SESSION][OS] Attachments index %s ready", index)

    def save(self, record: SessionAttachmentRecord) -> None:
        now = datetime.now(timezone.utc)
        created_at = record.created_at or now
        updated_at = record.updated_at or now
        body = {
            "session_id": record.session_id,
            "attachment_id": record.attachment_id,
            "name": record.name,
            "mime": record.mime,
            "size_bytes": record.size_bytes,
            "summary_md": record.summary_md,
            "document_uid": record.document_uid,
            "created_at": created_at.isoformat(),
            "updated_at": updated_at.isoformat(),
        }
        self.client.index(
            index=self.index,
            id=_doc_id(record.session_id, record.attachment_id),
            body=body,
        )
        # Update cache for this session_id
        try:
            cached = self._cache.get(record.session_id)
            if cached is not None:
                # Replace or append
                next_records: List[SessionAttachmentRecord] = []
                replaced = False
                for existing in cached:
                    if existing.attachment_id == record.attachment_id:
                        next_records.append(record)
                        replaced = True
                    else:
                        next_records.append(existing)
                if not replaced:
                    next_records.append(record)
                self._cache.set(record.session_id, next_records)
        except Exception:
            logger.debug(
                "[SESSION][OS] Failed to refresh cache for session %s",
                record.session_id,
                exc_info=True,
            )

    def list_for_session(self, session_id: str) -> List[SessionAttachmentRecord]:
        cached = self._cache.get(session_id)
        if cached is not None:
            logger.debug("[SESSION][OS] cache hit for session %s", session_id)
            return cached

        query = {"query": {"term": {"session_id": {"value": session_id}}}}
        response = self.client.search(
            index=self.index,
            body=query,
            params={"size": 1000, "sort": "created_at:asc"},
        )
        records: List[SessionAttachmentRecord] = []
        for hit in response.get("hits", {}).get("hits", []):
            src = hit.get("_source", {})
            records.append(
                SessionAttachmentRecord(
                    session_id=src.get("session_id", session_id),
                    attachment_id=src.get("attachment_id"),
                    name=src.get("name", ""),
                    mime=src.get("mime"),
                    size_bytes=src.get("size_bytes"),
                    summary_md=src.get("summary_md", ""),
                    document_uid=src.get("document_uid"),
                    created_at=_parse_dt(src.get("created_at")),
                    updated_at=_parse_dt(src.get("updated_at")),
                )
            )
        self._cache.set(session_id, records)
        return records

    def delete(self, session_id: str, attachment_id: str) -> None:
        try:
            self.client.delete(
                index=self.index,
                id=_doc_id(session_id, attachment_id),
            )
            cached = self._cache.get(session_id)
            if cached is not None:
                self._cache.set(
                    session_id,
                    [r for r in cached if r.attachment_id != attachment_id],
                )
        except Exception:
            logger.exception(
                "[SESSION][OS] Failed to delete attachment %s for session %s",
                attachment_id,
                session_id,
            )

    def delete_for_session(self, session_id: str) -> None:
        query = {"query": {"term": {"session_id": {"value": session_id}}}}
        try:
            self.client.delete_by_query(
                index=self.index,
                body=query,
                # OpenSearch expects lowercase true/false strings for query params
                params={"refresh": "true"},
            )
            self._cache.delete(session_id)
        except NotFoundError:
            logger.warning(
                "[SESSION][OS] No attachments to delete for session %s", session_id
            )
        except Exception:
            logger.exception(
                "[SESSION][OS] Failed to delete attachments for session %s",
                session_id,
            )
