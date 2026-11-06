# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Bounded vision calls using Knowledge Flow's configured model."""

from __future__ import annotations

import asyncio
import base64
import io
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fred_core import get_current_user_without_gcu, get_principal_context, is_service_agent
from fred_core.security.structure import LOCAL_DEV_CLIENT_ID, PrincipalContext
from langchain_core.messages import HumanMessage
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.core.processors.input.common.image_describer import (
    _stringify_content,
)

_MAX_IMAGE_BYTES = 4 * 1024 * 1024
_MAX_PROMPT_CHARS = 16_000
_MAX_PIXELS = 12_000_000
_TIMEOUT_SECONDS = 45
_CAPACITY_WAIT_SECONDS = 2


class VisionAvailability(BaseModel):
    available: bool


class VisionAnswer(BaseModel):
    text: str


class VisionController:
    def __init__(self, router: APIRouter, context: ApplicationContext) -> None:
        self._context = context
        self._model = None
        self._model_lock = asyncio.Lock()
        self._slots = asyncio.Semaphore(4)

        @router.get("/vision/availability", response_model=VisionAvailability, tags=["Vision"])
        async def availability(
            _user=Depends(get_current_user_without_gcu),
        ) -> VisionAvailability:
            return VisionAvailability(available=context.configuration.vision_model is not None)

        @router.post("/internal/vision/describe", response_model=VisionAnswer, tags=["Vision"])
        async def describe(
            image: Annotated[UploadFile, File()],
            prompt: Annotated[str, Form()],
            principals: PrincipalContext = Depends(get_principal_context),
        ) -> VisionAnswer:
            self._require_worker(principals)
            if not context.configuration.vision_model:
                raise HTTPException(status_code=503, detail="vision_model_unavailable")
            if not prompt or len(prompt) > _MAX_PROMPT_CHARS:
                raise HTTPException(status_code=422, detail="vision_prompt_invalid")
            data = await image.read(_MAX_IMAGE_BYTES + 1)
            if len(data) > _MAX_IMAGE_BYTES:
                raise HTTPException(status_code=413, detail="vision_image_too_large")
            media_type = self._image_type(data)
            try:
                await asyncio.wait_for(self._slots.acquire(), timeout=_CAPACITY_WAIT_SECONDS)
            except TimeoutError as exc:
                raise HTTPException(status_code=429, detail="vision_capacity_exceeded") from exc
            try:
                try:
                    async with asyncio.timeout(_TIMEOUT_SECONDS):
                        model = await self._get_model()
                        answer = await model.ainvoke(
                            [
                                HumanMessage(
                                    content=[
                                        {"type": "text", "text": prompt},
                                        {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{base64.b64encode(data).decode('ascii')}"}},
                                    ]
                                )
                            ]
                        )
                except TimeoutError as exc:
                    raise HTTPException(status_code=504, detail="vision_timeout") from exc
                except Exception as exc:
                    raise HTTPException(status_code=503, detail="vision_model_error") from exc
            finally:
                self._slots.release()
            text = _stringify_content(getattr(answer, "content", "")).strip()
            if not text or len(text) > 32_000:
                raise HTTPException(status_code=502, detail="vision_answer_invalid")
            return VisionAnswer(text=text)

    def _require_worker(self, principals: PrincipalContext) -> None:
        caller = principals.caller
        security = self._context.configuration.security
        if security.m2m.enabled:
            if not is_service_agent(caller) or caller.client_id != self._context.configuration.vision_worker_client_id:
                raise HTTPException(status_code=403, detail="vision_worker_required")
        elif caller.client_id != LOCAL_DEV_CLIENT_ID:
            raise HTTPException(status_code=403, detail="vision_worker_required")

    async def _get_model(self):
        if self._model is None:
            async with self._model_lock:
                if self._model is None:
                    self._model = self._context.get_vision_model()
        return self._model

    @staticmethod
    def _image_type(data: bytes) -> str:
        try:
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in ("PNG", "JPEG") or image.width * image.height > _MAX_PIXELS:
                    raise ValueError("Unsupported image")
                image.verify()
                return "image/png" if image.format == "PNG" else "image/jpeg"
        except (UnidentifiedImageError, Image.DecompressionBombError, ValueError, OSError) as exc:
            raise HTTPException(status_code=422, detail="vision_image_invalid") from exc
