# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Bounded text completion for a CP-authorized preparation and organization model."""

from __future__ import annotations

import asyncio
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fred_core.security import oidc
from fred_core.security.delegation import AssertedUser
from fred_core.security.structure import KeycloakUser
from fred_sdk.contracts.weaver import InferenceAdmission
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from knowledge_flow_backend.application_context import ApplicationContext

_TIMEOUT_SECONDS = 60


class TextCompletionRequest(BaseModel):
    preparation_id: UUID
    system: str = Field(min_length=1, max_length=16_000)
    user: str = Field(min_length=1, max_length=64_000)


class TextCompletionAnswer(BaseModel):
    text: str


class TextController:
    def __init__(self, router: APIRouter, context: ApplicationContext) -> None:
        slots = asyncio.Semaphore(4)

        @router.post("/internal/text/complete", response_model=TextCompletionAnswer, tags=["Text"])
        async def complete(body: TextCompletionRequest, request: Request, subject: KeycloakUser | AssertedUser = Depends(oidc.authenticate_request)) -> TextCompletionAnswer:
            # CP binds the received workload token to this exact preparation's pod.
            # Neither this workload nor the request body supplies model authority.
            if isinstance(subject, AssertedUser):
                raise HTTPException(status_code=403, detail="preparation_worker_required")
            base = context.configuration.control_plane_url
            token = request.headers.get("authorization")
            if not base or not token:
                raise HTTPException(status_code=403, detail="preparation_worker_required")
            try:
                reply = await context.get_authorization_client().get(
                    f"{base.rstrip('/')}/capability-preparations/{body.preparation_id}/text-admission",
                    headers={"Authorization": token},
                    auth=None,
                )
                reply.raise_for_status()
                admission = InferenceAdmission.model_validate(reply.json())
            except httpx.HTTPStatusError as exc:
                raise HTTPException(status_code=exc.response.status_code if exc.response.status_code in (401, 403, 404, 409) else 503, detail="preparation_admission_unavailable") from None
            except (httpx.HTTPError, ValueError):
                raise HTTPException(status_code=503, detail="preparation_admission_unavailable") from None
            try:
                await asyncio.wait_for(slots.acquire(), timeout=2)
            except TimeoutError:
                raise HTTPException(status_code=429, detail="text_capacity_exceeded") from None
            try:
                async with asyncio.timeout(_TIMEOUT_SECONDS):
                    model = context.get_document_models().chat(admission)
                    answer = await model.ainvoke([SystemMessage(content=body.system), HumanMessage(content=body.user)])
                text = str(answer.text).strip()
                if not text or len(text) > 32_000:
                    raise HTTPException(status_code=502, detail="text_answer_invalid")
                return TextCompletionAnswer(text=text)
            except TimeoutError:
                raise HTTPException(status_code=504, detail="text_timeout") from None
            finally:
                slots.release()
