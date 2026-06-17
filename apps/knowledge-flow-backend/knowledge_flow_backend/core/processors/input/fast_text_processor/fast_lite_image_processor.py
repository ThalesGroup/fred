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

import base64
import logging
import mimetypes
from pathlib import Path

from knowledge_flow_backend.application_context import get_configuration
from knowledge_flow_backend.core.processors.input.common.image_describer import build_image_describer
from knowledge_flow_backend.core.processors.input.fast_text_processor.base_fast_text_processor import (
    BaseFastTextProcessor,
    FastTextOptions,
    FastTextResult,
)
from knowledge_flow_backend.core.processors.input.image_processor.image_processor import SUPPORTED_IMAGE_EXTENSIONS

logger = logging.getLogger(__name__)


class FastLiteImageProcessor(BaseFastTextProcessor):
    """
    Fast-path image processor for chat attachments.

    It prefers a short vision description when a vision model is configured and
    otherwise falls back to a lightweight textual summary based on filename and
    basic metadata so the image remains retrievable in session-scoped RAG.
    """

    def __init__(self) -> None:
        self.image_describer = None
        self._warned_missing_vision_model = False

    def _resolve_image_describer(self):
        if self.image_describer is not None:
            return self.image_describer
        vision_model = get_configuration().vision_model
        if not vision_model:
            if not self._warned_missing_vision_model:
                logger.info("[FAST TEXT][IMAGE] Vision model missing; using filename fallback only.")
                self._warned_missing_vision_model = True
            return None
        self.image_describer = build_image_describer(vision_model)
        return self.image_describer

    @staticmethod
    def _fallback_text(file_path: Path) -> str:
        stem = file_path.stem.replace("_", " ").replace("-", " ").strip() or file_path.stem
        ext = file_path.suffix.lower().lstrip(".") or "unknown"
        return f"Image attachment: {file_path.name}\nTitle: {stem}\nFormat: {ext}\nThis image was attached to the conversation and is available for session-scoped retrieval."

    @staticmethod
    def _to_data_url(file_path: Path) -> str:
        mime = mimetypes.guess_type(file_path.name)[0] or "image/png"
        encoded = base64.b64encode(file_path.read_bytes()).decode("utf-8")
        return f"data:{mime};base64,{encoded}"

    def extract(self, file_path: Path, options: FastTextOptions | None = None) -> FastTextResult:
        _ = options or FastTextOptions()
        if not file_path.exists():
            raise ValueError(f"Image file does not exist: {file_path}")
        if file_path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
            raise ValueError(f"Unsupported image format for fast ingest: {file_path.suffix}")
        if file_path.stat().st_size == 0:
            raise ValueError(f"Image file is empty: {file_path}")

        text = self._fallback_text(file_path)
        describer = self._resolve_image_describer()
        if describer is not None:
            description = describer.describe(self._to_data_url(file_path)).strip()
            if description and description != "Image description not available.":
                text = f"{text}\n\nVision summary:\n{description}"

        return FastTextResult(
            document_name=file_path.name,
            page_count=1,
            total_chars=len(text),
            truncated=False,
            text=text,
            extras={"file_type": "image", "extension": file_path.suffix.lower()},
        )
