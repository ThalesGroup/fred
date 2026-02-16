"""Pydantic models for PPT Filler agent structured outputs.

Flattened structure to match PowerPoint template placeholders.
Used with `with_structured_output(Model, method=\"json_schema\")`.
"""

from pydantic import BaseModel, Field


# --- enjeuxBesoinsSchema ---


class EnjeuxBesoins(BaseModel):
    """Informations sur le contexte et les missions du projet."""

    contexte: str = Field(
        "",
        max_length=300,
        description="Contexte du projet.",
    )
    missions: str = Field(
        "",
        max_length=300,
        description="Ensemble des missions et objectifs.",
    )
    refCahierCharges: str = Field(
        "",
        description="Nom du fichier duquel les données sont extraites.",
    )


# --- cvSchema (flattened) ---


class CV(BaseModel):
    """Informations sur le CV de l'intervenant (structure plate)."""

    poste: str = Field("", description="L'intitulé du poste rempli par l'intervenant.")

    # Formations (max 3)
    dateFormation1: str = Field("", description="Date de la formation 1.")
    formation1: str = Field("", description="Nom de l'établissement ou formation 1.")
    dateFormation2: str = Field("", description="Date de la formation 2.")
    formation2: str = Field("", description="Nom de l'établissement ou formation 2.")
    dateFormation3: str = Field("", description="Date de la formation 3.")
    formation3: str = Field("", description="Nom de l'établissement ou formation 3.")

    # Langues (max 3)
    langue1: str = Field("", description="Langue parlée 1.")
    maitriseLangue1: int = Field(0, description="Maîtrise de la langue 1 (1-5).")
    langue2: str = Field("", description="Langue parlée 2.")
    maitriseLangue2: int = Field(0, description="Maîtrise de la langue 2 (1-5).")
    langue3: str = Field("", description="Langue parlée 3.")
    maitriseLangue3: int = Field(0, description="Maîtrise de la langue 3 (1-5).")

    # Compétences Management (max 3)
    competenceManagement1: str = Field("", description="Compétence management 1.")
    maitriseManagement1: int = Field(0, description="Maîtrise management 1 (1-5).")
    competenceManagement2: str = Field("", description="Compétence management 2.")
    maitriseManagement2: int = Field(0, description="Maîtrise management 2 (1-5).")
    competenceManagement3: str = Field("", description="Compétence management 3.")
    maitriseManagement3: int = Field(0, description="Maîtrise management 3 (1-5).")

    # Compétences Informatique (max 3)
    competenceInformatique1: str = Field("", description="Compétence informatique 1.")
    maitriseInformatique1: int = Field(0, description="Maîtrise informatique 1 (1-5).")
    competenceInformatique2: str = Field("", description="Compétence informatique 2.")
    maitriseInformatique2: int = Field(0, description="Maîtrise informatique 2 (1-5).")
    competenceInformatique3: str = Field("", description="Compétence informatique 3.")
    maitriseInformatique3: int = Field(0, description="Maîtrise informatique 3 (1-5).")

    # Compétences Gestion de Projet (max 3)
    competenceGestionProjet1: str = Field("", description="Compétence gestion de projet 1.")
    maitriseGestionProjet1: int = Field(0, description="Maîtrise gestion projet 1 (1-5).")
    competenceGestionProjet2: str = Field("", description="Compétence gestion de projet 2.")
    maitriseGestionProjet2: int = Field(0, description="Maîtrise gestion projet 2 (1-5).")
    competenceGestionProjet3: str = Field("", description="Compétence gestion de projet 3.")
    maitriseGestionProjet3: int = Field(0, description="Maîtrise gestion projet 3 (1-5).")

    # Expériences (max 3)
    entreprise1: str = Field("", description="Nom de l'entreprise 1.")
    poste1: str = Field("", description="Nom du poste 1.")
    duree1: str = Field("", description="Durée de l'expérience 1.")
    realisations1: str = Field("", description="Description des tâches réalisées 1.")
    entreprise2: str = Field("", description="Nom de l'entreprise 2.")
    poste2: str = Field("", description="Nom du poste 2.")
    duree2: str = Field("", description="Durée de l'expérience 2.")
    realisations2: str = Field("", description="Description des tâches réalisées 2.")
    entreprise3: str = Field("", description="Nom de l'entreprise 3.")
    poste3: str = Field("", description="Nom du poste 3.")
    duree3: str = Field("", description="Durée de l'expérience 3.")
    realisations3: str = Field("", description="Description des tâches réalisées 3.")


# --- prestationFinanciereSchema (flattened) ---


class PrestationFinanciere(BaseModel):
    """Informations sur les prestations financières facturées au client (structure plate)."""

    prestation1: str = Field("", description="Nom de la prestation 1.")
    prix1: int = Field(0, description="Prix unitaire de la prestation 1.")
    charge1: int = Field(0, description="Charge estimée de la prestation 1 en unités d'oeuvre.")
    prixTotalPrestation1: int = Field(0, description="Coût total de la prestation 1.")

    prestation2: str = Field("", description="Nom de la prestation 2.")
    prix2: int = Field(0, description="Prix unitaire de la prestation 2.")
    charge2: int = Field(0, description="Charge estimée de la prestation 2 en unités d'oeuvre.")
    prixTotalPrestation2: int = Field(0, description="Coût total de la prestation 2.")

    prestation3: str = Field("", description="Nom de la prestation 3.")
    prix3: int = Field(0, description="Prix unitaire de la prestation 3.")
    charge3: int = Field(0, description="Charge estimée de la prestation 3 en unités d'oeuvre.")
    prixTotalPrestation3: int = Field(0, description="Coût total de la prestation 3.")

    prestation4: str = Field("", description="Nom de la prestation 4.")
    prix4: int = Field(0, description="Prix unitaire de la prestation 4.")
    charge4: int = Field(0, description="Charge estimée de la prestation 4 en unités d'oeuvre.")
    prixTotalPrestation4: int = Field(0, description="Coût total de la prestation 4.")

    prestation5: str = Field("", description="Nom de la prestation 5.")
    prix5: int = Field(0, description="Prix unitaire de la prestation 5.")
    charge5: int = Field(0, description="Charge estimée de la prestation 5 en unités d'oeuvre.")
    prixTotalPrestation5: int = Field(0, description="Coût total de la prestation 5.")

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
