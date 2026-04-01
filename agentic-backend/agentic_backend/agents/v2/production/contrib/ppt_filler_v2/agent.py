"""V2 PPT Filler agent — extracts data from documents and fills PowerPoint templates."""

from __future__ import annotations

import json
import logging
import tempfile
from datetime import datetime
from pathlib import Path

import httpx
from pydantic import Field, ValidationError

from agentic_backend.agents.v2.production.ppt_filler_v2.export_utils import (
    convert_maitrise_to_emoji,
)
from agentic_backend.agents.v2.production.ppt_filler_v2.powerpoint_template_util import (
    fill_slide_from_structured_response,
)
from agentic_backend.agents.v2.production.ppt_filler_v2.pydantic_models import (
    CV,
    EnjeuxBesoins,
    PrestationFinanciere,
    schema_without_max_length,
)
from agentic_backend.agents.v2.production.ppt_filler_v2.skill_mastery import (
    extract_mastery_from_image,
    inject_mastery_alt_text,
    is_raster_image,
    parse_image_refs,
)
from agentic_backend.core.agents.agent_spec import FieldSpec, UIHints
from agentic_backend.core.agents.v2.authoring import (
    ReActAgent,
    ToolContext,
    ToolOutput,
    prompt_md,
    tool,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hardcoded search queries per extraction type
# ---------------------------------------------------------------------------

TOP_K_DEFAULT = 8

ENJEUX_BESOINS_QUERIES: list[tuple[str, int]] = [
    ("Quels sont les objectifs et les missions principales du projet ?", TOP_K_DEFAULT),
    ("Quel est le contexte du projet ?", TOP_K_DEFAULT),
]

CV_QUERIES: list[tuple[str, int]] = [
    ("Intitulé du poste", 5),
    ("Trigramme de l'intervenant", 5),
    ("Formations avec dates et établissements", TOP_K_DEFAULT),
    ("Langues parlées et niveau de maîtrise", TOP_K_DEFAULT),
    ("Compétences en management et niveau de maîtrise", TOP_K_DEFAULT),
    ("Compétences en informatique et niveau de maîtrise", 20),
    ("Compétences en gestion de projet et niveau de maîtrise", TOP_K_DEFAULT),
    (
        "Expériences professionnelles avec entreprises, postes, durées et réalisations",
        15,
    ),
]

PRESTATION_FINANCIERE_QUERIES: list[tuple[str, int]] = [
    ("Nom et coût unitaire des prestations", TOP_K_DEFAULT),
    ("Charge estimée en unités d'œuvre pour chaque prestation", TOP_K_DEFAULT),
    ("Coût total de chaque prestation et coût total global", TOP_K_DEFAULT),
]

# ---------------------------------------------------------------------------
# Extraction prompts
# ---------------------------------------------------------------------------

ENJEUX_BESOINS_EXTRACTION_PROMPT = """Extrais le contexte et les missions du projet depuis les extraits suivants.

RÈGLES IMPORTANTES:
- N'invente RIEN - utilise uniquement les informations présentes dans les extraits
- Si une information n'est pas trouvée, utilise une chaîne vide
- Le contexte doit décrire le projet de manière détaillée (2-3 phrases)
- Les missions doivent résumer les objectifs clés (2-3 phrases)
- Laisse refCahierCharges vide, il sera rempli automatiquement"""

CV_EXTRACTION_PROMPT = """Extrais les informations du CV de l'intervenant depuis les extraits suivants.

CONTEXTE PROJET (pour aligner les compétences et expériences):
{project_context}

RÈGLES IMPORTANTES:
- N'invente RIEN - utilise uniquement les informations présentes dans les extraits
- Les compétences et expériences doivent être pertinentes par rapport au contexte projet
- Sélectionne les compétences les plus pertinentes par rapport au projet (max 3 par catégorie)
- COMPÉTENCES INFORMATIQUES: trie par pertinence projet mais ne laisse pas de slots vides inutilement
- Pour les expériences, garde les plus récentes et pertinentes (max 3)
- Pour la maitrise (langues et compétences), utilise une échelle de 1 à 5 (en tant que string):
  "1" = Débutant, "2" = Intermédiaire, "3" = Bon, "4" = Très bon, "5" = Expert
- Si un emplacement de compétence n'est pas rempli (ex: competenceManagement3 est vide),
  la maîtrise associée (maitriseManagement3) DOIT être une chaîne vide "", pas "0"
- LANGUES: NE PAS inclure la langue maternelle du candidat (typiquement le français).
  Inclure uniquement les langues étrangères (Anglais, Espagnol, Allemand, etc.).
- Si une information n'est pas trouvée, utilise une chaîne vide
- STYLE: Rédige TOUJOURS à la troisième personne (pas de "je", "j'ai", "mon").
  Exemple: "A géré une équipe de 5 personnes" et non "J'ai géré une équipe de 5 personnes"."""

PRESTATION_FINANCIERE_EXTRACTION_PROMPT = """Extrais les prestations financières depuis les extraits suivants.

RÈGLES IMPORTANTES:
- N'invente RIEN - utilise uniquement les informations présentes dans les extraits
- Les prix doivent être en euros (nombres entiers)
- La charge est exprimée en unités d'œuvre (jours/homme typiquement)
- Le prixTotal d'une prestation = prix × charge
- Le prixTotal global = somme de tous les prixTotal des prestations
- NE PAS inventer de catégories de prestations. Si aucune information financière
  n'est trouvée dans les extraits, laisse TOUS les champs vides (chaînes vides pour
  les noms, 0 pour les montants). Ne crée pas de titres de catégories avec un coût de 0.
- Remplis uniquement les prestations pour lesquelles tu as des données concrètes
  (nom ET prix/charge). Un nom sans données financières n'est pas une prestation valide."""

PPTX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

DEFAULT_SYSTEM_PROMPT = prompt_md(
    package="agentic_backend.agents.v2.production.ppt_filler_v2",
    file_name="system_prompt.md",
)

# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


async def _enrich_with_skill_mastery(ctx: ToolContext, chunks_text: str) -> str:
    """Fetch skill images referenced in chunks and inject mastery alt text."""
    image_refs = parse_image_refs(chunks_text)
    if not image_refs:
        return chunks_text

    mastery_map: dict[str, int] = {}
    for doc_uid, filename in image_refs:
        if not is_raster_image(filename) or filename in mastery_map:
            continue
        try:
            image_bytes = await ctx.fetch_media(doc_uid, filename)
            level = extract_mastery_from_image(image_bytes)
            if level is not None:
                mastery_map[filename] = level
        except httpx.HTTPStatusError:
            continue
        except Exception:
            logger.warning(
                "[skill_mastery] Failed to fetch %s/%s",
                doc_uid,
                filename,
                exc_info=True,
            )

    if mastery_map:
        logger.info("[skill_mastery] Detected: %s", mastery_map)
        chunks_text = inject_mastery_alt_text(chunks_text, mastery_map)

    return chunks_text


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool(
    tool_ref="ppt_filler.extract.enjeux_besoins",
    description="Extrait le contexte et les missions du projet depuis les documents.",
    success_message="Enjeux et besoins extraits.",
)
async def extract_enjeux_besoins(
    ctx: ToolContext, context_hint: str = ""
) -> ToolOutput:
    bundle = await ctx.helpers.search_corpus_many(
        ENJEUX_BESOINS_QUERIES, context_hint=context_hint
    )
    if not bundle.text:
        return ctx.error("Aucun document trouvé.")

    result = await ctx.extract_structured(
        schema_without_max_length(EnjeuxBesoins),
        prompt=ENJEUX_BESOINS_EXTRACTION_PROMPT,
        text=bundle.text,
    )

    data = result.model_dump()
    if bundle.ranked_filenames:
        data["refCahierCharges"] = bundle.ranked_filenames[0]

    return ctx.json(data, text="Enjeux et besoins extraits.")


@tool(
    tool_ref="ppt_filler.extract.cv",
    description="Extrait les informations du CV de l'intervenant.",
    success_message="CV extrait.",
)
async def extract_cv(
    ctx: ToolContext, project_context: str = "", context_hint: str = ""
) -> ToolOutput:
    bundle = await ctx.helpers.search_corpus_many(CV_QUERIES, context_hint=context_hint)
    if not bundle.text:
        return ctx.error("Aucun document trouvé.")

    enriched_text = await _enrich_with_skill_mastery(ctx, bundle.text)

    result = await ctx.extract_structured(
        schema_without_max_length(CV),
        prompt=CV_EXTRACTION_PROMPT.format(
            project_context=project_context or "Non fourni"
        ),
        text=enriched_text,
    )

    return ctx.json(result, text="CV extrait.")


@tool(
    tool_ref="ppt_filler.extract.prestation_financiere",
    description="Extrait les informations de prestation financière depuis les documents.",
    success_message="Prestations financières extraites.",
)
async def extract_prestation_financiere(
    ctx: ToolContext, context_hint: str = ""
) -> ToolOutput:
    bundle = await ctx.helpers.search_corpus_many(
        PRESTATION_FINANCIERE_QUERIES, context_hint=context_hint
    )
    if not bundle.text:
        return ctx.error("Aucun document trouvé.")

    result = await ctx.extract_structured(
        schema_without_max_length(PrestationFinanciere),
        prompt=PRESTATION_FINANCIERE_EXTRACTION_PROMPT,
        text=bundle.text,
    )

    return ctx.json(result, text="Prestations financières extraites.")


@tool(
    tool_ref="ppt_filler.export.fill_template",
    description=(
        "Génère le fichier PowerPoint à partir des données extraites. "
        "Les trois arguments sont les JSON issus des outils d'extraction."
    ),
    success_message="PowerPoint généré.",
)
async def fill_template(
    ctx: ToolContext,
    enjeuxBesoins: str,
    cv: str,
    prestationFinanciere: str,
) -> ToolOutput:
    # 1. Parse and validate the three JSON sections
    try:
        enjeux_data = (
            json.loads(enjeuxBesoins)
            if isinstance(enjeuxBesoins, str)
            else enjeuxBesoins
        )
        cv_data = json.loads(cv) if isinstance(cv, str) else cv
        prestation_data = (
            json.loads(prestationFinanciere)
            if isinstance(prestationFinanciere, str)
            else prestationFinanciere
        )
    except json.JSONDecodeError as e:
        return ctx.error(f"Erreur de parsing JSON: {e}")

    validation_errors: list[str] = []
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
                validation_errors.append(f"{section_name}.{field}: {err['msg']}")

    if validation_errors:
        error_list = "\n".join(f"- {e}" for e in validation_errors)
        return ctx.error(
            f"Validation échouée. Raccourcis les champs trop longs "
            f"puis rappelle fill_template:\n{error_list}"
        )

    enjeux = EnjeuxBesoins.model_validate(enjeux_data)
    cv_model = CV.model_validate(cv_data)
    prestation = PrestationFinanciere.model_validate(prestation_data)

    # 2. Convert mastery levels to emojis
    cv_dict = cv_model.model_dump()
    for i in range(1, 4):
        for category in ["Langue", "Management", "Informatique", "GestionProjet"]:
            key = f"maitrise{category}{i}"
            cv_dict[key] = convert_maitrise_to_emoji(cv_dict.get(key, ""))

    # 3. Build template data
    template_data = {
        "enjeuxBesoins": enjeux.model_dump(),
        "cv": cv_dict,
        "prestationFinanciere": prestation.model_dump(),
    }

    # 4. Fetch PPTX template
    template_key = ctx.helpers.setting_text(
        "ppt.template_key", default="ppt_template.pptx"
    )
    resource = await ctx.read_resource(template_key)

    # 5. Fill the template (python-pptx needs file paths)
    template_path = None
    output_path = None
    try:
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=".pptx", prefix="ppt_template_"
        ) as tmp_in:
            tmp_in.write(resource.content_bytes)
            template_path = Path(tmp_in.name)

        with tempfile.NamedTemporaryFile(
            delete=False, suffix=".pptx", prefix="reference_filled_"
        ) as tmp_out:
            output_path = Path(tmp_out.name)

        fill_slide_from_structured_response(template_path, template_data, output_path)

        output_bytes = output_path.read_bytes()
    finally:
        if template_path:
            template_path.unlink(missing_ok=True)
        if output_path:
            output_path.unlink(missing_ok=True)

    # 6. Publish the filled PPTX
    timestamp = datetime.now().strftime("%m%d%H%M")
    final_name = f"Prop_commerciale_{timestamp}.pptx"

    artifact = await ctx.publish_bytes(
        file_name=final_name,
        content=output_bytes,
        content_type=PPTX_CONTENT_TYPE,
    )

    return ToolOutput(
        text="PowerPoint généré.",
        ui_parts=(artifact.to_link_part(),),
    )


# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------


class PptFillerReActV2Definition(ReActAgent):
    """V2 agent that extracts data from documents to fill PowerPoint templates."""

    agent_id: str = "ppt_filler.react.v2"
    role: str = "PowerPoint Template Filler"
    description: str = (
        "Extracts data from resumes and project documents to fill "
        "PowerPoint templates with structured information."
    )
    tags: tuple[str, ...] = ("document", "powerpoint", "extraction", "react")
    tools = (
        extract_enjeux_besoins,
        extract_cv,
        extract_prestation_financiere,
        fill_template,
    )
    system_prompt_template: str = Field(default=DEFAULT_SYSTEM_PROMPT, min_length=1)
    fields: tuple[FieldSpec, ...] = (
        FieldSpec(
            key="system_prompt_template",
            type="prompt",
            title="System Prompt",
            description="Instructions for the agent on how to extract and fill data.",
            required=True,
            default=DEFAULT_SYSTEM_PROMPT,
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="ppt.template_key",
            type="text",
            title="PowerPoint Template Key",
            description="Agent asset key for the .pptx template file.",
            default="ppt_template.pptx",
            ui=UIHints(group="PowerPoint"),
        ),
        FieldSpec(
            key="chat_options.attach_files",
            type="boolean",
            title="Allow file attachments",
            description="Show file upload/attachment controls for this agent.",
            default=True,
            ui=UIHints(group="Chat options"),
        ),
        FieldSpec(
            key="chat_options.libraries_selection",
            type="boolean",
            title="Document libraries picker",
            description="Let users select document libraries/knowledge sources for this agent.",
            default=True,
            ui=UIHints(group="Chat options"),
        ),
    )
