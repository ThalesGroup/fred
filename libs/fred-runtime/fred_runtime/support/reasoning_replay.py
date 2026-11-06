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
Speak Mistral's Chat Completions payload through the OpenAI-compatible client.

Mistral's docs ask for the assistant's reasoning chunks back in the history.
`langchain_openai` drops `thinking` blocks from the payload, so a Mistral model
served through the OpenAI-compatible client gets them re-inserted here. It also
renames the token ceiling and asks for usage, which Mistral's request does not list.
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
    """`ChatOpenAI` with Mistral's ceiling and streaming, and its reasoning chunks."""

    def _get_request_payload(
        self,
        input_: LanguageModelInput,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> dict:
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        wire = payload.get("messages")
        # Responses API: leave it as built.
        if not isinstance(wire, list):
            return payload
        if "max_completion_tokens" in payload:
            payload["max_tokens"] = payload.pop("max_completion_tokens")
        # Usage comes unasked on the last chunk.
        payload.pop("stream_options", None)
        messages = self._convert_input(input_).to_messages()
        # An unexpected payload shape: leave its messages as built.
        if len(wire) != len(messages):
            return payload
        for source, entry in zip(messages, wire, strict=True):
            if isinstance(source, AIMessage) and isinstance(source.content, list):
                content = native_reasoning_content(source.content)
                if isinstance(content, list) and isinstance(entry, dict):
                    entry["content"] = content
        return payload


def with_mistral_reasoning_replay(model: ChatOpenAI) -> ChatOpenAI:
    """Give a `ChatOpenAI` on a connection of the Mistral dialect its replay payload."""

    # Same fields and clients; only the payload serialisation differs.
    object.__setattr__(model, "__class__", MistralReasoningReplayChatOpenAI)
    return model


def replays_native_reasoning(model: object) -> bool:
    """Return whether the history should keep reasoning blocks for this model."""

    return isinstance(model, MistralReasoningReplayChatOpenAI)
