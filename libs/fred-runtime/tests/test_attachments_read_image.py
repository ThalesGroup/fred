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
Offline unit tests for the RUNTIME-08 ``attachments.read_image`` invoker and the
portable user-message image injection used by the shared tool loop.

Covers the acceptance criteria:
- source validation (document_media vs conversation_attachment)
- ReBAC / not-found is surfaced as a clean tool error (media fetch raising)
- unsupported multimodal capability returns a clear capability error
- base64 image bytes never appear in the model-visible tool text (only on the
  ``images`` artifact)
- the injection builder turns the image artifact into an OpenAI ``image_url``
  user-message block, scoped to the most-recent tool batch
"""

from __future__ import annotations

import base64
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from fred_sdk.contracts.context import (
    PortableContext,
    PortableEnvironment,
    ToolImageContent,
    ToolInvocationRequest,
    ToolInvocationResult,
)
from fred_sdk.support.builtins import TOOL_REF_ATTACHMENTS_READ_IMAGE

from fred_runtime.integrations.v2_runtime.adapters import (
    FredKnowledgeSearchToolInvoker,
)
from fred_runtime.support.multimodal import build_image_injection_messages

_PNG_BYTES = b"\x89PNG\r\n\x1a\nfake-image-bytes"


class _FakeMediaClient:
    def __init__(self, *, data: bytes = _PNG_BYTES, error: Exception | None = None):
        self._data = data
        self._error = error
        self.calls: list[tuple[str, str]] = []

    async def fetch_media(self, document_uid: str, media_id: str) -> bytes:
        self.calls.append((document_uid, media_id))
        if self._error is not None:
            raise self._error
        return self._data


def _make_invoker(
    *, media: _FakeMediaClient, supports_image: bool = True
) -> FredKnowledgeSearchToolInvoker:
    # Bypass __init__/rebind: those build real Knowledge Flow HTTP clients which
    # need live runtime config. The handler only reads _supports_image_input and
    # _media_client, so a bare instance with those two attributes is sufficient.
    invoker = FredKnowledgeSearchToolInvoker.__new__(FredKnowledgeSearchToolInvoker)
    # setattr: stub the two collaborators the handler reads without tripping the
    # static type of _media_client (a real KfMarkdownMediaClient).
    setattr(invoker, "_supports_image_input", lambda: supports_image)
    setattr(invoker, "_media_client", media)
    return invoker


def _request(payload: dict[str, object]) -> ToolInvocationRequest:
    return ToolInvocationRequest(
        tool_ref=TOOL_REF_ATTACHMENTS_READ_IMAGE,
        payload=payload,
        context=PortableContext(
            request_id="request-1",
            correlation_id="correlation-1",
            actor="user-1",
            tenant="team-1",
            environment=PortableEnvironment.DEV,
        ),
    )


def _block_text(result: ToolInvocationResult) -> str:
    return "\n".join(b.text or "" for b in result.blocks)


def _dict_blocks(message: HumanMessage) -> list[dict[str, Any]]:
    content = message.content
    assert isinstance(content, list)
    return [b for b in content if isinstance(b, dict)]


class TestDocumentMediaHappyPath:
    @pytest.mark.asyncio
    async def test_returns_image_on_the_artifact_not_in_text(self) -> None:
        media = _FakeMediaClient()
        invoker = _make_invoker(media=media)

        result = await invoker._invoke_attachments_read_image(
            _request(
                {
                    "source": "document_media",
                    "document_uid": "doc-1",
                    "file_name": "page-1-image-2.png",
                }
            )
        )

        assert result.is_error is False
        assert media.calls == [("doc-1", "page-1-image-2.png")]
        # Image rides on the artifact, base64-encoded, with the right mime.
        assert len(result.images) == 1
        encoded = base64.b64encode(_PNG_BYTES).decode("ascii")
        assert result.images[0].mime_type == "image/png"
        assert result.images[0].base64_data == encoded
        assert result.images[0].label == "page-1-image-2.png"

    @pytest.mark.asyncio
    async def test_base64_is_excluded_from_model_visible_tool_text(self) -> None:
        invoker = _make_invoker(media=_FakeMediaClient())

        result = await invoker._invoke_attachments_read_image(
            _request(
                {
                    "source": "document_media",
                    "document_uid": "doc-1",
                    "file_name": "diagram.png",
                }
            )
        )

        encoded = base64.b64encode(_PNG_BYTES).decode("ascii")
        text = _block_text(result)
        assert encoded not in text
        assert "data:" not in text
        # The model still gets a useful acknowledgement.
        assert "diagram.png" in text


class TestErrorPaths:
    @pytest.mark.asyncio
    async def test_unsupported_multimodal_capability_returns_clear_error(self) -> None:
        media = _FakeMediaClient()
        invoker = _make_invoker(media=media, supports_image=False)

        result = await invoker._invoke_attachments_read_image(
            _request(
                {
                    "source": "document_media",
                    "document_uid": "doc-1",
                    "file_name": "diagram.png",
                }
            )
        )

        assert result.is_error is True
        assert "cannot accept image input" in _block_text(result)
        assert result.images == ()
        # Capability is checked before any fetch.
        assert media.calls == []

    @pytest.mark.asyncio
    async def test_conversation_attachment_not_implemented(self) -> None:
        media = _FakeMediaClient()
        invoker = _make_invoker(media=media)

        result = await invoker._invoke_attachments_read_image(
            _request({"source": "conversation_attachment", "attachment_id": "att-1"})
        )

        assert result.is_error is True
        assert "not implemented" in _block_text(result)
        assert media.calls == []

    @pytest.mark.asyncio
    async def test_document_media_missing_reference_is_invalid(self) -> None:
        invoker = _make_invoker(media=_FakeMediaClient())

        result = await invoker._invoke_attachments_read_image(
            _request({"source": "document_media", "document_uid": "doc-1"})
        )

        assert result.is_error is True
        assert "Invalid attachments.read_image arguments" in _block_text(result)

    @pytest.mark.asyncio
    async def test_non_image_file_name_rejected(self) -> None:
        media = _FakeMediaClient()
        invoker = _make_invoker(media=media)

        result = await invoker._invoke_attachments_read_image(
            _request(
                {
                    "source": "document_media",
                    "document_uid": "doc-1",
                    "file_name": "notes.txt",
                }
            )
        )

        assert result.is_error is True
        assert "is not an image" in _block_text(result)
        assert media.calls == []

    @pytest.mark.asyncio
    async def test_media_fetch_failure_is_surfaced_cleanly(self) -> None:
        media = _FakeMediaClient(error=RuntimeError("403 forbidden"))
        invoker = _make_invoker(media=media)

        result = await invoker._invoke_attachments_read_image(
            _request(
                {
                    "source": "document_media",
                    "document_uid": "doc-secret",
                    "file_name": "diagram.png",
                }
            )
        )

        assert result.is_error is True
        text = _block_text(result)
        assert "Could not read image" in text
        # The raw backend error / ReBAC internals are not leaked to the model.
        assert "403 forbidden" not in text


class TestImageInjectionBuilder:
    def _tool_message(
        self, *, call_id: str, label: str, with_image: bool
    ) -> ToolMessage:
        images = (
            (
                ToolImageContent(
                    mime_type="image/png", base64_data="QUFBQQ==", label=label
                ),
            )
            if with_image
            else ()
        )
        return ToolMessage(
            content="loaded",
            tool_call_id=call_id,
            name="attachments_read_image",
            artifact=ToolInvocationResult(
                tool_ref=TOOL_REF_ATTACHMENTS_READ_IMAGE, images=images
            ),
        )

    def test_builds_openai_image_url_block(self) -> None:
        messages = [
            HumanMessage(content="show me the diagram"),
            AIMessage(content=""),
            self._tool_message(call_id="c1", label="diagram.png", with_image=True),
        ]

        injected = build_image_injection_messages(messages)

        assert len(injected) == 1
        blocks = _dict_blocks(injected[0])
        image_blocks = [b for b in blocks if b.get("type") == "image_url"]
        assert len(image_blocks) == 1
        assert image_blocks[0]["image_url"]["url"] == "data:image/png;base64,QUFBQQ=="

    def test_no_images_yields_no_injection(self) -> None:
        messages = [
            HumanMessage(content="hi"),
            self._tool_message(call_id="c1", label="x", with_image=False),
        ]
        assert build_image_injection_messages(messages) == []

    def test_only_most_recent_tool_batch_is_injected(self) -> None:
        # An older tool image (already injected on a prior pass) must not be
        # re-injected: it is not part of the trailing ToolMessage run.
        messages = [
            self._tool_message(call_id="old", label="old.png", with_image=True),
            AIMessage(content=""),
            self._tool_message(call_id="new", label="new.png", with_image=True),
        ]

        injected = build_image_injection_messages(messages)

        assert len(injected) == 1
        labels = [
            b["text"] for b in _dict_blocks(injected[0]) if b.get("type") == "text"
        ]
        assert labels == ["Attached image: new.png"]
