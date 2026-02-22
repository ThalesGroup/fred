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

from typing import Optional

_MERMAID_POLICY_EN = (
    "\n\n"
    "Mermaid diagram output policy:\n"
    "- If you generate Mermaid, use `<br/>` for line breaks inside labels (never `\\n`).\n"
    '- Prefer quoted labels like `["..."]`.\n'
    '- Prefer simple rectangular nodes (e.g., `A["..."]`) for compatibility, especially with multiline labels.\n'
    "- Use simple ASCII in Mermaid source when possible (`-`, `'`, `...`) and avoid typographic punctuation that may break parsers.\n"
    "- Keep node IDs simple (`A`, `node_api`, `kf_backend`) without spaces or special characters.\n"
    "- For edge labels, also use `<br/>` instead of `\\n`.\n"
    "- Return valid Mermaid syntax in a fenced ```mermaid``` block.\n"
    "- If the user asks mainly for a diagram, return one Mermaid block first, then optional short explanation after the block.\n"
    "- Prefer simpler flowchart syntax (rectangular nodes) when unsure.\n"
)

_MERMAID_POLICY_FR = (
    "\n\n"
    "Politique de rendu Mermaid:\n"
    "- Si tu génères du Mermaid, utilise `<br/>` pour les retours à la ligne dans les labels (jamais `\\n`).\n"
    '- Privilégie des labels quotés comme `["..."]`.\n'
    '- Privilégie des nœuds rectangulaires simples (ex: `A["..."]`) pour la compatibilité, surtout avec des labels multilignes.\n'
    "- Utilise si possible des caractères ASCII simples dans le source Mermaid (`-`, `'`, `...`) et évite la ponctuation typographique qui peut casser le parseur.\n"
    "- Garde des identifiants de nœuds simples (`A`, `node_api`, `kf_backend`) sans espaces ni caractères spéciaux.\n"
    "- Pour les labels de liens, utilise aussi `<br/>` au lieu de `\\n`.\n"
    "- Retourne une syntaxe Mermaid valide dans un bloc ```mermaid```.\n"
    "- Si la demande porte surtout sur un diagramme, retourne d'abord un bloc Mermaid unique, puis une courte explication optionnelle après le bloc.\n"
    "- En cas de doute, préfère une syntaxe `flowchart` simple (nœuds rectangulaires).\n"
)


def _normalize_lang(language: Optional[str]) -> str:
    value = (language or "").strip().lower()
    if value.startswith("fr"):
        return "fr"
    if value.startswith("en"):
        return "en"
    return "en"


def mermaid_rendering_policy(language: Optional[str] = None) -> str:
    """Return Mermaid authoring guidance in the user's language (fr/en)."""
    return (
        _MERMAID_POLICY_FR if _normalize_lang(language) == "fr" else _MERMAID_POLICY_EN
    )


def append_mermaid_rendering_policy(
    system_text: str, *, language: Optional[str] = None
) -> str:
    """
    Append a compact Mermaid policy to a system prompt.

    Kept intentionally small to avoid prompt bloat while improving renderability.
    """
    base = (system_text or "").strip()
    return f"{base}{mermaid_rendering_policy(language)}".strip()
