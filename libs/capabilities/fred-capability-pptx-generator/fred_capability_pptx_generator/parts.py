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

"""The `pptx_generator` capability's contributed chat part.

Not a reuse of `ppt_filler`'s `PptPreviewPart`: two capabilities registering
the same class would collide at the chat-part registry.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class PptxGeneratedPart(BaseModel):
    """Contributed `pptx_generated` chat part.

    Both URLs are the durable, bearer-protected `/fs/download/{path}` hrefs
    (never a signed short-TTL link) — this part is persisted in the
    conversation, so a frozen signed URL would 403 when the chat is reopened
    later (same doctrine as `PptPreviewPart`). `version` is a per-generation
    freshness token (content hash) that drives the viewer's remount key.
    """

    type: Literal["pptx_generated"] = "pptx_generated"
    preview_id: str
    title: str
    pdf_download_url: str
    version: str
    pptx_download_url: str | None = None
    file_name: str | None = None
