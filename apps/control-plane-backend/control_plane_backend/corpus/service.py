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
Team-scoped corpus creation (docs/swift/rfc/INDEXED-CORPUS-RFC.md §2/§4/§6).

The one place a `Corpus` instance gets created — `CorpusStore.create` itself
enforces nothing, by design (RFC §4: cross-checking against a `CorpusType`
is a service-layer concern, not either pure data model's).
"""

from __future__ import annotations

import uuid

from fred_core.common import TeamId
from fred_core.security.rebac.corpus_type_authz import can_team_use_corpus_type
from fred_core.security.rebac.rebac_engine import RebacEngine
from fred_sdk.contracts.corpus import Corpus, CorpusScope

from control_plane_backend.corpus.store import CorpusStore
from control_plane_backend.corpus_types.catalog import CorpusTypeCatalogSource


class CorpusTypeNotFound(Exception):
    """A `corpus_type_id` this deployment does not register, or has parked (`enabled: false`)."""

    http_status = 404


class CorpusTypeAccessDenied(Exception):
    """A team without `can_use` on the corpus type (RFC §6) — `fred_core.security.models.AuthorizationError`
    is a user-subject exception; this check's subject is the team, same reasoning as
    `routing_policy/service.py`'s own `ProfileNotUsableError` for `can_team_use_capability`."""

    http_status = 403


async def create_corpus(
    *,
    rebac: RebacEngine,
    store: CorpusStore,
    catalog_source: CorpusTypeCatalogSource,
    team_id: TeamId,
    corpus_type_id: str,
    name: str,
    tag_ids: list[str],
    connector_ref: str | None,
) -> Corpus:
    """Create one team-scoped corpus instance.

    Fails closed on two independent checks, in order: the corpus type must
    be registered and enabled in this deployment (`CorpusTypeNotFound`), then
    the team must hold `can_use` on it (`CorpusTypeAccessDenied`, RFC §6).
    """

    catalog = catalog_source.load()
    if not any(item.corpus_type_id == corpus_type_id for item in catalog.items):
        raise CorpusTypeNotFound(corpus_type_id)

    if not await can_team_use_corpus_type(
        rebac, str(team_id), corpus_type_id=corpus_type_id
    ):
        raise CorpusTypeAccessDenied(
            f"Team {team_id} may not use corpus type {corpus_type_id!r}"
        )

    corpus = Corpus(
        corpus_id=str(uuid.uuid4()),
        name=name,
        corpus_type_id=corpus_type_id,
        scope=CorpusScope(team_id=str(team_id), tag_ids=tag_ids),
        connector_ref=connector_ref,
    )
    return await store.create(corpus)
