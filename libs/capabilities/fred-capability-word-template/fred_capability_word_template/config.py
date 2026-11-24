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

"""The template library configuration: the entries an admin uploads, and
the save path that stores each new template and reads its parts.
"""

from __future__ import annotations

import unicodedata
from typing import Annotated

from fred_sdk.contracts.capability import (
    AssetKey,
    ScopePrivate,
)
from pydantic import BaseModel, Field

from fred_capability_word_template.analysis import (
    TemplateAnalysis,
)

TEMPLATE_LIBRARY_SLOT = "word_template_library"


class WordTemplateEntry(BaseModel):
    """A CP-owned original; admission supplies its acknowledged analysis reference.

    The asset key permits a complete marketplace snapshot. The preparation
    reference is private to its source and cleared during copy validation.
    """

    template_key: Annotated[str | None, AssetKey(TEMPLATE_LIBRARY_SLOT)] = None
    label: str = ""
    filename: str | None = None
    parts_summary: str = ""
    analysis: TemplateAnalysis | None = None
    sha256: str | None = None
    analysis_reference: ScopePrivate[str | None] = None


class WordTemplateConfig(BaseModel):
    template_library: list[WordTemplateEntry] | None = Field(default=None, max_length=8)


def normalized(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(folded.lower().split())
