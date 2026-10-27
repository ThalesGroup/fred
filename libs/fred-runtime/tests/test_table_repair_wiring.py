# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""The local corpus path verifies table expansion without retaining a SQL connection."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, cast
from uuid import UUID, uuid5

import pytest
from fred_capability_document_access import search as search_module
from fred_core.common import (
    ModelConfiguration,
    OpenSearchIndexConfig,
    OpenSearchStoreConfig,
)
from sqlalchemy.ext.asyncio import AsyncEngine

SPACE = UUID("00000000-0000-0000-0000-000000000001")
DOCUMENT = UUID("00000000-0000-0000-0000-000000000002")
GENERATION = UUID("00000000-0000-0000-0000-000000000003")
HEADER = "| name | default |\n| --- | --- |"


class _Rows:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def mappings(self) -> _Rows:
        return self

    def first(self) -> dict[str, Any]:
        return self.rows[0]

    def all(self) -> list[dict[str, Any]]:
        return self.rows


class _Engine:
    def __init__(self) -> None:
        self.active = False
        self.verifications = 0

    @asynccontextmanager
    async def connect(self):
        self.active = True
        try:
            yield self
        finally:
            self.active = False

    async def execute(self, statement: object, params: dict[str, Any]) -> _Rows:
        if "space_id" in params:
            return _Rows(
                [
                    {
                        "id": SPACE,
                        "parent_id": None,
                        "organization_id": None,
                        "deletion_id": None,
                    }
                ]
            )
        self.verifications += 1
        return _Rows(
            [
                {
                    "id": DOCUMENT,
                    "space_id": SPACE,
                    "deletion_id": None,
                    "space_deletion_id": None,
                    "retrievable": True,
                    "retrievable_pending": False,
                    "manifest": {
                        "generation": str(GENERATION),
                        "vector_ordinals": [0, 1, 2],
                    },
                }
            ]
        )


def _raw_hit(ordinal: int) -> dict[str, Any]:
    return {
        "_id": str(uuid5(GENERATION, str(ordinal))),
        "_score": 0.9,
        "_source": {
            "text": f"{HEADER}\n| {chr(97 + ordinal)} | {ordinal} |",
            "metadata": {"document_uid": str(DOCUMENT), "chunk_index": ordinal},
        },
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_expansion", [False, True])
async def test_document_search_port_repairs_table_hits(
    monkeypatch: pytest.MonkeyPatch, fail_expansion: bool
) -> None:
    engine = _Engine()
    calls: list[dict[str, Any]] = []

    class _Embeddings:
        async def aembed_query(self, query: str) -> list[float]:
            assert not engine.active
            return [0.1]

    class _Client:
        async def search(self, **kwargs: Any) -> dict[str, Any]:
            assert not engine.active
            calls.append(kwargs)
            if len(calls) == 2 and fail_expansion:
                raise TimeoutError("expansion unavailable")
            # Ordinal 3 is indexed but unpublished, so SQL must drop it.
            ordinals = [0, 2] if len(calls) == 1 else [0, 1, 2, 3]
            return {"hits": {"hits": [_raw_hit(i) for i in ordinals]}}

        async def close(self) -> None:
            pass

    monkeypatch.setattr(search_module, "get_embeddings", lambda _: _Embeddings())
    monkeypatch.setattr(search_module, "AsyncOpenSearch", lambda **_: _Client())
    search = search_module.CorpusSearch(
        engine=cast(AsyncEngine, engine),
        opensearch=OpenSearchStoreConfig(
            host="https://search.invalid",
            username="fixture",
            password="fixture",  # pragma: allowlist secret - offline fixture
        ),  # nosec B106
        index=OpenSearchIndexConfig(type="opensearch", index="fixture-vectors"),
        embedding=ModelConfiguration(provider="openai", name="fixture-embedding"),
        timeout=1,
    )
    try:
        if fail_expansion:
            with pytest.raises(TimeoutError):
                await search.search(
                    "defaults?",
                    space_id=SPACE,
                    top_k=2,
                    policy="semantic",
                    check_active=lambda: None,
                )
        else:
            result = await search.search(
                "defaults?",
                space_id=SPACE,
                top_k=2,
                policy="semantic",
                check_active=lambda: None,
            )
            assert [h.content for h in result.hits] == [
                f"{HEADER}\n| a | 0 |",
                "| b | 1 |",
                "| c | 2 |",
            ]
            assert engine.verifications == 2
        assert calls[1]["body"]["size"] == 40
        assert {"term": {"metadata.document_uid": str(DOCUMENT)}} in calls[1]["body"][
            "query"
        ]["bool"]["filter"]
    finally:
        await search.close()
