"""Pydantic models for PPT Filler agent structured outputs.

Flattened structure to match PowerPoint template placeholders.
max_length constraints define PPT card limits but are stripped for extraction
(so the LLM doesn't self-truncate). Validation happens at fill_template time.
"""

from typing import Type

from pydantic import BaseModel, Field, create_model


def schema_without_max_length(model_class: Type[BaseModel]) -> Type[BaseModel]:
    """Return a new Pydantic model with all max_length constraints removed.

    Used with `with_structured_output(schema, method="json_schema")` so the LLM
    extracts full content without truncating to fit PPT card limits.
    """
    fields = {}
    for name, field_info in model_class.model_fields.items():
        kwargs = {"default": field_info.default, "description": field_info.description}
        fields[name] = (field_info.annotation, Field(**kwargs))
    return create_model(model_class.__name__, **fields)


# --- enjeuxBesoinsSchema ---


class EnjeuxBesoins(BaseModel):
    """Informations sur le contexte et les missions du projet."""

    contexte: str = Field(
        "",
        max_length=270,
        description="Contexte du projet. Une à deux phrases.",
    )
    missions: str = Field(
        "",
        max_length=270,
        description="Ensemble des missions et objectifs. Une à deux phrases.",
    )
    refCahierCharges: str = Field(
        "",
        description="Nom du fichier duquel les données sont extraites.",
    )


# --- cvSchema ---


class CV(BaseModel):
    """Informations sur le CV de l'intervenant."""

    trigramme: str = Field(
        "",
        max_length=3,
        description="Trigramme servant à anonymiser le nom de l'intervenant (présent dans le CV).",
    )
    poste: str = Field(
        "", max_length=60, description="L'intitulé du poste rempli par l'intervenant."
    )

    # Formations (max 3)
    dateFormation1: str = Field("", description="Date de la formation 1.")
    formation1: str = Field("", description="Nom de l'établissement ou formation 1.")
    dateFormation2: str = Field("", description="Date de la formation 2.")
    formation2: str = Field("", description="Nom de l'établissement ou formation 2.")
    dateFormation3: str = Field("", description="Date de la formation 3.")
    formation3: str = Field("", description="Nom de l'établissement ou formation 3.")

    # Langues (max 1) - Exclude native language (e.g. French)
    langue1: str = Field(
        "", description="Langue parlée 1 (exclure la langue maternelle)."
    )
    maitriseLangue1: str = Field(
        "", description="Maîtrise de la langue 1 (1-5). Chaîne vide si pas de langue."
    )

    # Compétences Management (max 3)
    competenceManagement1: str = Field(
        "", max_length=30, description="Compétence management 1."
    )
    maitriseManagement1: str = Field(
        "", description="Maîtrise management 1 (1-5). Chaîne vide si pas de compétence."
    )
    competenceManagement2: str = Field(
        "", max_length=30, description="Compétence management 2."
    )
    maitriseManagement2: str = Field(
        "", description="Maîtrise management 2 (1-5). Chaîne vide si pas de compétence."
    )
    competenceManagement3: str = Field(
        "", max_length=30, description="Compétence management 3."
    )
    maitriseManagement3: str = Field(
        "", description="Maîtrise management 3 (1-5). Chaîne vide si pas de compétence."
    )

    # Compétences Informatique (max 3)
    competenceInformatique1: str = Field(
        "", max_length=30, description="Compétence informatique 1."
    )
    maitriseInformatique1: str = Field(
        "",
        description="Maîtrise informatique 1 (1-5). Chaîne vide si pas de compétence.",
    )
    competenceInformatique2: str = Field(
        "", max_length=30, description="Compétence informatique 2."
    )
    maitriseInformatique2: str = Field(
        "",
        description="Maîtrise informatique 2 (1-5). Chaîne vide si pas de compétence.",
    )
    competenceInformatique3: str = Field(
        "", max_length=30, description="Compétence informatique 3."
    )
    maitriseInformatique3: str = Field(
        "",
        description="Maîtrise informatique 3 (1-5). Chaîne vide si pas de compétence.",
    )

    # Compétences Gestion de Projet (max 3)
    competenceGestionProjet1: str = Field(
        "", max_length=30, description="Compétence gestion de projet 1."
    )
    maitriseGestionProjet1: str = Field(
        "",
        description="Maîtrise gestion projet 1 (1-5). Chaîne vide si pas de compétence.",
    )
    competenceGestionProjet2: str = Field(
        "", max_length=30, description="Compétence gestion de projet 2."
    )
    maitriseGestionProjet2: str = Field(
        "",
        description="Maîtrise gestion projet 2 (1-5). Chaîne vide si pas de compétence.",
    )
    competenceGestionProjet3: str = Field(
        "", max_length=30, description="Compétence gestion de projet 3."
    )
    maitriseGestionProjet3: str = Field(
        "",
        description="Maîtrise gestion projet 3 (1-5). Chaîne vide si pas de compétence.",
    )

    # Expériences (max 3)
    entreprise1: str = Field("", description="Nom de l'entreprise 1.")
    poste1: str = Field("", description="Nom du poste 1.")
    duree1: str = Field("", description="Durée de l'expérience 1.")
    realisations1: str = Field(
        "", max_length=600, description="Description des tâches réalisées 1."
    )
    entreprise2: str = Field("", description="Nom de l'entreprise 2.")
    poste2: str = Field("", description="Nom du poste 2.")
    duree2: str = Field("", description="Durée de l'expérience 2.")
    realisations2: str = Field(
        "", max_length=600, description="Description des tâches réalisées 2."
    )
    entreprise3: str = Field("", description="Nom de l'entreprise 3.")
    poste3: str = Field("", description="Nom du poste 3.")
    duree3: str = Field("", description="Durée de l'expérience 3.")
    realisations3: str = Field(
        "", max_length=600, description="Description des tâches réalisées 3."
    )


# --- prestationFinanciereSchema ---


class PrestationFinanciere(BaseModel):
    """Informations sur les prestations financières facturées au client.

    Ne remplir QUE les prestations pour lesquelles des données concrètes existent.
    Ne pas inventer de catégories avec un coût de 0.
    """

    prestation1: str = Field(
        "", description="Nom de la prestation 1. Vide si pas de données."
    )
    prix1: int = Field(0, description="Prix unitaire de la prestation 1.")
    charge1: int = Field(
        0, description="Charge estimée de la prestation 1 en unités d'oeuvre."
    )
    prixTotal1: int = Field(0, description="Coût total de la prestation 1.")

    prestation2: str = Field("", description="Nom de la prestation 2.")
    prix2: int = Field(0, description="Prix unitaire de la prestation 2.")
    charge2: int = Field(
        0, description="Charge estimée de la prestation 2 en unités d'oeuvre."
    )
    prixTotal2: int = Field(0, description="Coût total de la prestation 2.")

    prestation3: str = Field("", description="Nom de la prestation 3.")
    prix3: int = Field(0, description="Prix unitaire de la prestation 3.")
    charge3: int = Field(
        0, description="Charge estimée de la prestation 3 en unités d'oeuvre."
    )
    prixTotal3: int = Field(0, description="Coût total de la prestation 3.")

    prixTotal: int = Field(0, description="Coût total de toutes les prestations.")


# --- Utility model for schema-driven query generation ---


class SearchQueries(BaseModel):
    """Queries generated by the LLM to search for schema fields."""

    queries: list[str] = Field(
        ...,
        min_length=1,
        max_length=8,
        description="Search queries to find information for all schema fields. Group related fields into fewer queries.",
    )
