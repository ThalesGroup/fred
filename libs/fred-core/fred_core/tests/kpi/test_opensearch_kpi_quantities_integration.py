# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

"""Quantity aggregation on an explicitly supplied, disposable local OpenSearch."""

from __future__ import annotations

import copy
import os
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from fred_core.kpi.kpi_writer_structures import KPIEvent, Metric, Quantities
from fred_core.kpi.opensearch_kpi_store import KPI_INDEX_MAPPING, OpenSearchKPIStore

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("existing", [False, True], ids=["fresh", "additive"])
def test_turn_quantities_aggregate_without_reindexing_old_documents(
    existing: bool,
) -> None:
    url = os.environ.get("FRED_CORE_IT_OPENSEARCH")
    if not url:
        pytest.skip("set FRED_CORE_IT_OPENSEARCH to a disposable local OpenSearch")
    endpoint = urlsplit(url)
    assert endpoint.scheme == "http" and endpoint.hostname in {
        "localhost",
        "127.0.0.1",
        "::1",
    }
    assert endpoint.username is None and endpoint.password is None
    assert endpoint.path in {"", "/"} and not endpoint.query and not endpoint.fragment

    index = f"kpi-quantities-fixture-{uuid4().hex}"
    store = OpenSearchKPIStore(host=url, index=index)
    client = store.client
    try:
        if existing:
            old_mapping = copy.deepcopy(KPI_INDEX_MAPPING)
            old_mapping["settings"]["index.number_of_replicas"] = 0
            properties = old_mapping["mappings"]["properties"]["quantities"][
                "properties"
            ]
            for field in ("tool_count", "cache_read_tokens"):
                del properties[field]
            client.indices.create(index=index, body=old_mapping)
            client.index(
                index=index,
                id="before-mapping",
                body=KPIEvent(
                    metric=Metric(
                        name="agent.turn_completed", type="timer", value=1, unit="ms"
                    ),
                    quantities=Quantities(tool_count=7, cache_read_tokens=99),
                ).to_doc(),
            )
            client.indices.refresh(index=index)

        store.ensure_ready()
        for tools, cached in [(2, 784), (3, 800)]:
            store.index_event(
                KPIEvent(
                    metric=Metric(
                        name="agent.turn_completed", type="timer", value=1, unit="ms"
                    ),
                    quantities=Quantities(tool_count=tools, cache_read_tokens=cached),
                )
            )
        client.indices.refresh(index=index)
        response = client.search(
            index=index,
            body={
                "size": 0,
                "track_total_hits": True,
                "aggs": {
                    "tools": {"sum": {"field": "quantities.tool_count"}},
                    "cached": {"sum": {"field": "quantities.cache_read_tokens"}},
                },
            },
        )
        assert response["timed_out"] is False
        assert response["_shards"]["failed"] == 0
        assert response["hits"]["total"] == {
            "value": 3 if existing else 2,
            "relation": "eq",
        }
        assert response["aggregations"]["tools"]["value"] == 5
        assert response["aggregations"]["cached"]["value"] == 1584
        if existing:
            old_source = client.get(index=index, id="before-mapping")["_source"]
            assert old_source["quantities"] == {
                "tool_count": 7,
                "cache_read_tokens": 99,
            }
    finally:
        try:
            client.indices.delete(index=index, ignore=[404])
        finally:
            client.close()
