"""Pydantic models for Bid Manager agent structured outputs."""

from pydantic import BaseModel, Field

# --- Base items ---


class Requirement(BaseModel):
    """An extracted requirement from the tender."""

    title: str = Field(description="Titre court de l'exigence")
    description: str = Field(description="Description détaillée de l'exigence")


class EvaluationCriterion(BaseModel):
    """An evaluation criterion from the RC."""

    name: str = Field(description="Nom du critère")
    weight: str | None = Field(
        default=None, description="Pondération (ex: '60%') si mentionnée"
    )
    description: str = Field(description="Description du critère d'évaluation")


class Constraint(BaseModel):
    """A major constraint identified in the tender."""

    title: str = Field(description="Titre de la contrainte")
    description: str = Field(description="Description détaillée")


class Deliverable(BaseModel):
    """A deliverable expected in the bid response."""

    title: str = Field(description="Titre du livrable attendu")
    description: str = Field(description="Description et contenu attendu")


class KeyContractualClause(BaseModel):
    """A key contractual clause extracted from the tender."""

    category: str = Field(
        description=(
            "Catégorie parmi : 'Pénalités', 'SLA/SLO', "
            "'Propriété intellectuelle / Souveraineté', "
            "'Réversibilité', 'Obligation (moyens/résultat)'"
        )
    )
    title: str = Field(description="Titre court de la clause")
    description: str = Field(description="Contenu détaillé et impact contractuel")
    criticality: str | None = Field(
        default=None,
        description="Criticité si notable : 'Élevée', 'Moyenne', 'Faible'",
    )


# --- Tool result wrappers for structured LLM output ---


class SyntheseResult(BaseModel):
    """Synthèse du dossier : métadonnées structurées + trois sections narratives."""

    tender_title: str = Field(description="Titre de l'appel d'offres")
    client: str = Field(description="Entité acheteuse / pouvoir adjudicateur")
    tender_type: str | None = Field(
        default=None,
        description="Type d'AO : RFP, RFI, RFQ, Appel d'offres ouvert, MAPA, Accord-cadre...",
    )
    economic_model: str | None = Field(
        default=None,
        description=(
            "Modèle économique du contrat : FFP (forfait), T&M (régie), "
            "BPU/DQE (prix unitaires), Cost+, Accord-cadre, hybride — null si non précisé"
        ),
    )
    scope: str = Field(description="Périmètre et objet du marché")
    submission_deadline: str | None = Field(
        default=None, description="Date limite de soumission"
    )
    contract_duration: str | None = Field(default=None, description="Durée du marché")
    procedure_type: str | None = Field(default=None, description="Type de procédure")
    allotissement: str | None = Field(
        default=None, description="Découpe en lots si applicable"
    )
    key_structuring_elements: list[str] = Field(
        default_factory=list,
        description="Éléments structurants et importants du cahier des charges (max 8)",
    )
    executive_overview: str = Field(
        description="Synthèse exécutive narrative — 8 à 10 lignes sur l'objet, le périmètre et les enjeux du marché"
    )
    client_presentation: str = Field(
        description="Présentation du client : secteur d'activité, missions, contexte organisationnel"
    )
    project_context: str = Field(
        description="Contexte du projet : situation actuelle, problèmes à résoudre, type de solutions attendues"
    )


class AttentesResult(BaseModel):
    """Attentes et réponses : requirements (all categories) + evaluation criteria + key contractual clauses."""

    technical_requirements: list[Requirement]
    organizational_requirements: list[Requirement]
    administrative_requirements: list[Requirement]
    evaluation_criteria: list[EvaluationCriterion]
    key_contractual_clauses: list[KeyContractualClause]


class RiskWithPriority(BaseModel):
    """A CCTP risk with P0–P3 priority level."""

    title: str = Field(description="Titre court du risque")
    priority: str = Field(
        description="Priorité : 'P0' (bloquant), 'P1' (élevé), 'P2' (moyen), 'P3' (faible/vigilance)"
    )
    description: str = Field(description="Description détaillée du risque")
    mitigation: str | None = Field(
        default=None, description="Piste de mitigation si pertinente"
    )


class RiskAnalysisResult(BaseModel):
    """Analyse de risques CCTP : ~20 prioritized risks + constraints + deliverables."""

    risks: list[RiskWithPriority]
    constraints: list[Constraint]
    deliverables: list[Deliverable]
