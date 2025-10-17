# app/features/content/asset_controller.py (Single Controller)

import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from fred_core import KeycloakUser, get_current_user
from starlette.background import BackgroundTask

from app.features.content.asset_service import AssetListResponse, AssetMeta, AssetService, ScopeType
from app.features.content.content_controller import parse_range_header  # reuse helper

logger = logging.getLogger(__name__)


# Re-use the helper function
def _close_stream(s) -> None:
    try:
        s.close()
    except Exception:
        logger.warning("Failed to close stream", exc_info=True)
        pass


class AssetController:
    """
    Unified CRUD controller for both agent-scoped and user-scoped assets.

    Endpoints:
    - /agent-assets/{entity_id}/... (where entity_id is the agent name)
    - /user-assets/... (where entity_id is the user.uid)
    """

    def __init__(self, router: APIRouter):
        self.service = AssetService()
        self._register_routes(router)

    def _register_routes(self, router: APIRouter):
        # ----------------------------------------------------------------------
        # 1. AGENT SCOPE (Requires {entity_id} in path, where entity_id = agent name)
        # ----------------------------------------------------------------------

        # --- AGENT UPLOAD ---
        @router.post(
            "/agent-assets/{agent}/upload",
            tags=["Agent Assets"],
            summary="Upload or replace a per-user asset for an agent",
            response_model=AssetMeta,
        )
        async def upload_agent_asset(
            agent: str,  # entity_id = agent name
            user: KeycloakUser = Depends(get_current_user),
            file: UploadFile = File(..., description="Binary payload (e.g., .pptx)"),
            key: Optional[str] = Form(None, description="Logical asset key (defaults to uploaded filename)"),
            content_type_override: Optional[str] = Form(None, description="Force a content-type if needed"),
        ) -> AssetMeta:
            if not (key or file.filename):
                raise HTTPException(status_code=400, detail="Missing asset key or filename")
            try:
                # SCOPE: 'agents', ENTITY_ID: agent (from path)
                meta = await self.service.put_asset(
                    user=user,
                    scope="agents",
                    entity_id=agent,
                    key=(key if key is not None else file.filename or "asset"),
                    stream=file.file,
                    content_type=content_type_override or (file.content_type or "application/octet-stream"),
                    file_name=file.filename or (key or "asset"),
                )
                return meta
            finally:
                try:
                    await file.close()
                except Exception:
                    logger.warning("Failed to close uploaded file", exc_info=True)
                    pass

        # --- AGENT LIST ---
        @router.get(
            "/agent-assets/{agent}",
            tags=["Agent Assets"],
            summary="List user's assets for an agent",
            response_model=AssetListResponse,
        )
        async def list_agent_assets(agent: str, user: KeycloakUser = Depends(get_current_user)) -> AssetListResponse:
            # SCOPE: 'agents', ENTITY_ID: agent (from path)
            return await self.service.list_assets(user=user, scope="agents", entity_id=agent)

        # --- AGENT STREAM / DOWNLOAD (Helper uses this logic too) ---
        @router.get(
            "/agent-assets/{agent}/{key}",
            tags=["Agent Assets"],
            summary="Stream or download an asset (supports Range)",
            # ... (responses remain the same)
        )
        async def get_agent_asset(
            agent: str,
            key: str,
            user: KeycloakUser = Depends(get_current_user),
            range_header: Optional[str] = Header(None, alias="Range"),
        ):
            # Calls the generic streaming handler
            return await self._handle_stream(user, "agents", agent, key, range_header)

        # --- AGENT DELETE ---
        @router.delete(
            "/agent-assets/{agent}/{key}",
            tags=["Agent Assets"],
            summary="Delete a user's asset",
            response_model=dict,
        )
        async def delete_agent_asset(agent: str, key: str, user: KeycloakUser = Depends(get_current_user)):
            # SCOPE: 'agents', ENTITY_ID: agent (from path)
            await self.service.delete_asset(user=user, scope="agents", entity_id=agent, key=key)
            return {"ok": True, "key": key}

        # ----------------------------------------------------------------------
        # 2. USER SCOPE (entity_id = user.uid, taken from JWT or from parameter)
        # ----------------------------------------------------------------------

        # --- NEW HELPER to get the effective entity_id ---
        def _get_entity_id(current_user: KeycloakUser, user_id_override: Optional[str]) -> str:
            """
            Determines the entity_id (the user ID) to use for the operation.

            NOTE: Security and permission checks for 'user_id_override' must be
            handled by the authentication layer (KeycloakUser) or a custom dependency.
            For this implementation, we simply trust the override if provided.
            """
            return user_id_override or current_user.uid

        # --- USER UPLOAD ---
        @router.post(
            "/user-assets/upload",
            tags=["User Assets"],
            summary="Upload or replace a per-user result asset",
            response_model=AssetMeta,
        )
        async def upload_user_asset(
            user: KeycloakUser = Depends(get_current_user),
            file: UploadFile = File(..., description="Binary payload (e.g., .pptx, .pdf)"),
            key: Optional[str] = Form(None, description="Logical asset key (defaults to uploaded filename)"),
            content_type_override: Optional[str] = Form(None, description="Force a content-type if needed"),
            # NEW: Explicit user ID for the actual asset owner
            user_id_override: Optional[str] = Form(None, description="[AGENT USE ONLY] Explicit user ID of the asset owner"),
        ) -> AssetMeta:
            if not (key or file.filename):
                raise HTTPException(status_code=400, detail="Missing asset key or filename")

            entity_id = _get_entity_id(user, user_id_override)

            try:
                # SCOPE: 'users', ENTITY_ID: entity_id (resolved from current user or override)
                meta = await self.service.put_asset(
                    user=user,  # IMPORTANT: Still use the service's KeycloakUser for permissions/auth
                    scope="users",
                    entity_id=entity_id,
                    key=(key if key is not None else file.filename or "asset"),
                    stream=file.file,
                    content_type=content_type_override or (file.content_type or "application/octet-stream"),
                    file_name=file.filename or (key or "asset"),
                )
                return meta
            finally:
                try:
                    await file.close()
                except Exception:
                    logger.warning("Failed to close uploaded file", exc_info=True)
                    pass

        # --- USER LIST (Modified) ---
        @router.get(
            "/user-assets",
            tags=["User Assets"],
            summary="List user's personal assets/results",
            response_model=AssetListResponse,
        )
        async def list_user_assets(
            user: KeycloakUser = Depends(get_current_user),
            # NEW: Explicit user ID for the actual asset owner
            user_id_override: Optional[str] = Header(None, alias="X-Asset-User-ID", description="[AGENT USE ONLY] Explicit user ID of the asset owner (Header)"),
        ) -> AssetListResponse:
            entity_id = _get_entity_id(user, user_id_override)

            # SCOPE: 'users', ENTITY_ID: entity_id (resolved from current user or override)
            return await self.service.list_assets(user=user, scope="users", entity_id=entity_id)

        # --- USER STREAM / DOWNLOAD (Modified) ---
        @router.get(
            "/user-assets/{key}",
            tags=["User Assets"],
            summary="Stream or download a user asset (supports Range)",
            # ... (responses remain the same)
        )
        async def get_user_asset(
            key: str,
            user: KeycloakUser = Depends(get_current_user),
            range_header: Optional[str] = Header(None, alias="Range"),
            # NEW: Explicit user ID for the actual asset owner
            user_id_override: Optional[str] = Header(None, alias="X-Asset-User-ID", description="[AGENT USE ONLY] Explicit user ID of the asset owner (Header)"),
        ):
            entity_id = _get_entity_id(user, user_id_override)

            # Calls the generic streaming handler
            return await self._handle_stream(user, "users", entity_id, key, range_header)

        # --- USER DELETE ---
        @router.delete(
            "/user-assets/{key}",
            tags=["User Assets"],
            summary="Delete a user's asset/result",
            response_model=dict,
        )
        async def delete_user_asset(
            key: str,
            user: KeycloakUser = Depends(get_current_user),
            # NEW: Explicit user ID for the actual asset owner
            user_id_override: Optional[str] = Header(None, alias="X-Asset-User-ID", description="[AGENT USE ONLY] Explicit user ID of the asset owner (Header)"),
        ):
            entity_id = _get_entity_id(user, user_id_override)

            # SCOPE: 'users', ENTITY_ID: entity_id (resolved from current user or override)
            await self.service.delete_asset(user=user, scope="users", entity_id=entity_id, key=key)
            return {"ok": True, "key": key}

    # ----------------------------------------------------------------------
    # 3. HELPER METHOD: Unified Streaming Logic
    # ----------------------------------------------------------------------

    async def _handle_stream(
        self,
        user: KeycloakUser,
        scope: ScopeType,
        entity_id: str,
        key: str,
        range_header: Optional[str],
    ):
        """
        Generic method to handle the complex Range Request streaming logic,
        used by both AGENT and USER GET endpoints.
        """
        try:
            # Stat the asset to get size and content_type
            meta = await self.service.stat_asset(user=user, scope=scope, entity_id=entity_id, key=key)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Asset not found")

        total_size = meta.size
        content_type = meta.content_type or "application/octet-stream"
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Disposition": f'inline; filename="{meta.file_name}"',
        }

        rng = parse_range_header(range_header)

        # --- Full Stream (200) ---
        if rng is None:
            stream = await self.service.stream_asset(user=user, scope=scope, entity_id=entity_id, key=key)

            def gen(chunk: int = 8192):
                while True:
                    buf = stream.read(chunk)
                    if not buf:
                        break
                    yield buf

            headers["Content-Length"] = str(total_size)
            return StreamingResponse(
                gen(),
                media_type=content_type,
                headers=headers,
                background=BackgroundTask(_close_stream, stream),
                status_code=200,
            )

        # --- Partial Stream (206) ---
        start, end = rng
        if start is None and end is not None:
            if end <= 0:
                headers["Content-Range"] = f"bytes */{total_size}"
                raise HTTPException(status_code=416, detail="Range Not Satisfiable")
            start = max(total_size - end, 0)
            end = total_size - 1
        else:
            if start is None or start < 0 or start >= total_size:
                headers["Content-Range"] = f"bytes */{total_size}"
                raise HTTPException(status_code=416, detail="Range Not Satisfiable")
            end = total_size - 1 if end is None else min(end, total_size - 1)
            if end < start:
                headers["Content-Range"] = f"bytes */{total_size}"
                raise HTTPException(status_code=416, detail="Range Not Satisfiable")

        length = end - start + 1
        stream = await self.service.stream_asset(user=user, scope=scope, entity_id=entity_id, key=key, start=start, length=length)

        def gen206(chunk: int = 8192):
            remaining = length
            while remaining > 0:
                buf = stream.read(min(chunk, remaining))
                if not buf:
                    break
                remaining -= len(buf)
                yield buf

        headers["Content-Range"] = f"bytes {start}-{end}/{total_size}"
        # Omitting Content-Length for 206 responses is often safer for proxies
        return StreamingResponse(
            gen206(),
            media_type=content_type,
            headers=headers,
            background=BackgroundTask(_close_stream, stream),
            status_code=206,
        )
