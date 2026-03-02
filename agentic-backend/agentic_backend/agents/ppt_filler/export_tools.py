"""Export tools for PPT Filler agent - template filling and file generation."""

import json
import logging
import tempfile
from datetime import datetime
from pathlib import Path

from langchain.tools import tool
from pydantic import ValidationError

from agentic_backend.agents.ppt_filler.powerpoint_template_util import (
    fill_slide_from_structured_response,
)
from agentic_backend.agents.ppt_filler.pydantic_models import (
    CV,
    EnjeuxBesoins,
    PrestationFinanciere,
)
from agentic_backend.core.chatbot.chat_schema import LinkKind, LinkPart

logger = logging.getLogger(__name__)


def _convert_maitrise_to_emoji(level: str | int) -> str:
    """Convert maitrise level (1-5) to emoji pattern (●○○○○ to ●●●●●).

    Args:
        level: Integer or string from 1 to 5, or empty string for no skill

    Returns:
        String with filled (●) and empty (○) circles, or empty string if no level
    """
    if isinstance(level, str):
        if not level.strip():
            return ""
        try:
            level = int(level)
        except ValueError:
            return ""
    if not 1 <= level <= 5:
        return ""
    filled = "●" * level
    empty = "○" * (5 - level)
    return filled + empty


class ExportTools:
    """Helper class to organize PPT export tools."""

    def __init__(self, agent):
        self.agent = agent

    def get_fill_template_tool(self):
        """Create the fill_template tool."""

        # Define the schema — each section is a top-level kwarg so the LLM
        # doesn't have to nest them inside a wrapper object.
        tool_schema = {
            "type": "object",
            "properties": {
                "enjeuxBesoins": {"$ref": "#/$defs/EnjeuxBesoins"},
                "cv": {"$ref": "#/$defs/CV"},
                "prestationFinanciere": {"$ref": "#/$defs/PrestationFinanciere"},
            },
            "required": ["enjeuxBesoins", "cv", "prestationFinanciere"],
            "$defs": {
                "EnjeuxBesoins": EnjeuxBesoins.model_json_schema(),
                "CV": CV.model_json_schema(),
                "PrestationFinanciere": PrestationFinanciere.model_json_schema(),
            },
        }

        @tool(args_schema=tool_schema)
        async def fill_template(**kwargs):
            """
            Génère le fichier PowerPoint à partir des données extraites.

            Args:
                enjeuxBesoins: Contexte et missions du projet
                cv: Informations CV de l'intervenant
                prestationFinanciere: Informations financières

            Returns:
                Lien de téléchargement du fichier PowerPoint généré
            """
            try:
                # 1. Extract and validate the three sections (max_length enforced here)
                enjeux_data = kwargs.get("enjeuxBesoins", {})
                cv_data = kwargs.get("cv", {})
                prestation_data = kwargs.get("prestationFinanciere", {})

                validation_errors = []
                for section_name, model_cls, section_data in [
                    ("enjeuxBesoins", EnjeuxBesoins, enjeux_data),
                    ("cv", CV, cv_data),
                    ("prestationFinanciere", PrestationFinanciere, prestation_data),
                ]:
                    try:
                        model_cls.model_validate(section_data)
                    except ValidationError as e:
                        for err in e.errors():
                            field = ".".join(str(loc) for loc in err["loc"])
                            validation_errors.append(
                                f"{section_name}.{field}: {err['msg']}"
                            )

                if validation_errors:
                    error_list = "\n".join(f"- {e}" for e in validation_errors)
                    return (
                        f"❌ Validation échouée. Raccourcis les champs trop longs "
                        f"puis rappelle fill_template:\n{error_list}"
                    )

                enjeux = EnjeuxBesoins.model_validate(enjeux_data)
                cv = CV.model_validate(cv_data)
                prestation = PrestationFinanciere.model_validate(prestation_data)

                # 2. Convert maitrise levels to emojis for CV
                cv_dict = cv.model_dump()
                for i in range(1, 4):
                    for category in [
                        "Langue",
                        "Management",
                        "Informatique",
                        "GestionProjet",
                    ]:
                        key = f"maitrise{category}{i}"
                        cv_dict[key] = _convert_maitrise_to_emoji(cv_dict.get(key, ""))

                # 3. Build template data structure
                template_data = {
                    "enjeuxBesoins": enjeux.model_dump(),
                    "cv": cv_dict,
                    "prestationFinanciere": prestation.model_dump(),
                }

                # 4. Fetch template from agent assets
                template_key = (
                    self.agent.get_tuned_text("ppt.template_key") or "ppt_template.pptx"
                )
                template_path = await self.agent.fetch_config_blob_to_tempfile(
                    template_key, suffix=".pptx"
                )

                # 5. Fill the template
                with tempfile.NamedTemporaryFile(
                    delete=False, suffix=".pptx", prefix="reference_filled_"
                ) as out:
                    output_path = Path(out.name)

                    fill_slide_from_structured_response(
                        template_path, template_data, output_path
                    )

                # 6. Upload to user storage
                timestamp = datetime.now().strftime("%m%d%H%M")
                final_key = f"Prop_commerciale_{timestamp}.pptx"

                with open(output_path, "rb") as f:
                    upload_result = await self.agent.upload_user_blob(
                        key=final_key,
                        file_content=f,
                        filename=final_key,
                        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    )

                # Clean up temp file
                output_path.unlink(missing_ok=True)

                # Return LinkPart directly for proper UI rendering
                return LinkPart(
                    href=upload_result.download_url,
                    title=upload_result.file_name,
                    kind=LinkKind.download,
                    mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                ).model_dump(mode="json")

            except json.JSONDecodeError as e:
                error_msg = f"❌ Erreur de parsing JSON: {str(e)}"
                logger.error(f"[fill_template] {error_msg}")
                return error_msg
            except Exception as e:
                error_msg = f"❌ Erreur lors de la génération du PPT: {str(e)}"
                logger.error(f"[fill_template] {error_msg}", exc_info=True)
                return error_msg

        return fill_template
