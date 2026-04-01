from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path

from agentic_backend.agents.ppt_filler.powerpoint_template_util import (
    fill_slide_from_structured_response,
)
from agentic_backend.agents.ppt_filler.pydantic_models import (
    CV,
    EnjeuxBesoins,
    PrestationFinanciere,
)
from agentic_backend.core.agents.v2.authoring import ToolContext, tool

from ..helpers import convert_maitrise_to_emoji


@tool(
    tool_ref="ppt.fill_template",
    description="Générer le PowerPoint final et publier le fichier pour l'utilisateur.",
    success_message="Présentation PowerPoint générée avec succès.",
)
async def fill_template(
    ctx: ToolContext,
    enjeuxBesoins: EnjeuxBesoins,
    cv: CV,
    prestationFinanciere: PrestationFinanciere,
):
    template_key = ctx.setting_text("template_key", default="ppt_template.pptx")
    template_resource = await ctx.read_resource(template_key)

    template_path: Path | None = None
    output_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pptx") as handle:
            handle.write(template_resource.content_bytes)
            template_path = Path(handle.name)

        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".pptx",
            prefix="reference_filled_",
        ) as handle:
            output_path = Path(handle.name)

        cv_dict = cv.model_dump()
        for index in range(1, 4):
            for category in (
                "Langue",
                "Management",
                "Informatique",
                "GestionProjet",
            ):
                key = f"maitrise{category}{index}"
                cv_dict[key] = convert_maitrise_to_emoji(cv_dict.get(key, ""))

        fill_slide_from_structured_response(
            template_path,
            {
                "enjeuxBesoins": enjeuxBesoins.model_dump(),
                "cv": cv_dict,
                "prestationFinanciere": prestationFinanciere.model_dump(),
            },
            output_path,
        )

        timestamp = datetime.now().strftime("%m%d%H%M")
        file_name = f"Prop_commerciale_{timestamp}.pptx"
        return await ctx.publish_bytes(
            file_name=file_name,
            content=output_path.read_bytes(),
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "presentationml.presentation"
            ),
            title="Télécharger la présentation générée",
        )
    finally:
        if template_path is not None:
            template_path.unlink(missing_ok=True)
        if output_path is not None:
            output_path.unlink(missing_ok=True)
