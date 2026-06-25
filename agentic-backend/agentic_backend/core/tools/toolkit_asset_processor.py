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

"""Generic *toolkit asset processor* seam (PPTFILL-04 / #1833).

A reusable extension point for any inprocess toolkit that uploads a document at
agent-save time and derives configuration from it. It generalises the ``ppt_filler``
need so future toolkits plug in by registering a processor + metadata, without new
endpoints or bespoke save logic.

The contract is a **pure ``params -> params`` transform** that MAY upload a config blob
and derive params, raising a TYPED error (:class:`ToolkitAssetValidationError`) on invalid
input. The single generic hook in the agent create/update service runs the matching
processor for each tool's params and persists the **returned** params.

Companion registry: :mod:`agentic_backend.core.tools.toolkit_asset_registry` (parallel to
:mod:`agentic_backend.core.tools.inprocess_toolkit_registry`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, BinaryIO, List, Optional, Protocol, runtime_checkable

from pydantic import BaseModel

if TYPE_CHECKING:  # avoid an import cycle through agent_spec at module import time
    from agentic_backend.core.agents.agent_spec import ToolParams


class TemplateErrorLike(BaseModel):
    """Structured per-asset validation error.

    Same shape as :class:`~agentic_backend.integrations.ppt_filler.parser.TemplateError`
    (``{slide, key, code, message}``) — the shared error contract the analyze endpoint
    uses and that the save path turns into a ``422 { "errors": [...] }`` response. Declared
    here (generically) so the seam does not depend on the ``ppt_filler`` package; concrete
    ``TemplateError`` instances are structurally compatible.
    """

    slide: int
    key: str
    code: str
    message: str


class ToolkitAssetValidationError(Exception):
    """Raised by a processor when the incoming params are invalid.

    Carries the structured ``errors`` list so the API layer can turn it into a ``422``
    with the SAME ``{ "errors": [...] }`` shape the analyze endpoint returns. Each error
    exposes ``slide``, ``key``, ``code`` and ``message``. The constructor normalises any
    structurally compatible model (e.g. the parser's ``TemplateError``) to
    :class:`TemplateErrorLike`, so the carried shape is uniform regardless of source.
    """

    def __init__(self, errors: List[BaseModel]):
        self.errors: List[TemplateErrorLike] = [
            e
            if isinstance(e, TemplateErrorLike)
            else TemplateErrorLike.model_validate(e.model_dump())
            for e in errors
        ]
        codes = ", ".join(e.code for e in self.errors) or "none"
        super().__init__(f"Toolkit asset validation failed ({codes}).")

    def errors_payload(self) -> list[dict]:
        """Return the ``errors`` list as plain dicts for a JSON ``422`` body."""
        return [e.model_dump() for e in self.errors]


@runtime_checkable
class ToolkitAssetStore(Protocol):
    """Narrow storage port the processor depends on (injection seam).

    A subset of :class:`~agentic_backend.common.kf_workspace_client.KfWorkspaceClient`:
    the only operation a processor needs is uploading a config blob to the
    admin/agent-config scoped store under a fixed key. Tests pass a fake; production wraps
    a real ``KfWorkspaceClient``. Keeping the port narrow keeps the processor pure and
    decoupled from HTTP/token plumbing.
    """

    async def upload_agent_config_blob(
        self,
        key: str,
        file_content: bytes | BinaryIO,
        filename: str,
        agent_id: str,
        content_type: Optional[str] = None,
    ) -> object: ...


class ToolkitAssetProcessor(ABC):
    """Contract: a pure ``params -> params`` transform run at agent save time.

    A processor MAY upload a config blob and derive params, and MUST raise
    :class:`ToolkitAssetValidationError` on invalid input. It MUST NOT mutate the input in
    place — it returns the (possibly new) params to persist. The single highest-risk
    invariant (for ``ppt_filler``) is that any transient raw-upload field is stripped from
    the returned params before persistence.

    Declarative metadata (read by BOTH the UI and the backend):

    - :attr:`provider` — the discriminator the processor is registered under.
    - :attr:`asset_required` — whether the toolkit cannot function without its asset (the
      UI gates Save on it; the backend rejects a save that lacks both an upload and a
      previously derived config).
    - :attr:`accepted_file_types` — accepted upload types (extensions and/or MIME), so the
      UI can constrain the file picker and the catalog can advertise them.
    """

    #: Provider discriminator this processor handles (e.g. ``"ppt_filler"``).
    provider: str
    #: Whether the toolkit's asset is mandatory.
    asset_required: bool = False
    #: Accepted upload file types (extensions and/or MIME types).
    accepted_file_types: List[str] = []

    @abstractmethod
    async def process(
        self, params: "ToolParams", *, agent_id: str, store: ToolkitAssetStore
    ) -> "ToolParams":
        """Return the params to persist for ``params``.

        - Upload bytes present → upload the blob (fixed key), re-parse server-side, write
          the derived config, and STRIP the transient upload field.
        - Bytes absent, config present → no-op pass-through (ordinary edit).
        - Bytes absent, config absent, :attr:`asset_required` → raise
          :class:`ToolkitAssetValidationError`.
        """
        raise NotImplementedError
