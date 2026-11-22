# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Bounded worker text completions using Knowledge Flow's configured model."""

from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fred_core import AssertedUser, KeycloakUser, get_current_user_or_service, get_principal_context, is_service_agent
from fred_core.security.structure import LOCAL_DEV_CLIENT_ID, PrincipalContext
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.core.processors.input.common.image_describer import _stringify_content

logger = logging.getLogger(__name__)

_MAX_SYSTEM_CHARS = 16_000
_MAX_USER_CHARS = 64_000
_MAX_ANSWER_CHARS = 32_000
_TIMEOUT_SECONDS = 60
_CAPACITY_WAIT_SECONDS = 2


class TextCompletionRequest(BaseModel):
    system: str
    user: str


class TextCompletionAnswer(BaseModel):
    text: str


async def _worker_principal_context(
    request: Request,
    subject: KeycloakUser | AssertedUser = Depends(get_current_user_or_service),
) -> PrincipalContext:
    return await get_principal_context(request, subject)


class TextController:
    def __init__(self, router: APIRouter, context: ApplicationContext) -> None:
        self._context = context
        self._model = None
        self._model_lock = asyncio.Lock()
        self._slots = asyncio.Semaphore(4)

        @router.post("/internal/text/complete", response_model=TextCompletionAnswer, tags=["Text"])
        async def complete(
            body: TextCompletionRequest,
            principals: PrincipalContext = Depends(_worker_principal_context),
        ) -> TextCompletionAnswer:
            self._require_worker(principals)
            if not body.system or len(body.system) > _MAX_SYSTEM_CHARS or not body.user or len(body.user) > _MAX_USER_CHARS:
                raise HTTPException(status_code=422, detail="text_input_invalid")
            try:
                await asyncio.wait_for(self._slots.acquire(), timeout=_CAPACITY_WAIT_SECONDS)
            except TimeoutError as exc:
                raise HTTPException(status_code=429, detail="text_capacity_exceeded") from exc
            started = time.monotonic()
            try:
                try:
                    async with asyncio.timeout(_TIMEOUT_SECONDS):
                        model = await self._get_model()
                        answer = await model.ainvoke([SystemMessage(content=body.system), HumanMessage(content=body.user)])
                except TimeoutError as exc:
                    raise HTTPException(status_code=504, detail="text_timeout") from exc
                except Exception as exc:
                    logger.warning("Internal text completion failed", exc_info=True)
                    raise HTTPException(status_code=503, detail="text_model_error") from exc
            finally:
                self._slots.release()
            text = _stringify_content(getattr(answer, "content", "")).strip()
            if not text or len(text) > _MAX_ANSWER_CHARS:
                raise HTTPException(status_code=502, detail="text_answer_invalid")
            logger.info("Internal text completion succeeded in %.1fs", time.monotonic() - started)
            return TextCompletionAnswer(text=text)

    def _require_worker(self, principals: PrincipalContext) -> None:
        caller = principals.caller
        security = self._context.configuration.security
        if security.m2m.enabled:
            if not is_service_agent(caller) or caller.client_id != self._context.configuration.preparation_worker_client_id:
                raise HTTPException(status_code=403, detail="preparation_worker_required")
        elif caller.client_id != LOCAL_DEV_CLIENT_ID:
            raise HTTPException(status_code=403, detail="preparation_worker_required")

    async def _get_model(self):
        if self._model is None:
            async with self._model_lock:
                if self._model is None:
                    self._model = self._context.get_utility_model()
        return self._model
