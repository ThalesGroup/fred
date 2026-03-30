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

from agentic_backend.agents.ppt_filler.pydantic_models import PrestationFinanciere
from agentic_backend.core.agents.v2.authoring import ToolContext, prompt_md, tool

PRESTATION_FINANCIERE_QUERIES: list[tuple[str, int]] = [
    ("Nom et coût unitaire des prestations", 8),
    ("Charge estimée en unités d'œuvre pour chaque prestation", 8),
    ("Coût total de chaque prestation et coût total global", 8),
]

EXTRACT_PRESTATION_FINANCIERE_PROMPT = prompt_md(
    package="agentic_backend.agents.v2.production.ppt_filler_react",
    file_name="ppt_filler_extract_prestation_prompt.md",
)


@tool(
    tool_ref="ppt.extract_prestation_financiere",
    description="Extraire les prestations et montants financiers du dossier.",
    success_message="Prestations financières extraites.",
)
async def extract_prestation_financiere(
    ctx: ToolContext,
    context_hint: Annotated[
        str,
        Field(
            default="",
            description="Indication optionnelle pour cibler la recherche financière.",
        ),
    ] = "",
) -> PrestationFinanciere | object:
    bundle = await ctx.search_many(
        PRESTATION_FINANCIERE_QUERIES,
        context_hint=context_hint,
    )
    if not bundle.text:
        return ctx.error(
            "Aucun document exploitable trouvé pour extraire les prestations financières."
        )

    result = await ctx.extract_structured(
        PrestationFinanciere,
        prompt=EXTRACT_PRESTATION_FINANCIERE_PROMPT,
        text=bundle.text,
    )
    return (
        result
        if isinstance(result, PrestationFinanciere)
        else PrestationFinanciere.model_validate(result)
    )
