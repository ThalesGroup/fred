# Copyright Thales 2025
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

import logging
from typing import Any, Dict, List, Optional, Union

from fred_core import get_model
from fred_core.common import ModelConfiguration
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from knowledge_flow_backend.core.processors.input.common.base_image_ocr import BaseImageOcr

logger = logging.getLogger(__name__)

OCR_TRANSCRIBE_PROMPT_V1 = """
Transcribe all visible text from the image.
Preserve the reading order as faithfully as possible.
Do not summarize, translate, explain, or add commentary.
Return plain text only.
If the image contains no readable text, return an empty string.
""".strip()


def build_image_ocr(
    ocr_cfg: Optional[ModelConfiguration],
    system_prompt: str | None = None,
) -> Optional[BaseImageOcr]:
    """
    Why:
        Centralize OCR-model construction so PDF processors do not contain
        provider-specific model setup logic.

    How:
        Pass the optional `ocr_model` configuration from runtime settings.
        Returns `None` when OCR is not configured, otherwise a provider-agnostic
        OCR adapter.

    Example:
        `ocr = build_image_ocr(config.ocr_model)`
    """
    if not ocr_cfg:
        logger.info("No OCR model configuration found; remote OCR is disabled.")
        return None
    model = get_model(ocr_cfg)
    return RemoteImageOcr(model=model, system_prompt=system_prompt or OCR_TRANSCRIBE_PROMPT_V1, provider=ocr_cfg.provider)


def _stringify_content(content: Union[str, List[Any], Dict[str, Any]]) -> str:
    """
    Why:
        Normalize multimodal provider responses into one plain-text OCR string.

    How:
        Pass the `result.content` payload returned by the chat model.
        The helper extracts text parts from common string/list/dict shapes.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for part in content:
            if isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(part, str):
                parts.append(part)
        return " ".join(parts)
    if isinstance(content, dict):
        text = content.get("text")
        return text if isinstance(text, str) else ""
    return ""


class RemoteImageOcr(BaseImageOcr):
    """
    Why:
        Reuse the shared Fred model factory for OCR-capable remote multimodal
        models without adding provider-specific branches to ingestion code.

    How:
        Construct the adapter with a chat model returned by `fred_core.get_model`
        and call `extract_text(base64_png)` for each rendered page image.
    """

    def __init__(self, model: BaseChatModel, system_prompt: str, provider: str | None = None, max_tokens: int = 2048):
        self.provider = (provider or "").lower()
        self.model = model
        self.system_prompt = system_prompt
        self.max_tokens = max_tokens

    def extract_text(self, image_base64: str) -> str:
        """
        Why:
            Keep OCR output safe for markdown assembly by forcing plain-text
            transcription instead of general image description.

        How:
            Pass the base64 PNG/JPEG payload of the page image. The method sends
            a strict multimodal transcription prompt and returns normalized text.
        """
        try:
            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(
                    content=[
                        {"type": "text", "text": "Transcribe the visible text in reading order."},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{image_base64}"},
                        },
                    ]
                ),
            ]
            result = self.model.invoke(messages)
            return _stringify_content(getattr(result, "content", "")).strip()
        except Exception as exc:
            logger.warning("Remote OCR failed: %s", exc)
            return ""
