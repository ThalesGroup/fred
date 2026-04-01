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

"""Pydantic models for Reference Editor agent structured outputs.

These models are the single source of truth for the reference document schema.
The JSON schema used by tools and validation is derived from these models.
"""

from pydantic import BaseModel, Field


class InformationsProjet(BaseModel):
    """Informations sur le projet."""

    nomSociete: str = Field(
        "",
        max_length=50,
        description="Le nom de la société",
    )
    nomProjet: str = Field(
        "",
        max_length=50,
        description="Le nom du projet",
    )
    dateProjet: str = Field(
        "",
        description="La date de début et de fin du projet",
    )
    nombrePersonnes: str = Field(
        "",
        description="Le nombre de personnes dans la direction (uniquement dans la direction)",
    )
    enjeuFinancier: str = Field(
        "",
        max_length=100,
        description="Les coûts financiers ou la rentabilité du projet exprimé en euros, juste un seul chiffre clé comme le CA (jamais en nombre de personnes sinon ne rien mettre)",
    )


class Contexte(BaseModel):
    """Informations sur le contexte et le client."""

    presentationClient: str = Field(
        "",
        max_length=300,
        description="Courte présentation du client. Longueur maximale: 300 caractères (une à deux phrases).",
    )
    presentationContexte: str = Field(
        "",
        max_length=300,
        description="Courte présentation du contexte du projet. Longueur maximale: 300 caractères (une à deux phrases).",
    )
    listeTechnologies: str = Field(
        "",
        description="Listes des technologies utilisés lors de ce projet",
    )


class SyntheseProjet(BaseModel):
    """Synthèse structurée du projet."""

    enjeux: str = Field(
        "",
        max_length=300,
        description="Court résumé des enjeux du projet. Longueur maximale: 300 caractères (une à deux phrases).",
    )
    activiteSolutions: str = Field(
        "",
        max_length=300,
        description="Court résumé des activités et solutions du projet. Longueur maximale: 300 caractères (une à deux phrases).",
    )
    beneficeClients: str = Field(
        "",
        description="Court résumé des bénéfices pour le client. Longueur maximale: 300 caractères (une à deux phrases).",
    )
    pointsForts: str = Field(
        "",
        description="Court résumé des points forts du projet. Longueur maximale: 300 caractères (une à deux phrases).",
    )
