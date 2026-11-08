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
import io
import logging
from pathlib import Path
from typing import cast

from PIL import Image, ImageOps

from knowledge_flow_backend.application_context import get_configuration
from knowledge_flow_backend.core.processors.input.common.image_describer import (
    IMAGE_DESCRIPTION_UNAVAILABLE,
    VISION_ATTACHMENT_PROMPT_V1,
    build_image_describer,
)
from knowledge_flow_backend.core.processors.input.fast_text_processor.base_fast_text_processor import (
    BaseFastTextProcessor,
    FastTextOptions,
    FastTextResult,
)
from knowledge_flow_backend.core.processors.input.image_processor.image_processor import SUPPORTED_IMAGE_EXTENSIONS

logger = logging.getLogger(__name__)

# Read by the chat agent next to the description: silence must not become absence.
DESCRIPTION_MAX_CHARS = 6000
DESCRIPTION_TRUNCATED = "[description truncated]"
NO_DESCRIPTION = "No visual description is available for this image: its content is unknown."
# Long edge sent to the vision model: providers downscale past this anyway.
VISION_MAX_EDGE_PX = 1568
# Decoded pixels after the JPEG draft: above this the bitmap alone costs hundreds of MB.
VISION_MAX_PIXELS = 50_000_000
_VISION_FORMATS = ["PNG", "JPEG", "GIF", "WEBP", "BMP", "ICO"]
DESCRIPTION_LIMITS = "Limits: this description was written once, without knowing future questions. It is not exhaustive: anything it does not mention was not checked and is unknown, not absent."


class FastLiteImageProcessor(BaseFastTextProcessor):
    """
    Fast-path image processor for chat attachments.

    It prefers an exhaustive vision description when a vision model is configured and
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
        self.image_describer = build_image_describer(vision_model, VISION_ATTACHMENT_PROMPT_V1)
        return self.image_describer

    @staticmethod
    def _fallback_text(file_path: Path) -> str:
        stem = file_path.stem.replace("_", " ").replace("-", " ").strip() or file_path.stem
        ext = file_path.suffix.lower().lstrip(".") or "unknown"
        return f"Image attachment: {file_path.name}\nTitle: {stem}\nFormat: {ext}\nThis image was attached to the conversation and is available for session-scoped retrieval."

    @staticmethod
    def _eight_bit(image: Image.Image) -> Image.Image:
        # convert("RGB") clips 16-bit and float samples at 255: the image would turn white.
        if image.mode.startswith("I;16"):
            return image.point(lambda value: value / 256).convert("L")
        if image.mode in ("I", "F"):
            low, high = cast(tuple[float, float], image.getextrema())
            scale = 255 / (high - low) if high > low else 0
            offset = -low * scale
            return image.point(lambda value: value * scale + offset).convert("L")
        return image

    @staticmethod
    def _vision_png(file_path: Path) -> bytes | None:
        """The bounded PNG a vision model sees, or None when the image cannot be prepared."""
        try:
            with Image.open(file_path, formats=_VISION_FORMATS) as opened:
                opened.draft(None, (VISION_MAX_EDGE_PX, VISION_MAX_EDGE_PX))
                if opened.width * opened.height > VISION_MAX_PIXELS:
                    logger.warning("[FAST TEXT][IMAGE] %s not described: %dx%d px is above the vision limit", file_path.name, opened.width, opened.height)
                    return None
                # Shrink before any copy; palette and 1-bit images would resize nearest-neighbour.
                image = opened.convert("RGBA" if opened.has_transparency_data else "RGB") if opened.mode in ("P", "1") else opened
                # 2 px of slack: an SVG render (1569 px) is sent as is rather than resampled.
                if max(image.size) > VISION_MAX_EDGE_PX + 2:
                    image.thumbnail((VISION_MAX_EDGE_PX, VISION_MAX_EDGE_PX), Image.Resampling.LANCZOS)
                image = ImageOps.exif_transpose(FastLiteImageProcessor._eight_bit(image))
                image = image.convert("RGBA" if image.has_transparency_data else "RGB")
                buffer = io.BytesIO()
                image.save(buffer, format="PNG", optimize=True)
        except Exception as exc:  # Pillow raises many error types on corrupt or exotic input.
            # Pillow messages can carry the temp path: keep the file name only.
            message = str(exc).replace(str(file_path), file_path.name)[:200]
            logger.warning("[FAST TEXT][IMAGE] %s not described: %s: %s", file_path.name, type(exc).__name__, message)
            return None
        return buffer.getvalue()

    def extract(self, file_path: Path, options: FastTextOptions | None = None) -> FastTextResult:
        _ = options or FastTextOptions()
        if not file_path.exists():
            raise ValueError(f"Image file does not exist: {file_path}")
        if file_path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
            raise ValueError(f"Unsupported image format for fast ingest: {file_path.suffix}")
        if file_path.stat().st_size == 0:
            raise ValueError(f"Image file is empty: {file_path}")

        # Limits come before the model's description: a truncated summary must lose
        # the end of the description, never the limits note.
        text = self._fallback_text(file_path)
        describer = self._resolve_image_describer()
        png = self._vision_png(file_path) if describer is not None else None
        vision_url = f"data:image/png;base64,{base64.b64encode(png).decode('ascii')}" if png else None
        description = describer.describe(vision_url).strip() if describer is not None and vision_url else ""
        if vision_url and description in ("", IMAGE_DESCRIPTION_UNAVAILABLE):
            logger.info("[FAST TEXT][IMAGE] No visual description for %s: the vision model gave none", file_path.name)
        if len(description) > DESCRIPTION_MAX_CHARS:
            description = description[: DESCRIPTION_MAX_CHARS - len(DESCRIPTION_TRUNCATED) - 1] + "\n" + DESCRIPTION_TRUNCATED
        if description and description != IMAGE_DESCRIPTION_UNAVAILABLE:
            text = f"{text}\n\n{DESCRIPTION_LIMITS}\n\nVision summary:\n{description}"
        else:
            text = f"{text}\n\n{NO_DESCRIPTION}"

        return FastTextResult(
            document_name=file_path.name,
            page_count=1,
            total_chars=len(text),
            truncated=False,
            text=text,
            extras={"file_type": "image", "extension": file_path.suffix.lower()},
        )
