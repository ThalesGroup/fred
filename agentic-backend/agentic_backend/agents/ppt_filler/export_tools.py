"""Export tools for PPT Filler agent - template filling and file generation."""

import json
import logging
import tempfile
from pathlib import Path
from typing import Any

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from agentic_backend.agents.ppt_filler.pydantic_models import (
    CV,
    EnjeuxBesoins,
    PrestationFinanciere,
)
from agentic_backend.agents.reference_editor.powerpoint_template_util import (
    fill_slide_from_structured_response,
)
from agentic_backend.core.chatbot.chat_schema import LinkKind, LinkPart

logger = logging.getLogger(__name__)


def _maitrise_to_emoji(maitrise: int) -> str:
    """
    Convert maitrise level (1-5) to emoji representation.
    Uses filled (●) and empty (○) circles.

    Args:
        maitrise: Integer between 1 and 5

    Returns:
        String like "●●●○○" for level 3
    """
    level = max(1, min(5, maitrise))
    return "●" * level + "○" * (5 - level)


def _pydantic_to_template_data(
    enjeux: EnjeuxBesoins, cv: CV, prestation: PrestationFinanciere
) -> dict:
    """
    Convert Pydantic models to template data structure.

    The template expects numbered keys for arrays:
    - formation1, dateFormation1, formation2, dateFormation2, ...
    - langue1, maitriseLangue1, ...
    - competenceManagement1, maitriseManagement1, ...
    - entreprise1, poste1, duree1, realisations1, ...

    Args:
        enjeux: EnjeuxBesoins model
        cv: CV model
        prestation: PrestationFinanciere model

    Returns:
        Nested dict ready for fill_slide_from_structured_response
    """
    # EnjeuxBesoins - simple passthrough
    enjeux_dict = enjeux.model_dump()

    # CV - convert arrays to numbered keys
    cv_dict: dict[str, Any] = {"poste": cv.poste}

    # Formations (max 3)
    for i, formation in enumerate(cv.formations[:3], 1):
        cv_dict[f"dateFormation{i}"] = formation.date
        cv_dict[f"formation{i}"] = formation.nom

    # Langues
    for i, langue in enumerate(cv.langues[:3], 1):
        cv_dict[f"langue{i}"] = langue.langue
        cv_dict[f"maitriseLangue{i}"] = _maitrise_to_emoji(langue.maitrise)

    # Compétences Management
    for i, comp in enumerate(cv.competencesManagement[:3], 1):
        cv_dict[f"competenceManagement{i}"] = comp.competence
        cv_dict[f"maitriseManagement{i}"] = _maitrise_to_emoji(comp.maitrise)

    # Compétences Informatique
    for i, comp in enumerate(cv.competencesInformatique[:3], 1):
        cv_dict[f"competenceInformatique{i}"] = comp.competence
        cv_dict[f"maitriseInformatique{i}"] = _maitrise_to_emoji(comp.maitrise)

    # Compétences Gestion Projet
    for i, comp in enumerate(cv.competencesGestionProjet[:3], 1):
        cv_dict[f"competenceGestionProjet{i}"] = comp.competence
        cv_dict[f"maitriseGestionProjet{i}"] = _maitrise_to_emoji(comp.maitrise)

    # Expériences
    for i, exp in enumerate(cv.experiences[:3], 1):
        cv_dict[f"entreprise{i}"] = exp.entreprise
        cv_dict[f"poste{i}"] = exp.poste
        cv_dict[f"duree{i}"] = exp.duree
        cv_dict[f"realisations{i}"] = exp.realisations

    # PrestationFinanciere - convert prestations array to numbered keys
    prestation_dict: dict[str, Any] = {"prixTotal": prestation.prixTotal}
    for i, prest in enumerate(prestation.prestations, 1):
        prestation_dict[f"prestation{i}"] = prest.nom
        prestation_dict[f"prix{i}"] = prest.prix
        prestation_dict[f"charge{i}"] = prest.charge
        prestation_dict[f"prixTotalPrestation{i}"] = prest.prixTotal

    return {
        "enjeuxBesoins": enjeux_dict,
        "cv": cv_dict,
        "prestationFinanciere": prestation_dict,
    }


class ExportTools:
    """Export tools for PPT template filling."""

    def __init__(self, agent):
        """Initialize export tools with reference to parent agent."""
        self.agent = agent

    def get_fill_template_tool(self):
        """Tool that fills the PPT template with extracted data."""

        @tool
        async def fill_template(
            runtime: ToolRuntime,
            enjeux_json: str,
            cv_json: str,
            prestation_json: str,
        ):
            """
            Remplit le template PPT avec les données extraites.

            IMPORTANT: Les trois JSON doivent avoir été extraits via les outils d'extraction
            (extract_enjeux_besoins, extract_cv, extract_prestation_financiere).

            Args:
                enjeux_json: JSON string of EnjeuxBesoins
                cv_json: JSON string of CV
                prestation_json: JSON string of PrestationFinanciere

            Returns:
                Lien de téléchargement du fichier PowerPoint généré
            """
            try:
                # 1. Parse JSON strings into Pydantic models
                logger.info("[fill_template] Starting template filling process")
                logger.info(
                    f"[fill_template] Parsing JSON inputs - enjeux length: {len(enjeux_json)}, cv length: {len(cv_json)}, prestation length: {len(prestation_json)}"
                )
                enjeux = EnjeuxBesoins.model_validate_json(enjeux_json)
                cv = CV.model_validate_json(cv_json)
                prestation = PrestationFinanciere.model_validate_json(prestation_json)
                logger.info("[fill_template] JSON parsing successful")

                # 2. Convert to template data structure
                logger.info("[fill_template] Converting to template data structure")
                template_data = _pydantic_to_template_data(enjeux, cv, prestation)
                logger.info(
                    f"[fill_template] Template data keys: {list(template_data.keys())}"
                )

                # 3. Fetch template from agent assets
                template_key = (
                    self.agent.get_tuned_text("ppt.template_key") or "ppt_template.pptx"
                )
                logger.info(f"[fill_template] Fetching template: {template_key}")
                template_path = await self.agent.fetch_config_blob_to_tempfile(
                    template_key, suffix=".pptx"
                )
                logger.info(f"[fill_template] Template fetched to: {template_path}")

                # 4. Fill the template
                with tempfile.NamedTemporaryFile(
                    delete=False, suffix=".pptx", prefix="reference_filled_"
                ) as out:
                    output_path = Path(out.name)

                logger.info(
                    f"[fill_template] Filling template: {template_path} -> {output_path}"
                )
                fill_slide_from_structured_response(
                    template_path, template_data, output_path
                )
                logger.info(
                    f"[fill_template] Template filled successfully, output file size: {output_path.stat().st_size} bytes"
                )

                # 5. Upload to user storage
                user_id = self.agent.get_end_user_id()
                final_key = f"{user_id}_{output_path.name}"
                logger.info(
                    f"[fill_template] Uploading to user storage with key: {final_key}"
                )

                with open(output_path, "rb") as f:
                    upload_result = await self.agent.upload_user_blob(
                        key=final_key,
                        file_content=f,
                        filename=f"Reference_Filled_{self.agent.get_id()}.pptx",
                        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    )

                # Clean up temp file
                output_path.unlink(missing_ok=True)

                logger.info(
                    f"[fill_template] ✅ PPT generated successfully: {upload_result.download_url}"
                )

                # Return LinkPart directly for proper UI rendering
                return LinkPart(
                    href=upload_result.download_url,
                    title=f"📥 Télécharger {upload_result.file_name}",
                    kind=LinkKind.download,
                    mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                )

            except json.JSONDecodeError as e:
                logger.error(f"JSON parsing error: {e}", exc_info=True)
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                f"❌ Erreur de parsing JSON: {str(e)}",
                                tool_call_id=runtime.tool_call_id,
                            )
                        ]
                    }
                )
            except FileNotFoundError as e:
                logger.error(f"Template not found: {e}", exc_info=True)
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                "❌ Template PowerPoint introuvable. "
                                "Veuillez configurer le template dans les paramètres de l'agent.",
                                tool_call_id=runtime.tool_call_id,
                            )
                        ]
                    }
                )
            except Exception as e:
                logger.error(f"Error filling template: {e}", exc_info=True)
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                f"❌ Erreur lors de la génération du PPT: {str(e)}",
                                tool_call_id=runtime.tool_call_id,
                            )
                        ]
                    }
                )

        return fill_template
