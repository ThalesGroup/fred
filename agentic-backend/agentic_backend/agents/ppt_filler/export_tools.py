"""Export tools for PPT Filler agent - template filling and file generation."""

import json
import logging
import tempfile
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

        # Define the schema for the tool
        tool_schema = {
            "type": "object",
            "properties": {
                "data": {
                    "type": "object",
                    "properties": {
                        "enjeuxBesoins": {"$ref": "#/$defs/EnjeuxBesoins"},
                        "cv": {"$ref": "#/$defs/CV"},
                        "prestationFinanciere": {
                            "$ref": "#/$defs/PrestationFinanciere"
                        },
                    },
                    "required": ["enjeuxBesoins", "cv", "prestationFinanciere"],
                },
            },
            "required": ["data"],
            "$defs": {
                "EnjeuxBesoins": EnjeuxBesoins.model_json_schema(),
                "CV": CV.model_json_schema(),
                "PrestationFinanciere": PrestationFinanciere.model_json_schema(),
            },
        }

        @tool(args_schema=tool_schema)
        async def fill_template(data: dict):
            """
            Génère le fichier PowerPoint à partir des données extraites.

            Args:
                data: Dictionnaire contenant les trois sections:
                    - enjeuxBesoins: Contexte et missions du projet
                    - cv: Informations CV de l'intervenant
                    - prestationFinanciere: Informations financières

            Returns:
                Lien de téléchargement du fichier PowerPoint généré
            """
            try:
                # 1. Extract and validate the three sections (max_length enforced here)
                enjeux_data = data.get("enjeuxBesoins", {})
                cv_data = data.get("cv", {})
                prestation_data = data.get("prestationFinanciere", {})

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
                user_id = self.agent.get_end_user_id()
                final_key = f"{user_id}_{output_path.name}"

                with open(output_path, "rb") as f:
                    upload_result = await self.agent.upload_user_blob(
                        key=final_key,
                        file_content=f,
                        filename=f"Reference_Filled_{self.agent.get_id()}.pptx",
                        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    )

                # Clean up temp file
                output_path.unlink(missing_ok=True)

                # Return LinkPart directly for proper UI rendering
                return LinkPart(
                    href=upload_result.download_url,
                    title=f"📥 Télécharger {upload_result.file_name}",
                    kind=LinkKind.download,
                    mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                )

            except json.JSONDecodeError as e:
                error_msg = f"❌ Erreur de parsing JSON: {str(e)}"
                logger.error(f"[fill_template] {error_msg}")
                return error_msg
            except Exception as e:
                error_msg = f"❌ Erreur lors de la génération du PPT: {str(e)}"
                logger.error(f"[fill_template] {error_msg}", exc_info=True)
                return error_msg

        return fill_template
