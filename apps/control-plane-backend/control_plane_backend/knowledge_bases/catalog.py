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
Knowledge Base definitions an operator installs into this deployment.

There is no runtime registration: a definition exists because it is configured
here. Being configured means the Platform Admin can see it and enable it for a
team — never that a pod exists or a worker is connected.
"""

from __future__ import annotations

import re

from fred_sdk.knowledge_base import KnowledgeBaseManifest
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

_UNSAFE_VALUE_RE = re.compile(r"""[\s"'\\<>`{}|^]""")


def _reject_unsafe(value: str, field: str) -> str:
    if _UNSAFE_VALUE_RE.search(value):
        raise ValueError(f"{field} must not contain whitespace or quoting characters")
    return value


class KnowledgeBaseDefinitionConfig(BaseModel):
    """One configured Knowledge Base definition.

    `manifest` is the artifact the SDK author produced, installed verbatim.
    The two fields beside it are deployment bindings the author never chooses.
    """

    model_config = ConfigDict(extra="forbid")

    manifest: KnowledgeBaseManifest
    client_id: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description=(
            "Exact confidential M2M client this definition's application "
            "authenticates as. Every runtime call is checked against it, so a "
            "client bound elsewhere cannot read this definition's instances."
        ),
    )
    task_queue: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description=(
            "Internal execution routing for this definition's runs. Never "
            "surfaced to an SDK author or to a Fred user."
        ),
    )

    @property
    def definition_id(self) -> str:
        return self.manifest.id

    @field_validator("client_id", "task_queue")
    @classmethod
    def _safe_binding(cls, value: str, info: ValidationInfo) -> str:
        return _reject_unsafe(value, str(info.field_name))
