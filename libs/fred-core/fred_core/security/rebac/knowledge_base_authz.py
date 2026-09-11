# Copyright Thales 2026
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

"""
Authorization helpers for configured Knowledge Base definitions.

The authorized object is the definition, and its type is distinct from
`capability` and `app` so neither of their grants can make a Knowledge Base
usable. Instances are not authorization objects: they are team-scoped rows
whose access follows their team.

This module covers the WRITE and DISPLAY side only: composing the catalog id
and naming the authorization object. Nothing here answers "may this team use
this definition?" — no caller asks yet, because instances do not exist. The
consumption helper belongs with whatever first needs it.
"""

from __future__ import annotations

import re

from fred_core.security.models import Resource
from fred_core.security.rebac.rebac_engine import (
    RebacReference,
)

KNOWLEDGE_BASE_CATALOG_NAMESPACE_PREFIX = "kb__"

__all__ = [
    "KNOWLEDGE_BASE_CATALOG_NAMESPACE_PREFIX",
    "knowledge_base_catalog_id",
    "knowledge_base_definition_ref",
    "knowledge_base_provider_and_definition",
]


def _id_safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "-", value)


def knowledge_base_catalog_id(provider_id: str, definition_id: str) -> str:
    """Return the collision-free id used by the shared administration catalog.

    Two segments, because a provider exposes several Knowledge Bases and two
    providers may each expose one of the same name. Mirrors
    `agent__<runtime_id>__<agent_id>` and `model__<provider>__<name>`: the
    provider names where it comes from, the second segment what it is.
    """

    return (
        f"{KNOWLEDGE_BASE_CATALOG_NAMESPACE_PREFIX}"
        f"{_id_safe(provider_id)}__{_id_safe(definition_id)}"
    )


def knowledge_base_provider_and_definition(catalog_id: str) -> tuple[str, str]:
    """Split an exact Knowledge Base catalog id into (provider, definition).

    Splits on the FIRST separator after the prefix, exactly as the model
    namespace does: a definition id may itself contain ``_``, a provider may
    not be empty.
    """

    if not catalog_id.startswith(KNOWLEDGE_BASE_CATALOG_NAMESPACE_PREFIX):
        raise ValueError(f"Not a Knowledge Base catalog id: {catalog_id!r}")
    rest = catalog_id[len(KNOWLEDGE_BASE_CATALOG_NAMESPACE_PREFIX) :]
    provider_id, separator, definition_id = rest.partition("__")
    if not separator or not provider_id or not definition_id:
        raise ValueError(
            "Knowledge Base catalog id must be "
            f"{KNOWLEDGE_BASE_CATALOG_NAMESPACE_PREFIX}<provider>__<definition>: "
            f"{catalog_id!r}"
        )
    return provider_id, definition_id


def knowledge_base_definition_ref(object_id: str) -> RebacReference:
    """Return the typed authorization reference for one definition object id.

    `object_id` is `<provider>__<definition>` — the catalog id minus its
    namespace prefix, the same relationship `app__<app_id>` has to `app:<id>`.
    """

    return RebacReference(type=Resource.KNOWLEDGE_BASE_DEFINITION, id=object_id)
