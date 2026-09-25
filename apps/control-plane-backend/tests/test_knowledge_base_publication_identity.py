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


"""What a publication records about the identity that made it.

A prefix is bound to a **client** — `azp` — and that is what a later
publication is checked against. A grant names an **account** — `sub` — because
a relation's subject is never a client. Both arrive on the one token that
authorizes a publication, so both are recorded then: creating a synchronized
folder later needs the second, and asking Keycloak's admin API which account
backs a client would be a dependency bought for nothing.

Against SQLite, through the real store.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from control_plane_backend.knowledge_bases.store import (
    KnowledgeBaseDefinitionStore,
    KnowledgeBasePrefixConflict,
)
from control_plane_backend.models.base import Base
from fred_sdk.knowledge_base import KnowledgeBaseDeclaration
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

PREFIX = "acme.kb"
DEFINITION = "acme.kb.http-markdown"
CLIENT = "kb-acme"
SUBJECT = "service-account-kb-acme"


async def _store(tmp_path: Path) -> KnowledgeBaseDefinitionStore:
    engine: AsyncEngine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'kb.db'}"
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return KnowledgeBaseDefinitionStore(engine)


def _declaration(version: str = "1.0.0") -> KnowledgeBaseDeclaration:
    return KnowledgeBaseDeclaration.model_validate(
        {
            "id": DEFINITION,
            "version": version,
            "name": "HTTP Markdown",
            "description": "Synchronize Markdown documents",
            "configuration_fields": [],
        }
    )


@pytest.mark.asyncio
async def test_a_publication_records_the_client_and_the_account_behind_it(tmp_path):
    store = await _store(tmp_path)

    published = await store.upsert(
        prefix=PREFIX, declaration=_declaration(), client_id=CLIENT, subject=SUBJECT
    )

    assert (published.client_id, published.subject) == (CLIENT, SUBJECT)
    stored = await store.get(DEFINITION)
    assert stored is not None
    assert (stored.client_id, stored.subject) == (CLIENT, SUBJECT)


@pytest.mark.asyncio
async def test_replaying_a_publication_leaves_both_identities_unchanged(tmp_path):
    """Every deployment of the image replays the publication."""
    store = await _store(tmp_path)
    await store.upsert(
        prefix=PREFIX, declaration=_declaration(), client_id=CLIENT, subject=SUBJECT
    )

    await store.upsert(
        prefix=PREFIX,
        declaration=_declaration(version="2.0.0"),
        client_id=CLIENT,
        subject=SUBJECT,
    )

    stored = await store.get(DEFINITION)
    assert stored is not None
    assert (stored.client_id, stored.subject) == (CLIENT, SUBJECT)
    assert stored.version == "2.0.0"


def _named(name: str) -> KnowledgeBaseDeclaration:
    return KnowledgeBaseDeclaration.model_validate(
        {
            "id": name,
            "version": "1.0.0",
            "name": "Squatted",
            "description": "Published under somebody else's prefix",
            "configuration_fields": [],
        }
    )


@pytest.mark.asyncio
async def test_no_client_may_claim_a_prefix_inside_another_clients(tmp_path):
    """Owning `acme.kb` has to mean owning everything under it.

    Checking the exact key alone would protect only names already published: a
    second client could claim `acme.kb.payroll` and publish inside it.
    """
    store = await _store(tmp_path)
    await store.upsert(
        prefix=PREFIX, declaration=_declaration(), client_id=CLIENT, subject=SUBJECT
    )

    with pytest.raises(KnowledgeBasePrefixConflict):
        await store.upsert(
            prefix=f"{PREFIX}.payroll",
            declaration=_named(f"{PREFIX}.payroll.hr"),
            client_id="kb-intruder",
            subject="service-account-intruder",
        )

    assert await store.get(f"{PREFIX}.payroll.hr") is None


@pytest.mark.asyncio
async def test_no_client_may_claim_a_prefix_above_another_clients(tmp_path):
    """The other direction of the same violation.

    A prefix that sits above an existing claim swallows it, so `acme` over
    `acme.kb` is refused exactly as `acme.kb.payroll` under it is.
    """
    store = await _store(tmp_path)
    await store.upsert(
        prefix=PREFIX, declaration=_declaration(), client_id=CLIENT, subject=SUBJECT
    )

    with pytest.raises(KnowledgeBasePrefixConflict):
        await store.upsert(
            prefix="acme",
            declaration=_named("acme.finance"),
            client_id="kb-other",
            subject="service-account-other",
        )

    assert await store.get("acme.finance") is None


@pytest.mark.asyncio
async def test_a_neighbouring_prefix_is_not_an_overlap(tmp_path):
    """A segment boundary is required, so `acme.kbx` is nobody's business."""
    store = await _store(tmp_path)
    await store.upsert(
        prefix=PREFIX, declaration=_declaration(), client_id=CLIENT, subject=SUBJECT
    )

    published = await store.upsert(
        prefix="acme.kbx",
        declaration=_named("acme.kbx.triage"),
        client_id="kb-neighbour",
        subject="service-account-neighbour",
    )

    assert published.client_id == "kb-neighbour"


@pytest.mark.asyncio
async def test_another_client_is_still_refused_the_prefix(tmp_path):
    store = await _store(tmp_path)
    await store.upsert(
        prefix=PREFIX, declaration=_declaration(), client_id=CLIENT, subject=SUBJECT
    )

    with pytest.raises(KnowledgeBasePrefixConflict):
        await store.upsert(
            prefix=PREFIX,
            declaration=_declaration(),
            client_id="kb-intruder",
            subject="service-account-intruder",
        )

    stored = await store.get(DEFINITION)
    assert stored is not None
    assert (stored.client_id, stored.subject) == (CLIENT, SUBJECT)


@pytest.mark.asyncio
async def test_listing_carries_both_identities(tmp_path):
    """The grant a synchronized folder makes reads the subject from here."""
    store = await _store(tmp_path)
    await store.upsert(
        prefix=PREFIX, declaration=_declaration(), client_id=CLIENT, subject=SUBJECT
    )

    listed = await store.list_all()

    assert [(d.id, d.client_id, d.subject) for d in listed] == [
        (DEFINITION, CLIENT, SUBJECT)
    ]


@pytest.mark.asyncio
async def test_a_rotated_service_account_is_recorded_by_the_next_publication(tmp_path):
    """The prefix is the client's, so recreating its account keeps it.

    Only a publication carries the account, and the one it carries is what a
    grant made from then on will name.
    """
    store = await _store(tmp_path)
    await store.upsert(
        prefix=PREFIX,
        declaration=_declaration(),
        client_id=CLIENT,
        subject="service-account-kb-acme-before-rotation",
    )

    await store.upsert(
        prefix=PREFIX, declaration=_declaration(), client_id=CLIENT, subject=SUBJECT
    )

    stored = await store.get(DEFINITION)
    assert stored is not None and stored.subject == SUBJECT
