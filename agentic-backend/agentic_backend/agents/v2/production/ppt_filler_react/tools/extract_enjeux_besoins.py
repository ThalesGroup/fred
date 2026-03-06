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

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from agentic_backend.agents.ppt_filler.pydantic_models import EnjeuxBesoins
from agentic_backend.core.agents.v2.authoring import ToolContext, prompt_md, tool

ENJEUX_BESOINS_QUERIES: list[tuple[str, int]] = [
    ("Quels sont les objectifs et les missions principales du projet ?", 8),
    ("Quel est le contexte du projet ?", 8),
]

EXTRACT_ENJEUX_BESOINS_PROMPT = prompt_md(
    package="agentic_backend.agents.v2.production.ppt_filler_react",
    file_name="ppt_filler_extract_enjeux_prompt.md",
)


@tool(
    tool_ref="ppt.extract_enjeux_besoins",
    description="Extraire le contexte, les missions et la référence du dossier.",
    success_message="Enjeux et besoins extraits.",
)
async def extract_enjeux_besoins(
    ctx: ToolContext,
    context_hint: Annotated[
        str,
        Field(
            default="",
            description="Indication optionnelle, par exemple le nom du projet.",
        ),
    ] = "",
) -> EnjeuxBesoins | object:
    bundle = await ctx.search_many(
        ENJEUX_BESOINS_QUERIES,
        context_hint=context_hint,
    )
    if not bundle.text:
        return ctx.error(
            "Aucun document exploitable trouvé pour extraire les enjeux et besoins."
        )

    result = await ctx.extract_structured(
        EnjeuxBesoins,
        prompt=EXTRACT_ENJEUX_BESOINS_PROMPT,
        text=bundle.text,
    )
    enjeux = (
        result
        if isinstance(result, EnjeuxBesoins)
        else EnjeuxBesoins.model_validate(result)
    )
    if bundle.ranked_filenames:
        enjeux.refCahierCharges = bundle.ranked_filenames[0]
    return enjeux
