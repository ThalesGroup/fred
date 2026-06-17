# Copyright Thales 2026
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
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fred_core import Action, KeycloakUser, Resource, authorize_or_raise, get_current_user
from pydantic import BaseModel, Field

from knowledge_flow_backend.features.audio.audio_transcription_service import AudioTranscriptionService

logger = logging.getLogger(__name__)


class AudioTranscriptionResponse(BaseModel):
    text: str = Field(..., description="Plain-text transcript for the uploaded audio clip.")


class AudioTranscriptionController:
    def __init__(self, router: APIRouter) -> None:
        self.service = AudioTranscriptionService()
        self._register_routes(router)

    def _register_routes(self, router: APIRouter) -> None:
        @router.post(
            "/audio/transcriptions",
            tags=["Audio"],
            summary="Transcribe an uploaded audio clip for chat dictation",
            response_model=AudioTranscriptionResponse,
        )
        async def transcribe_audio(
            file: UploadFile = File(..., description="Audio or video clip to transcribe"),
            language: Optional[str] = Form(None, description="Optional language hint for Whisper"),
            user: KeycloakUser = Depends(get_current_user),
        ) -> AudioTranscriptionResponse:
            authorize_or_raise(user, Action.CREATE, Resource.FILES)
            try:
                text = await self.service.transcribe_upload(file, language=language)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except HTTPException:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.exception("Audio transcription failed")
                raise HTTPException(status_code=500, detail="Audio transcription failed.") from exc
            return AudioTranscriptionResponse(text=text)
