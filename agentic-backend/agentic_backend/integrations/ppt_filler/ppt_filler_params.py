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

"""Agent-level typed params for the ``ppt_filler`` inprocess toolkit.

Mirrors :class:`~agentic_backend.integrations.kf_vector_search.kf_vector_search_params.KfVectorSearchParams`:
a Pydantic model carrying a ``provider`` literal discriminator that is added to the
``ToolParams`` discriminated union (see
:mod:`agentic_backend.core.agents.agent_spec`).

What it carries:

- The **derived per-slide schema** (persisted): the same per-slide grouping produced by
  the PPTFILL-01 parser (:class:`~agentic_backend.integrations.ppt_filler.parser.SlideSchema`).
- A **fixed per-agent template key** convention — one template per agent; the creator
  never chooses it. It is a constant default, not a user-editable field.
- A **transient base64 upload field** (``template_upload_b64``) used ONLY to transport new
  ``.pptx`` bytes from the form to the backend on save. It is **stripped before
  persistence** by the toolkit asset processor in a LATER slice (PPTFILL-03 / #1833); this
  module only DEFINES the field.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from agentic_backend.integrations.ppt_filler.parser import SlideSchema

PptFillerProviderType = Literal["ppt_filler"]
PPT_FILLER_PROVIDER: PptFillerProviderType = "ppt_filler"

# One template per agent: the upload always lands under this fixed key in the agent config
# blob store. The creator never picks it (RFC: "the creator never chooses it").
PPT_FILLER_TEMPLATE_KEY = "ppt_filler_template.pptx"


class PptFillerParams(BaseModel):
    """Agent-level scoping parameters for the ``ppt_filler`` inprocess tool.

    Discriminated by ``provider`` within the ``ToolParams`` union, mirroring
    :class:`KfVectorSearchParams`.
    """

    provider: PptFillerProviderType = PPT_FILLER_PROVIDER

    template_key: str = Field(
        default=PPT_FILLER_TEMPLATE_KEY,
        description=(
            "Fixed per-agent storage key for the uploaded .pptx template (one template "
            "per agent). Conventional and not user-editable — the creator never chooses "
            "it; replacing the template swaps the file under this same key."
        ),
    )

    schema_slides: List[SlideSchema] = Field(
        default_factory=list,
        alias="schema",
        serialization_alias="schema",
        description=(
            "Derived per-slide template schema (the parser output), persisted with the "
            "agent. Each entry is one slide's 1-based number and its {{key}} fields with "
            "their note descriptions. Recomputed server-side from the actual .pptx "
            "whenever the template is (re)uploaded."
        ),
    )

    template_upload_b64: Optional[str] = Field(
        default=None,
        description=(
            "TRANSIENT base64-encoded .pptx bytes, used ONLY to transport a newly "
            "(re)uploaded template from the form to the backend on save. The toolkit "
            "asset processor (PPTFILL-03 / #1833) re-parses these bytes, writes the "
            "schema, and STRIPS this field before persistence — it must never reach the "
            "store. Absent on ordinary edits (template unchanged)."
        ),
    )

    # ``schema`` is a reserved attribute name on ``BaseModel`` (``BaseModel.schema``), so
    # the per-slide field is named ``schema_slides`` in Python but aliased to ``schema``
    # for the JSON contract. ``populate_by_name`` lets callers use either name.
    model_config = {"populate_by_name": True}
