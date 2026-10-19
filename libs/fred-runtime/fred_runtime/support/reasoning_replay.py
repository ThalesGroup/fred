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

"""
Replay Mistral reasoning to Mistral in its own `thinking` chunk shape.

Mistral's docs ask for the assistant's reasoning chunks back in the history.
`langchain_openai` drops `thinking` blocks from the payload, so a Mistral model
served through the OpenAI-compatible client gets them re-inserted here.
Full rationale: `RUNTIME-EXECUTION-CONTRACT.md` §8.117.
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI

from .thinking import native_reasoning_content


def is_mistral_model_name(model_name: str | None) -> bool:
    """Return whether one configured/effective model name is Mistral."""

    if model_name is None:
        return False
    normalized = model_name.lower()
    return normalized.startswith("mistral") or "/mistral" in normalized


class MistralReasoningReplayChatOpenAI(ChatOpenAI):
    """`ChatOpenAI` that sends assistant reasoning back as Mistral chunks."""

    def _get_request_payload(
        self,
        input_: LanguageModelInput,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> dict:
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        wire = payload.get("messages")
        messages = self._convert_input(input_).to_messages()
        # Responses API or an unexpected payload shape: leave it as built.
        if not isinstance(wire, list) or len(wire) != len(messages):
            return payload
        for source, entry in zip(messages, wire, strict=True):
            if isinstance(source, AIMessage) and isinstance(source.content, list):
                content = native_reasoning_content(source.content)
                if isinstance(content, list) and isinstance(entry, dict):
                    entry["content"] = content
        return payload


def with_mistral_reasoning_replay(model: object) -> object:
    """Give a plain Mistral `ChatOpenAI` the reasoning-replay payload; others pass."""

    if type(model) is not ChatOpenAI or not is_mistral_model_name(model.model_name):
        return model
    # Same fields and clients; only the payload serialisation differs.
    object.__setattr__(model, "__class__", MistralReasoningReplayChatOpenAI)
    return model


def replays_native_reasoning(model: object) -> bool:
    """Return whether the history should keep reasoning blocks for this model."""

    return isinstance(model, MistralReasoningReplayChatOpenAI)
