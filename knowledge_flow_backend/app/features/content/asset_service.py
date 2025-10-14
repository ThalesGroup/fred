# app/features/content/asset_service.py (Unified)

from __future__ import annotations

import mimetypes
import re
from typing import BinaryIO, List, Literal, Optional

from fred_core import Action, KeycloakUser, Resource, authorize
from pydantic import BaseModel, Field

from app.application_context import ApplicationContext
from app.core.stores.content.base_content_store import StoredObjectInfo

# Define the scope type for clarity
ScopeType = Literal["agents", "users"]

# ----- Public response models (Simplified) ---------------------------------


class AssetMeta(BaseModel):
    """
    Public metadata for any asset, inheriting file details and adding scope context.
    """

    # NOTE: Inheriting from StoredObjectInfo would be cleaner, but since we are
    # modifying the existing model, we'll keep the fields explicitly and rename 'agent'.
    scope: ScopeType  # The top-level bucket: 'agents' or 'users'
    entity_id: str  # The agent name OR the user's uid
    owner_user_id: str  # The ID of the user responsible for the asset
    key: str  # The short, normalized key
    file_name: str
    content_type: str
    size: int
    etag: Optional[str] = None
    modified: Optional[str] = None
    extra: dict = Field(default_factory=dict)


class AssetListResponse(BaseModel):
    """List wrapper."""

    items: List[AssetMeta]


# ----- Service ----------------------------------------------------------------------

SAFE_KEY = re.compile(r"^[A-Za-z0-9._-]{1,200}$")


class AssetService:  # RENAMED from AgentAssetService
    """
    Unified service for all binary assets (agent templates and user results).
    Handles two primary scopes: 'agents'/{agent_name} and 'users'/{user_uid}.
    """

    def __init__(self):
        self.store = ApplicationContext.get_instance().get_content_store()

    # ---- path rules ---------------------------------------------------------------

    @staticmethod
    def _prefix(scope: ScopeType, entity_id: str) -> str:
        """
        Generates the storage prefix: {scope}/{entity_id}/
        (e.g., 'agents/slide_maker/' or 'users/a1b2c3d4/')
        """
        # Note: In the user scope, entity_id will be user.uid.
        if not entity_id or "/" in entity_id or "\\" in entity_id:
            raise ValueError("Invalid entity_id.")
        return f"{scope}/{entity_id}/"  # DYNAMICALLY uses 'agents' or 'users'

    @staticmethod
    def _normalize_key(key: str) -> str:
        # Normalization logic remains unchanged
        k = (key or "").strip()
        if "/" in k or "\\" in k:
            k = k.replace("\\", "/").split("/")[-1]
        if not k or not SAFE_KEY.match(k):
            raise ValueError("Invalid asset key. Allowed: [A-Za-z0-9._-], length 1..200.")
        return k

    @staticmethod
    def _to_meta(scope: ScopeType, entity_id: str, user: KeycloakUser, key: str, info: StoredObjectInfo) -> AssetMeta:
        # Content-type may be absent from listings → guess from filename as a stable fallback.
        ct = info.content_type or (mimetypes.guess_type(info.file_name)[0]) or "application/octet-stream"
        return AssetMeta(
            scope=scope,  # NEW: Dynamic scope field
            entity_id=entity_id,  # RENAMED from 'agent'
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
        scope: ScopeType,  # NEW: Explicit scope parameter
        entity_id: str,  # RENAMED/REPURPOSED: Agent name or user UID
        key: str,
        stream: BinaryIO,
        *,
        content_type: Optional[str],
        file_name: Optional[str] = None,
    ) -> AssetMeta:
        """Store/replace an asset under a specific scope/entity_id."""
        norm = self._normalize_key(key)
        storage_key = self._prefix(scope, entity_id) + norm  # Uses dynamic prefix
        ct = content_type or (mimetypes.guess_type(file_name or norm)[0]) or "application/octet-stream"

        info = self.store.put_object(storage_key, stream, content_type=ct)

        if not info.file_name:
            info.file_name = file_name or norm
        return self._to_meta(scope, entity_id, user, norm, info)

    @authorize(Action.READ, Resource.DOCUMENTS)
    async def list_assets(
        self,
        user: KeycloakUser,
        scope: ScopeType,
        entity_id: str,
    ) -> AssetListResponse:
        prefix = self._prefix(scope, entity_id)  # Uses dynamic prefix
        infos = self.store.list_objects(prefix)

        items: List[AssetMeta] = []
        for info in infos:
            # Keep listing flat under prefix.
            short_key = info.key[len(prefix) :] if info.key.startswith(prefix) else info.key
            if "/" in short_key:
                continue
            items.append(self._to_meta(scope, entity_id, user, short_key, info))

        return AssetListResponse(items=items)

    @authorize(Action.READ, Resource.DOCUMENTS)
    async def stat_asset(
        self,
        user: KeycloakUser,
        scope: ScopeType,  # NEW: Explicit scope parameter
        entity_id: str,  # RENAMED/REPURPOSED
        key: str,
    ) -> AssetMeta:
        norm = self._normalize_key(key)
        storage_key = self._prefix(scope, entity_id) + norm  # Uses dynamic prefix
        info = self.store.stat_object(storage_key)
        return self._to_meta(scope, entity_id, user, norm, info)

    @authorize(Action.READ, Resource.DOCUMENTS)
    async def stream_asset(
        self,
        user: KeycloakUser,
        scope: ScopeType,  # NEW: Explicit scope parameter
        entity_id: str,  # RENAMED/REPURPOSED
        key: str,
        *,
        start: Optional[int] = None,
        length: Optional[int] = None,
    ) -> BinaryIO:
        """
        Returns a streaming BinaryIO (works with StreamingResponse).
        """
        norm = self._normalize_key(key)
        storage_key = self._prefix(scope, entity_id) + norm  # Uses dynamic prefix
        return self.store.get_object_stream(storage_key, start=start, length=length)

    @authorize(Action.UPDATE, Resource.DOCUMENTS)
    async def delete_asset(
        self,
        user: KeycloakUser,
        scope: ScopeType,  # NEW: Explicit scope parameter
        entity_id: str,  # RENAMED/REPURPOSED
        key: str,
    ) -> None:
        norm = self._normalize_key(key)
        storage_key = self._prefix(scope, entity_id) + norm  # Uses dynamic prefix
        self.store.delete_object(storage_key)
