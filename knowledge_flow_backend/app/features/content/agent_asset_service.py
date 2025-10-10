# app/features/assets/agent_asset_service.py
# Copyright Thales 2025
#
# Purpose (Fred):
# - Small, typed façade over BaseContentStore for *agent-scoped* assets.
# - Encodes the storage convention: agents/{agent}/{user_id}/{key}
# - Keeps controllers slim (HTTP only) and isolates storage concerns here.

from __future__ import annotations

import mimetypes
import re
from typing import BinaryIO, List, Optional

from pydantic import BaseModel, Field
from fred_core import Action, KeycloakUser, Resource, authorize

from app.core.stores.content.base_content_store import StoredObjectInfo
from app.application_context import ApplicationContext  # to obtain BaseContentStore

# ----- Public response models (hover-over friendly) ---------------------------------


class AgentAssetMeta(BaseModel):
    """
    Public metadata for an agent asset.
    Why this shape:
    - Controllers can return it directly as JSON (FastAPI response_model).
    - Agents can rely on stable, typed fields regardless of storage backend.
    """

    agent: str
    owner_user_id: str
    key: str
    file_name: str
    content_type: str
    size: int
    etag: Optional[str] = None
    modified: Optional[str] = None
    extra: dict = Field(default_factory=dict)  # reserved for future tagging/notes


class AgentAssetListResponse(BaseModel):
    """List wrapper to stay extensible (pagination, next_cursor, etc. later)."""

    items: List[AgentAssetMeta]


# ----- Service ----------------------------------------------------------------------

SAFE_KEY = re.compile(r"^[A-Za-z0-9._-]{1,200}$")


class AgentAssetService:
    """
    Narrow service for agent-scoped binary assets (e.g., PPTX templates).
    Rationale:
    - Single responsibility: map agent/user/key → flat object key; delegate I/O to BaseContentStore.
    - Keeps all validation + path rules in one place (controller stays thin).
    """

    def __init__(self):
        # Acquire the canonical store (FS/MinIO) from the app context.
        self.store = ApplicationContext.get_instance().get_content_store()

    # ---- path rules ---------------------------------------------------------------

    @staticmethod
    def _prefix(agent: str, user: KeycloakUser) -> str:
        # Clear tenancy boundary for lifecycle + authorization:
        return f"agents/{agent}/{user.uid}/"

    @staticmethod
    def _normalize_key(key: str) -> str:
        # Single-level, predictable keys → easy to list + no traversal headaches.
        k = (key or "").strip()
        if "/" in k or "\\" in k:
            k = k.replace("\\", "/").split("/")[-1]
        if not k or not SAFE_KEY.match(k):
            raise ValueError("Invalid asset key. Allowed: [A-Za-z0-9._-], length 1..200.")
        return k

    @staticmethod
    def _to_meta(agent: str, user: KeycloakUser, key: str, info: StoredObjectInfo) -> AgentAssetMeta:
        # Content-type may be absent from listings → guess from filename as a stable fallback.
        ct = info.content_type or (mimetypes.guess_type(info.file_name)[0]) or "application/octet-stream"
        return AgentAssetMeta(
            agent=agent,
            owner_user_id=user.uid,
            key=key,
            file_name=info.file_name,
            content_type=ct,
            size=info.size,
            etag=info.etag,
            modified=info.modified.isoformat() if info.modified else None,
        )

    # ---- public API used by controllers / MCP tools --------------------------------

    @authorize(Action.UPDATE, Resource.DOCUMENTS)
    async def put_asset(
        self,
        user: KeycloakUser,
        agent: str,
        key: str,
        stream: BinaryIO,
        *,
        content_type: Optional[str],
        file_name: Optional[str] = None,
    ) -> AgentAssetMeta:
        """
        Store/replace a user-scoped asset for an agent.
        Why we ask for content_type/file_name:
        - Backends (S3/MinIO) benefit from explicit content-type; we still guess if missing.
        """
        norm = self._normalize_key(key)
        storage_key = self._prefix(agent, user) + norm
        ct = content_type or (mimetypes.guess_type(file_name or norm)[0]) or "application/octet-stream"

        info = self.store.put_object(storage_key, stream, content_type=ct)

        # Ensure filename is stable even if backend didn’t set it explicitly.
        if not info.file_name:
            info.file_name = file_name or norm
        return self._to_meta(agent, user, norm, info)

    @authorize(Action.READ, Resource.DOCUMENTS)
    async def list_assets(self, user: KeycloakUser, agent: str) -> AgentAssetListResponse:
        prefix = self._prefix(agent, user)
        infos = self.store.list_objects(prefix)

        items: List[AgentAssetMeta] = []
        for info in infos:
            # Keep listing flat under prefix.
            short_key = info.key[len(prefix) :] if info.key.startswith(prefix) else info.key
            if "/" in short_key:
                continue
            items.append(self._to_meta(agent, user, short_key, info))

        return AgentAssetListResponse(items=items)

    @authorize(Action.READ, Resource.DOCUMENTS)
    async def stat_asset(self, user: KeycloakUser, agent: str, key: str) -> AgentAssetMeta:
        norm = self._normalize_key(key)
        storage_key = self._prefix(agent, user) + norm
        info = self.store.stat_object(storage_key)
        return self._to_meta(agent, user, norm, info)

    @authorize(Action.READ, Resource.DOCUMENTS)
    async def stream_asset(
        self,
        user: KeycloakUser,
        agent: str,
        key: str,
        *,
        start: Optional[int] = None,
        length: Optional[int] = None,
    ) -> BinaryIO:
        """
        Returns a streaming BinaryIO (works with StreamingResponse).
        If start/length provided → partial content, suitable for Range requests.
        """
        norm = self._normalize_key(key)
        storage_key = self._prefix(agent, user) + norm
        return self.store.get_object_stream(storage_key, start=start, length=length)

    @authorize(Action.UPDATE, Resource.DOCUMENTS)
    async def delete_asset(self, user: KeycloakUser, agent: str, key: str) -> None:
        norm = self._normalize_key(key)
        storage_key = self._prefix(agent, user) + norm
        self.store.delete_object(storage_key)
