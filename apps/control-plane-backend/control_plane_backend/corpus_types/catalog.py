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

"""Registration of the corpus types a Fred deployment offers.

A corpus type is contributed by a developer (docs/swift/rfc/INDEXED-CORPUS-RFC.md
§2/§6) and enabled per team by a platform admin — it is not created through a
product API. Registration is therefore deployment configuration, mirroring
`ApplicationSourceConfig` (`control_plane_backend/applications/catalog.py`)
exactly: same reasoning, same shape, same `CatalogSource` protocol so a
durable/dynamic source can later replace the configured one without changing
callers.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from fred_sdk.contracts.corpus import CorpusType
from pydantic import BaseModel, ConfigDict


class CorpusTypeConfig(CorpusType):
    """A `CorpusType` registered as deployment configuration.

    Adds only `enabled` to the underlying contract — `False` parks a type
    without removing its registration, same convention as
    `ApplicationSourceConfig.enabled`.
    """

    enabled: bool = True


class CorpusTypeCatalog(BaseModel):
    """Corpus types registered in this deployment."""

    model_config = ConfigDict(extra="forbid")

    items: list[CorpusTypeConfig]


class CorpusTypeCatalogSource(Protocol):
    """Source boundary for registered-corpus-type state."""

    def load(self) -> CorpusTypeCatalog: ...


def registered_corpus_types(
    sources: Sequence[CorpusTypeConfig],
) -> list[CorpusTypeConfig]:
    """Enabled entries only: `enabled: false` parks a type without deleting it."""

    return [source for source in sources if source.enabled]


@dataclass(frozen=True)
class ConfiguredCorpusTypeCatalogSource:
    """Read the corpus types an operator registered in platform configuration."""

    sources: tuple[CorpusTypeConfig, ...] = ()

    def load(self) -> CorpusTypeCatalog:
        return CorpusTypeCatalog(items=registered_corpus_types(self.sources))
