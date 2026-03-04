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

from agentic_backend.agents.ppt_filler.pydantic_models import CV
from agentic_backend.agents.ppt_filler.skill_mastery import (
    extract_mastery_from_image,
    inject_mastery_alt_text,
    is_raster_image,
    parse_image_refs,
)
from agentic_backend.core.agents.v2.authoring import ToolContext, prompt_md, tool

CV_QUERIES: list[tuple[str, int]] = [
    ("Intitulé du poste", 5),
    ("Trigramme de l'intervenant", 5),
    ("Formations avec dates et établissements", 8),
    ("Langues parlées et niveau de maîtrise", 8),
    ("Compétences en management et niveau de maîtrise", 8),
    ("Compétences en informatique et niveau de maîtrise", 20),
    ("Compétences en gestion de projet et niveau de maîtrise", 8),
    (
        "Expériences professionnelles avec entreprises, postes, durées et réalisations",
        15,
    ),
]

EXTRACT_CV_PROMPT = prompt_md(
    package="agentic_backend.agents.v2.production.ppt_filler_react",
    file_name="ppt_filler_extract_cv_prompt.md",
)


@tool(
    tool_ref="ppt.extract_cv",
    description="Extraire le CV structuré de l'intervenant le plus pertinent.",
    success_message="CV extrait.",
)
async def extract_cv(
    ctx: ToolContext,
    project_context: Annotated[
        str,
        Field(
            default="",
            description="Contexte projet déjà extrait pour aligner le CV.",
        ),
    ] = "",
    context_hint: Annotated[
        str,
        Field(
            default="",
            description="Indication optionnelle, par exemple le nom du candidat.",
        ),
    ] = "",
) -> CV | object:
    bundle = await ctx.search_many(CV_QUERIES, context_hint=context_hint)
    if not bundle.text:
        return ctx.error("Aucun document exploitable trouvé pour extraire le CV.")

    enriched_chunks = await _enrich_with_skill_mastery(ctx, bundle.text)
    prompt = EXTRACT_CV_PROMPT.format(project_context=project_context or "Non fourni")
    result = await ctx.extract_structured(
        CV,
        prompt=prompt,
        text=enriched_chunks,
    )
    return result if isinstance(result, CV) else CV.model_validate(result)


async def _enrich_with_skill_mastery(ctx: ToolContext, chunks_text: str) -> str:
    image_refs = parse_image_refs(chunks_text)
    if not image_refs:
        return chunks_text

    mastery_map: dict[str, int] = {}
    for document_uid, filename in image_refs:
        if not is_raster_image(filename) or filename in mastery_map:
            continue
        level: int | None = None
        try:
            image_bytes = await ctx.fetch_media(document_uid, filename)
            level = extract_mastery_from_image(image_bytes)
        except (OSError, RuntimeError, TypeError, ValueError):
            level = None
        if level is not None:
            mastery_map[filename] = level

    if not mastery_map:
        return chunks_text
    return inject_mastery_alt_text(chunks_text, mastery_map)
