# app/features/content/asset_service.py (Unified)

from __future__ import annotations

import mimetypes
import re
import shutil
import tempfile
from pathlib import Path
from typing import BinaryIO, List, Literal, Optional

from fred_core import Action, KeycloakUser, Resource, authorize
from pydantic import BaseModel, Field

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.core.stores.content.base_content_store import StoredObjectInfo
from knowledge_flow_backend.features.ingestion.ingestion_service import get_ingestion_service
from knowledge_flow_backend.features.tag.tag_service import TagCreate, TagService, TagType

USER_ASSET_TAG_NAME = "User Assets"
USER_ASSET_TAG_PATH = "user-assets"
USER_ASSET_TAG_DESCRIPTION = "Personal assets generated or uploaded by the current user (including agent outputs)."

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
    document_uid: Optional[str] = ""
    extra: dict = Field(default_factory=dict)


class AssetListResponse(BaseModel):
    """List wrapper."""

    items: List[AssetMeta]


# ----- Service ----------------------------------------------------------------------

SAFE_KEY = re.compile(r"^[A-Za-z0-9._-]{1,200}$")


class AssetService:  # RENAMED from AgentAssetService
    """
    Unified service for all binary assets (agent templates and user results).
    Handles two primary scopes: 'agents'/{agent_id} and 'users'/{user_uid}.
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
            document_uid=info.document_uid,
            modified=info.modified.isoformat() if info.modified else None,
        )

    # ---- public API used by controllers / MCP tools --------------------------------

    @authorize(Action.UPDATE, Resource.DOCUMENTS)
    async def put_asset(
        self,
        user: KeycloakUser,
        scope: ScopeType,
        entity_id: str,
        key: str,
        stream: BinaryIO,
        *,
        content_type: Optional[str],
        file_name: Optional[str] = None,
    ):
        norm_key = self._normalize_key(key)
        storage_key = self._prefix(scope, entity_id) + norm_key
        ct = content_type or (mimetypes.guess_type(file_name or norm_key)[0]) or "application/octet-stream"

        # For agent-generated assets, skip ingestion and store directly
        # This avoids processing overhead and potential errors for binary outputs
        if scope == "agents" or scope == "users":
            info = self.store.put_object(storage_key, stream, content_type=ct)
            # Set file_name for proper display
            info.file_name = file_name or norm_key
            return self._to_meta(scope, entity_id, user, norm_key, info)

        # Legacy path: Full ingestion for other scopes (currently unused)
        # This is kept for backward compatibility but may be removed in the future
        ingestion_service = get_ingestion_service()
        tag_service = TagService()

        # 0️⃣ Get or create the "user_asset" tag (single source of truth)
        existing_tags = await tag_service.list_all_tags_for_user(user, tag_type=TagType.DOCUMENT)
        user_asset_tag = next((t for t in existing_tags if t.name == USER_ASSET_TAG_NAME), None)
        if user_asset_tag is None:
            created_tag = await tag_service.create_tag_for_user(
                TagCreate(
                    name=USER_ASSET_TAG_NAME,
                    path=USER_ASSET_TAG_PATH,
                    description=USER_ASSET_TAG_DESCRIPTION,
                    type=TagType.DOCUMENT,
                ),
                user,
            )
            tag_id = created_tag.id
        else:
            tag_id = user_asset_tag.id

        # 1️⃣ Create a temporary folder, but use the *real* filename
        tmp_dir = Path(tempfile.mkdtemp())
        final_file_path = tmp_dir / (file_name or key)
        with open(final_file_path, "wb") as f:
            shutil.copyfileobj(stream, f)

        # 2️⃣ Extract metadata using the tag ID
        metadata = ingestion_service.extract_metadata(
            user=user,
            file_path=final_file_path,
            tags=[tag_id],
            source_tag="fred",
        )

        # 3️⃣ Save input
        ingestion_service.save_input(user, metadata=metadata, input_dir=tmp_dir)

        # 4️⃣ Save metadata
        await ingestion_service.save_metadata(user, metadata=metadata)

        # 5️⃣ Store the file in the content store with the correct name
        info = self.store.put_object(storage_key, final_file_path.open("rb"), content_type=ct)
        info.document_uid = metadata.document_uid

        # Clean up
        shutil.rmtree(tmp_dir, ignore_errors=True)

        return self._to_meta(scope, entity_id, user, norm_key, info)

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
