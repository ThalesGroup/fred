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

"""``ToolkitAssetProcessor`` for the ``ppt_filler`` provider (PPTFILL-04 / #1833).

First consumer of the generic toolkit-asset-processor seam. The uploaded ``.pptx`` is the
single source of truth: when the params carry upload bytes, this processor uploads the
blob under the FIXED per-agent key, RE-PARSES the bytes server-side (PPTFILL-01
:func:`~agentic_backend.integrations.ppt_filler.parser.parse`), and persists *that* schema
— the frontend's inline analyze is preview only.

Conditional behaviour (RFC "Save flow" table):

================================== ==========================================================
 Incoming params                    Action
================================== ==========================================================
 ``template_upload_b64`` present     decode → upload blob (fixed key) → re-parse → on errors
                                     raise :class:`ToolkitAssetValidationError` (→422) → else
                                     write ``schema_slides`` → STRIP ``template_upload_b64``
 bytes absent, schema present        no-op pass-through (ordinary edit; template untouched)
 bytes absent, schema absent, req.   raise :class:`ToolkitAssetValidationError` (→422)
================================== ==========================================================

Hard invariant: the returned (persisted) params MUST NEVER contain ``template_upload_b64``.
"""

from __future__ import annotations

import base64
import binascii
import logging
from typing import List, Optional

from agentic_backend.core.tools.toolkit_asset_processor import (
    TemplateErrorLike,
    ToolkitAssetProcessor,
    ToolkitAssetStore,
    ToolkitAssetValidationError,
)
from agentic_backend.integrations.ppt_filler.folder_resolution import (
    FolderResolver,
    resolve_and_validate_images,
)
from agentic_backend.integrations.ppt_filler.parser import parse
from agentic_backend.integrations.ppt_filler.ppt_filler_params import (
    PPT_FILLER_PROVIDER,
    PptFillerParams,
)

logger = logging.getLogger(__name__)

# Stable error codes for processor-level (non per-slide) rejections. Reuse the
# ``{slide, key, code, message}`` shape (slide=0, key="" for non-slide errors) so the
# 422 body matches the analyze endpoint exactly.
CODE_ASSET_REQUIRED = "asset_required"
CODE_INVALID_UPLOAD = "invalid_upload"

# python-pptx content type for a .pptx upload.
_PPTX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
)


class PptFillerAssetProcessor(ToolkitAssetProcessor):
    """Process ``ppt_filler`` agent params at save time."""

    provider = PPT_FILLER_PROVIDER
    asset_required = True
    accepted_file_types = [
        ".pptx",
        _PPTX_CONTENT_TYPE,
    ]

    async def process(
        self,
        params: PptFillerParams,
        *,
        agent_id: str,
        store: ToolkitAssetStore,
        team_id: Optional[str] = None,
        folder_resolver: Optional[object] = None,
    ) -> PptFillerParams:
        # ``team_id`` is accepted for seam symmetry; the resolver is already scoped to the
        # agent's space (team vs personal) by the caller, so the processor only needs the
        # resolver itself. A loosely-typed ``Optional[object]`` keeps the base seam free of
        # an import cycle; here we narrow it to the structural ``FolderResolver``.
        resolver: Optional[FolderResolver] = folder_resolver  # type: ignore[assignment]

        upload_b64 = params.template_upload_b64

        # --- State 1: upload bytes present → upload, re-parse, write schema, strip bytes.
        if upload_b64:
            pptx_bytes = self._decode_upload(upload_b64)

            result = self._parse_or_raise(pptx_bytes)
            # Space-aware folder resolution / image-location validation. Skipped entirely
            # when no resolver was threaded in (backward-compat / no folders configured):
            # behaves exactly as before. With a resolver, resolved folder_tag_id values are
            # written into the schema and folder_not_found / image_key_invalid_location are
            # appended to the errors below.
            if resolver is not None:
                result = await resolve_and_validate_images(pptx_bytes, result, resolver)
            if result.errors:
                # Source-of-truth validation failed (parse OR image) → reject save (422).
                raise ToolkitAssetValidationError(list(result.errors))

            # Valid template: upload the blob under the FIXED per-agent key.
            await store.upload_agent_config_blob(
                key=params.template_key,
                file_content=pptx_bytes,
                filename=params.template_key,
                agent_id=agent_id,
                content_type=_PPTX_CONTENT_TYPE,
            )

            # Persist the server-recomputed schema; STRIP the transient upload field.
            # model_copy returns a NEW model (no in-place mutation of the input).
            return params.model_copy(
                update={
                    "schema_slides": list(result.slides),
                    "template_upload_b64": None,
                }
            )

        # --- State 2: bytes absent, schema present → no-op pass-through.
        if params.schema_slides:
            return params

        # --- State 3: bytes absent, schema absent, asset required → reject.
        if self.asset_required:
            raise ToolkitAssetValidationError(
                [
                    TemplateErrorLike(
                        slide=0,
                        key="",
                        code=CODE_ASSET_REQUIRED,
                        message=(
                            "PPT Filler requires a PowerPoint template, but none was "
                            "provided and none is configured. Upload a .pptx template."
                        ),
                    )
                ]
            )

        # Asset not required and nothing to do: pass through unchanged.
        return params

    @staticmethod
    def _decode_upload(upload_b64: str) -> bytes:
        try:
            return base64.b64decode(upload_b64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ToolkitAssetValidationError(
                [
                    TemplateErrorLike(
                        slide=0,
                        key="",
                        code=CODE_INVALID_UPLOAD,
                        message=(
                            "The uploaded template could not be base64-decoded. "
                            "Re-select the .pptx file and try again."
                        ),
                    )
                ]
            ) from exc

    @staticmethod
    def _parse_or_raise(pptx_bytes: bytes):
        try:
            return parse(pptx_bytes)
        except Exception as exc:  # noqa: BLE001 - any unreadable .pptx is a 422 reject
            raise ToolkitAssetValidationError(
                [
                    TemplateErrorLike(
                        slide=0,
                        key="",
                        code=CODE_INVALID_UPLOAD,
                        message=(
                            f"The uploaded file could not be read as a .pptx: {exc}"
                        ),
                    )
                ]
            ) from exc


# Re-exported for symmetry; the registry imports the class directly.
__all__: List[str] = [
    "PptFillerAssetProcessor",
    "CODE_ASSET_REQUIRED",
    "CODE_INVALID_UPLOAD",
]
