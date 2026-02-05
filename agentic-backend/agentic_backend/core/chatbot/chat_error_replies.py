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

from __future__ import annotations

from agentic_backend.common.mcp_utils import MCPConnectionError
from agentic_backend.core.agents.runtime_context import RuntimeContext


def _is_french(runtime_context: RuntimeContext | None) -> bool:
    if runtime_context is None:
        return False
    lang = runtime_context.language or ""
    return lang.lower().startswith("fr")


def human_error_message(runtime_context: RuntimeContext | None, err: Exception) -> str:
    """
    Sometimes the backend must send error messages to the user. This function provides
    an easy way to centralize and localize those messages and return french or english
    versions based on the runtime context. Although logs are in english, user-facing
    messages can be localized here.

    Args:
        runtime_context: current runtime context (for language preference).
        err: the raised exception.

    Returns:
        Localized, human-friendly message including the original error text.
    """
    french = _is_french(runtime_context)
    err_text = str(err) if err else ""
    lower = err_text.lower()

    if isinstance(err, MCPConnectionError):
        return (
            "L'agent ne peut pas démarrer : un serveur MCP requis est inaccessible. "
            f"Détail : {err_text}"
            if french
            else "The agent cannot start because a required MCP server is unreachable. "
            f"Detail: {err_text}"
        )

    if "timeout" in lower or "timed out" in lower:
        return (
            "L'opération a dépassé le délai. Réduisez la portée ou le nombre de documents. "
            f"Détail : {err_text}"
            if french
            else "The operation timed out. Try reducing scope or documents. "
            f"Detail: {err_text}"
        )

    if "context length" in lower or "context window" in lower:
        return (
            "La requête dépasse la limite de contexte du modèle. Essayez avec des documents plus courts ou moins de pièces jointes. "
            f"Détail : {err_text}"
            if french
            else "The request exceeded the model's context limit. Try shorter documents or fewer attachments. "
            f"Detail: {err_text}"
        )

    if "rate limit" in lower:
        return (
            f"Trop de requêtes en cours. Patientez puis réessayez. Détail : {err_text}"
            if french
            else "Too many requests right now. Please wait and try again. "
            f"Detail: {err_text}"
        )

    return (
        "Une erreur inattendue est survenue. Merci de réessayer plus tard. "
        f"Détail : {err_text}"
        if french
        else "The agent encountered an error and cannot continue. Please try again later. "
        f"Detail: {err_text}"
    )
