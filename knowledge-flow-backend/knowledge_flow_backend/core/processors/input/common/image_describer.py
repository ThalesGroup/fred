# app/core/processors/input/common/vision_image_describer.py
# Copyright Thales 2025
# SPDX-License-Identifier: Apache-2.0

import logging
from typing import Any, Dict, List, Optional, Union

from fred_core import get_model
from fred_core.common import ModelConfiguration
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from knowledge_flow_backend.core.processors.input.common.base_image_describer import BaseImageDescriber

logger = logging.getLogger(__name__)

VISION_DESCRIBE_PROMPT_V1 = """
Describe the image.
Start with this sentence: "There is an image showing".
First, summarize the main content.
Then, add precise details—structure, relationships, and any relevant context you can infer.
If the image is a schema or diagram, list components and explain their relationships.
If the image is a chart or graph, name the axes (if visible), units, and summarize key trends and notable values.
If the image is a table, summarize what it contains (headers, key rows/columns, totals) rather than reproducing every cell.
If the image is a screenshot, describe the interface elements that matter (titles, menus, dialogs).
If the image is a photograph, describe scene, objects, and people, including notable attributes.
If the image is a logo or icon, describe its design and any visible text.

Constraints:
- Output plain text only (no markdown, code fences, or links).
- Do not include image URLs or base64.
- If unsure, say what is uncertain rather than hallucinating specifics.
""".strip()

PPTX_MEDIUM_VISION_DESCRIBE_PROMPT_V1 = """
You are generating a short visual enrichment for a slide that has already been processed by native extraction.

Your goal is not to describe the whole slide like an image caption.
Your goal is to add only visually useful information that is likely missing from the native markdown.

Priorities:
- Recover important visible text embedded in images, screenshots, charts, diagrams, or visual blocks.
- Summarize the useful visual structure only when it adds meaning.
- Describe diagrams, charts, maps, screenshots, or tables only to the extent needed to understand their content.
- Keep only information that improves markdown reading or retrieval.

Do not include:
- decorative details
- colors, background, styling, branding, or general visual impression
- slide numbers
- repetition of content already likely extracted natively
- speculative interpretations when the structure is ambiguous

If the slide contains:
- a diagram: name the main components and their relationships
- a chart: summarize what is being compared and the key visible trend
- a screenshot or web page: extract the important visible text and the purpose of the screen
- a table: summarize the main headers and key takeaway, not every cell
- logos or portraits only: ignore them unless they add essential meaning

Output constraints:
- Output plain text only
- Be concise
- Use at most 4 short paragraphs
- Prefer factual statements
- If uncertain, say so briefly instead of inventing details
""".strip()


def build_image_describer(
    vision_cfg: Optional[ModelConfiguration],
    system_prompt: str | None = None,
) -> Optional[BaseImageDescriber]:
    """
    Fred rationale:
    - Centralizes the decision: if 'vision' is configured, we return a describer.
    - Keeps PdfMarkdownProcessor free of provider logic.
    """
    if not vision_cfg:
        logger.info("No vision configuration found; images won't be described.")
        return None
    model = get_model(vision_cfg)  # one constructor for all providers
    return VisionImageDescriber(model, system_prompt or VISION_DESCRIBE_PROMPT_V1, provider=vision_cfg.provider)


def _stringify_content(content: Union[str, List[Any], Dict[str, Any]]) -> str:
    """
    Fred rationale:
    - Some providers return a list of content parts (e.g., [{'type':'text','text':'...'}]).
    - Normalize to plain text so callers always get a string.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for p in content:
            if isinstance(p, dict):
                # common LC/OpenAI part shape
                t = p.get("text")
                if isinstance(t, str):
                    parts.append(t)
            elif isinstance(p, str):
                parts.append(p)
        return " ".join(parts)
    if isinstance(content, dict):
        # last resort: try typical key
        t = content.get("text")
        return t if isinstance(t, str) else ""
    return ""


class VisionImageDescriber(BaseImageDescriber):
    """
    Fred rationale:
    - Provider-agnostic: any LangChain chat model that supports images (OpenAI 4o/mini, Azure 4o, Ollama vision).
    - Prompt lives here; transport/auth stays in fred_core.model_hub.
    """

    def __init__(self, model: BaseChatModel, system_prompt: str, provider: str | None = None, max_tokens: int = 512):
        # Bind per-call kwargs like max_tokens via LC's .bind()
        self.provider = (provider or "").lower()
        # `max_tokens` via LangChain `.bind(...)` is not accepted by the Ollama chat client
        # used in our current setup. Keep the historical bound behavior for other providers,
        # but skip it for Ollama and rely on provider-native settings (e.g. `num_predict`).
        if self.provider == "ollama":
            self.model = model
        else:
            self.model = model.bind(max_tokens=max_tokens)
        self.system_prompt = system_prompt
        self.max_tokens = max_tokens

    def describe(self, image_base64: str) -> str:
        """
        Fred rationale:
        - Multimodal messages are "text + image_url(data:...)".
        - We stay strict on output (plain text) so callers can inject into Markdown safely.
        """
        try:
            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(
                    content=[
                        {"type": "text", "text": "Please describe this image."},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{image_base64}"},
                        },
                    ]
                ),
            ]
            # NOTE: model kwargs already bound; no 'config' needed here.
            result = self.model.invoke(messages)
            text = _stringify_content(getattr(result, "content", "")).strip()
            return text or "Image description not available."
        except Exception as e:
            logger.warning("Vision description failed: %s", e)
            return "Image description not available."
