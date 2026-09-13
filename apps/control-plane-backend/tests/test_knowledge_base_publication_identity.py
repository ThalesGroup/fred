# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0

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
async def test_a_prefix_claimed_before_subjects_were_recorded_is_healed(tmp_path):
    """A row predating the column gets its subject on the next publication.

    Nothing backfills it, because only a publication carries the account.
    """
    store = await _store(tmp_path)
    await store.upsert(
        prefix=PREFIX, declaration=_declaration(), client_id=CLIENT, subject=SUBJECT
    )
    async with store._sessions() as session:  # noqa: SLF001 - simulating an old row
        async with session.begin():
            from control_plane_backend.models.knowledge_base_models import (
                KnowledgeBasePrefixRow,
            )

            claim = await session.get(KnowledgeBasePrefixRow, PREFIX)
            assert claim is not None
            claim.subject = None

    await store.upsert(
        prefix=PREFIX, declaration=_declaration(), client_id=CLIENT, subject=SUBJECT
    )

    stored = await store.get(DEFINITION)
    assert stored is not None and stored.subject == SUBJECT
