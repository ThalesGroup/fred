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
Offline unit tests for the RUNTIME-08 ``attachments.read_image`` built-in
catalog entry and its typed arguments, plus the ``ToolInvocationResult.images``
contract carrier.

Verifies:
- the tool is registered with the TOOL_INVOKER backend and the right args schema
- source-discriminated validation (conversation_attachment vs document_media)
- the image artifact carrier defaults to an empty tuple and round-trips bytes
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fred_sdk.contracts.context import ToolImageContent, ToolInvocationResult
from fred_sdk.support.builtins import (
    TOOL_REF_ATTACHMENTS_READ_IMAGE,
    AttachmentsReadImageToolArgs,
    BuiltinToolBackend,
    get_builtin_tool_spec,
    list_builtin_tool_specs,
)


class TestCatalogEntry:
    def test_tool_ref_value_is_stable(self) -> None:
        assert TOOL_REF_ATTACHMENTS_READ_IMAGE == "attachments.read_image"

    def test_spec_registered_with_tool_invoker_backend(self) -> None:
        spec = get_builtin_tool_spec(TOOL_REF_ATTACHMENTS_READ_IMAGE)
        assert spec is not None
        assert spec.backend is BuiltinToolBackend.TOOL_INVOKER
        assert spec.args_schema is AttachmentsReadImageToolArgs
        assert spec.default_description

    def test_present_in_full_catalog(self) -> None:
        refs = {spec.tool_ref for spec in list_builtin_tool_specs()}
        assert TOOL_REF_ATTACHMENTS_READ_IMAGE in refs


class TestArgsValidation:
    def test_conversation_attachment_requires_attachment_id(self) -> None:
        args = AttachmentsReadImageToolArgs(
            source="conversation_attachment", attachment_id="attachment-123"
        )
        assert args.attachment_id == "attachment-123"

    def test_conversation_attachment_missing_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AttachmentsReadImageToolArgs(source="conversation_attachment")

    def test_document_media_requires_uid_and_file_name(self) -> None:
        args = AttachmentsReadImageToolArgs(
            source="document_media",
            document_uid="doc-1",
            file_name="page-1-image-2.png",
        )
        assert args.document_uid == "doc-1"
        assert args.file_name == "page-1-image-2.png"

    @pytest.mark.parametrize(
        "payload",
        [
            {"source": "document_media", "document_uid": "doc-1"},
            {"source": "document_media", "file_name": "img.png"},
            {"source": "document_media"},
        ],
    )
    def test_document_media_partial_reference_rejected(self, payload: dict) -> None:
        with pytest.raises(ValidationError):
            AttachmentsReadImageToolArgs(**payload)

    def test_unknown_source_rejected(self) -> None:
        # model_validate exercises runtime validation of the source discriminator
        # (a bare constructor call with a bad literal is caught statically instead).
        with pytest.raises(ValidationError):
            AttachmentsReadImageToolArgs.model_validate({"source": "presigned_url"})


class TestImageCarrier:
    def test_result_images_default_empty(self) -> None:
        result = ToolInvocationResult(tool_ref=TOOL_REF_ATTACHMENTS_READ_IMAGE)
        assert result.images == ()

    def test_image_content_round_trips(self) -> None:
        image = ToolImageContent(
            mime_type="image/png", base64_data="QUFBQQ==", label="page-1-image-2.png"
        )
        result = ToolInvocationResult(
            tool_ref=TOOL_REF_ATTACHMENTS_READ_IMAGE, images=(image,)
        )
        assert result.images[0].mime_type == "image/png"
        assert result.images[0].base64_data == "QUFBQQ=="
        assert result.images[0].label == "page-1-image-2.png"
