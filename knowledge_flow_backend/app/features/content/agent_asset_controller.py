# app/features/assets/agent_asset_controller.py
# Copyright Thales 2025
#
# Purpose (Fred):
# - Minimal CRUD over per-user agent assets (e.g., PPTX templates).
# - Streaming (incl. Range) built-in; typed responses only.
# - Storage layout: agents/{agent}/{user_id}/{key}

import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from fred_core import KeycloakUser, get_current_user
from starlette.background import BackgroundTask

from app.features.content.agent_asset_service import AgentAssetListResponse, AgentAssetMeta, AgentAssetService
from app.features.content.content_controller import parse_range_header  # reuse helper

logger = logging.getLogger(__name__)


def _close_stream(s) -> None:
    try:
        s.close()
    except Exception:
        logger.warning("Failed to close stream", exc_info=True)
        pass


class AgentAssetController:
    """
    Agent-friendly CRUD for per-user assets.

    Endpoints
    ---------
    - POST   /agent-assets/{agent}/upload
    - GET    /agent-assets/{agent}
    - GET    /agent-assets/{agent}/{key}   (supports Range)
    - DELETE /agent-assets/{agent}/{key}
    """

    def __init__(self, router: APIRouter):
        self.service = AgentAssetService()
        self._register_routes(router)

    def _register_routes(self, router: APIRouter):
        @router.post(
            "/agent-assets/{agent}/upload",
            tags=["Agent Assets"],
            summary="Upload or replace a per-user asset for an agent",
            response_model=AgentAssetMeta,
        )
        async def upload_asset(
            agent: str,
            user: KeycloakUser = Depends(get_current_user),
            file: UploadFile = File(..., description="Binary payload (e.g., .pptx)"),
            key: Optional[str] = Form(None, description="Logical asset key (defaults to uploaded filename)"),
            content_type_override: Optional[str] = Form(None, description="Force a content-type if needed"),
        ) -> AgentAssetMeta:
            if not (key or file.filename):
                raise HTTPException(status_code=400, detail="Missing asset key or filename")
            try:
                meta = await self.service.put_asset(
                    user=user,
                    agent=agent,
                    key=(key if key is not None else file.filename or "asset"),  # normalized in service
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

        @router.get(
            "/agent-assets/{agent}",
            tags=["Agent Assets"],
            summary="List user's assets for an agent",
            response_model=AgentAssetListResponse,
        )
        async def list_assets(agent: str, user: KeycloakUser = Depends(get_current_user)) -> AgentAssetListResponse:
            return await self.service.list_assets(user=user, agent=agent)

        @router.get(
            "/agent-assets/{agent}/{key}",
            tags=["Agent Assets"],
            summary="Stream or download an asset (supports Range)",
            response_class=StreamingResponse,
            responses={
                200: {"description": "Full stream"},
                206: {"description": "Partial stream (Range)"},
                404: {"description": "Not found"},
                416: {"description": "Range Not Satisfiable"},
            },
        )
        async def get_asset(
            agent: str,
            key: str,
            user: KeycloakUser = Depends(get_current_user),
            range_header: Optional[str] = Header(None, alias="Range"),
        ):
            try:
                meta = await self.service.stat_asset(user=user, agent=agent, key=key)
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail="Asset not found")

            total_size = meta.size
            content_type = meta.content_type or "application/octet-stream"
            headers = {
                "Accept-Ranges": "bytes",
                "Content-Disposition": f'inline; filename="{meta.file_name}"',
            }

            rng = parse_range_header(range_header)
            if rng is None:
                stream = await self.service.stream_asset(user=user, agent=agent, key=key)

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

            # Range requested
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
            stream = await self.service.stream_asset(user=user, agent=agent, key=key, start=start, length=length)

            def gen206(chunk: int = 8192):
                remaining = length
                while remaining > 0:
                    buf = stream.read(min(chunk, remaining))
                    if not buf:
                        break
                    remaining -= len(buf)
                    yield buf

            headers["Content-Range"] = f"bytes {start}-{end}/{total_size}"
            # Intentionally omit Content-Length for 206 (safer on client aborts)
            return StreamingResponse(
                gen206(),
                media_type=content_type,
                headers=headers,
                background=BackgroundTask(_close_stream, stream),
                status_code=206,
            )

        @router.delete(
            "/agent-assets/{agent}/{key}",
            tags=["Agent Assets"],
            summary="Delete a user's asset",
            response_model=dict,  # tiny response; avoid another model type
        )
        async def delete_asset(agent: str, key: str, user: KeycloakUser = Depends(get_current_user)):
            await self.service.delete_asset(user=user, agent=agent, key=key)
            return {"ok": True, "key": key}
