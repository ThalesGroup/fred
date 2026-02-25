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

"""Validation tools for Reference Editor agent."""

import logging

from jsonschema import Draft7Validator
from langchain.tools import tool

from agentic_backend.agents.reference_editor.powerpoint_template_util import (
    referenceSchema,
)

logger = logging.getLogger(__name__)

EXPECTED_REFERENCE_SECTIONS = {"informationsProjet", "contexte", "syntheseProjet"}


def _normalize_reference_payload_for_validation(
    data: dict | None,
) -> tuple[dict | None, str | None]:
    """
    Accept both payload styles:
    - {"data": {...}}  (preferred, matches tool schema)
    - {...}            (legacy convenience)
    """
    if data is None:
        return (
            None,
            "Missing required argument: data. Call validator_tool(data={...}) with the structured payload.",
        )
    if not isinstance(data, dict):
        return None, "Invalid payload type. Expected a JSON object."

    payload = data.get("data", data)
    if not isinstance(payload, dict):
        return (
            None,
            "Invalid payload format. Expected `data` to be a JSON object.",
        )

    keys = set(payload.keys())
    if keys != EXPECTED_REFERENCE_SECTIONS:
        return (
            None,
            "Bad root key format. Expected sections are: "
            '{"informationsProjet": {...}, "contexte": {...}, "syntheseProjet": {...}} '
            "(inside `data` if wrapped).",
        )

    return payload, None


class ValidationTools:
    """Helper class to organize reference editor validation tools."""

    def __init__(self, agent):
        self.agent = agent

    def get_validator_tool(self):
        """Create the JSON schema validation tool."""

        @tool
        async def validator_tool(data: dict | None = None):
            """
            Outil permettant de valider le format des données avant de les passer à l'outil de templetisation.
            L'outil retourne [] si le schéma est valide et la liste des erreurs sinon.

            IMPORTANT : Si cet outil retourne [] (liste vide), tu DOIS IMMÉDIATEMENT appeler template_tool(data={{...}})
            avec exactement les mêmes données dans le MÊME tour de conversation. Ne t'arrête pas ici.
            """
            payload, error_message = _normalize_reference_payload_for_validation(data)
            if error_message:
                return error_message

            def shorten_error_message(error):
                """Convert verbose validation errors to concise messages."""
                field_path = ".".join(str(p) for p in error.path) or "root"
                if error.validator == "type":
                    return f"{field_path} type invalid. Expected {error.schema.get('type')}."
                if error.validator == "required":
                    return f"{field_path} missing required field."
                return f"{field_path} invalid. Reason: {error.validator}."

            validator = Draft7Validator(referenceSchema)
            errors = [
                shorten_error_message(e) for e in validator.iter_errors(payload)
            ]
            if not errors:
                return "✓ Validation réussie ! Appelle maintenant template_tool(data={...}) avec ces mêmes données."
            return errors

        return validator_tool
