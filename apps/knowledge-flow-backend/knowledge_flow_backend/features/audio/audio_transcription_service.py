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

import tempfile
from pathlib import Path
from typing import Optional

from fastapi import UploadFile

from knowledge_flow_backend.core.processors.input.audio_processor.audio_processor import (
    SUPPORTED_CONTENT_TYPES,
    SUPPORTED_EXTENSIONS,
    AudioProcessor,
)

MAX_AUDIO_TRANSCRIPTION_BYTES = 25 * 1024 * 1024


class AudioTranscriptionService:
    """
    Small synchronous transcription helper for chat dictation uploads.

    Why this exists:
    - chat dictation needs Whisper transcription without creating documents or
      triggering the ingestion workflow

    How to use:
    - pass the uploaded `UploadFile` plus an optional language hint
    - the service validates the payload, writes one temp file, runs Whisper, and
      returns plain text
    """

    def __init__(self, processor: Optional[AudioProcessor] = None) -> None:
        self._processor = processor or AudioProcessor()

    async def transcribe_upload(self, upload: UploadFile, language: Optional[str] = None) -> str:
        suffix = self._validate_upload(upload)
        temp_path = await self._materialize_upload(upload, suffix)
        try:
            transcript = self._processor.transcribe_file_to_text(temp_path, language=language)
            text = str(transcript["text"]).strip()
            if not text:
                raise ValueError("Transcription returned no text.")
            return text
        finally:
            temp_path.unlink(missing_ok=True)
            await upload.close()

    def _validate_upload(self, upload: UploadFile) -> str:
        filename = Path(upload.filename or "recording").name
        suffix = Path(filename).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
            raise ValueError(f"Unsupported audio format '{suffix or '(none)'}'. Supported: {supported}")

        raw_content_type = (upload.content_type or "").strip().lower()
        content_type = raw_content_type.split(";", 1)[0].strip()
        if content_type and content_type not in SUPPORTED_CONTENT_TYPES:
            raise ValueError(f"Unsupported content type '{raw_content_type}'.")

        return suffix

    async def _materialize_upload(self, upload: UploadFile, suffix: str) -> Path:
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        total_bytes = 0
        try:
            with temp_file:
                while True:
                    chunk = await upload.read(1024 * 1024)
                    if not chunk:
                        break
                    total_bytes += len(chunk)
                    if total_bytes > MAX_AUDIO_TRANSCRIPTION_BYTES:
                        raise ValueError(
                            f"Audio file exceeds {MAX_AUDIO_TRANSCRIPTION_BYTES} bytes; keep recordings short for dictation.",
                        )
                    temp_file.write(chunk)
        except Exception:
            Path(temp_file.name).unlink(missing_ok=True)
            raise

        if total_bytes == 0:
            Path(temp_file.name).unlink(missing_ok=True)
            raise ValueError("Uploaded audio file is empty.")

        return Path(temp_file.name)
