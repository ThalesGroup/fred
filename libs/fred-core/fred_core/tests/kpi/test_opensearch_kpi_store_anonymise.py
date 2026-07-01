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

"""Tests for `OpenSearchKPIStore.anonymise_for_session` (CTRLP-12 A3).

RGPD default per RFC §3.3: KPI events are an analytics aggregate, so erasure
*anonymises* the session's rows (nulls the identifiers) rather than deleting
them — aggregate counts must stay intact. There is no live OpenSearch here; a
tiny in-memory fake interprets the `update_by_query` body (filter + painless
field removal) exactly as OpenSearch would, so the test proves the store issues
the right query/script and the effect is anonymise-not-delete.
"""

from __future__ import annotations

from typing import Any, Dict, List

from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore


class _FakeOpenSearchClient:
    """In-memory OpenSearch stand-in that applies an `update_by_query` body.

    It supports just enough to exercise the anonymise path: a bool/filter with
    `term` clauses and a painless script that removes `params.fields` from each
    matched doc's `dims`. Returns `{"updated": n}` like the real API.
    """

    def __init__(self, docs: List[Dict[str, Any]]) -> None:
        self.docs = docs

    def update_by_query(
        self, *, index: str, body: Dict[str, Any], **_: Any
    ) -> Dict[str, Any]:
        terms = {
            list(clause["term"].keys())[0]: list(clause["term"].values())[0]
            for clause in body["query"]["bool"]["filter"]
        }
        fields = body["script"]["params"]["fields"]

        def matches(doc: Dict[str, Any]) -> bool:
            dims = doc.get("dims", {})
            return all(dims.get(k.split(".", 1)[1]) == v for k, v in terms.items())

        updated = 0
        for doc in self.docs:
            if matches(doc):
                for f in fields:
                    doc["dims"].pop(f, None)
                updated += 1
        return {"updated": updated}


def _store_with(docs: List[Dict[str, Any]]) -> OpenSearchKPIStore:
    """Build a store bound to the fake client, bypassing the OpenSearch __init__."""
    store = OpenSearchKPIStore.__new__(OpenSearchKPIStore)
    store.index = "kpi"
    store.client = _FakeOpenSearchClient(docs)  # type: ignore[assignment]
    return store


def test_anonymise_for_session_nulls_identifiers_and_keeps_row_count() -> None:
    """After anonymise, no row of the session carries user_id/session id/exchange_id,
    the anonymised count is returned, and the total row count is unchanged."""
    docs: List[Dict[str, Any]] = [
        {
            "dims": {
                "scope_type": "session",
                "scope_id": "session-1",
                "user_id": "alice",
                "exchange_id": "ex-1",
                "agent_id": "planner",
            }
        },
        {
            "dims": {
                "scope_type": "session",
                "scope_id": "session-1",
                "user_id": "alice",
                "exchange_id": "ex-2",
                "agent_id": "planner",
            }
        },
        # A different session — must be left untouched.
        {
            "dims": {
                "scope_type": "session",
                "scope_id": "session-2",
                "user_id": "bob",
                "exchange_id": "ex-9",
            }
        },
    ]
    store = _store_with(docs)

    updated = store.anonymise_for_session("session-1")

    assert updated == 2
    # Row count unchanged — anonymised, not deleted.
    assert len(docs) == 3

    session_1 = [d for d in docs if d["dims"].get("agent_id") == "planner"]
    for doc in session_1:
        dims = doc["dims"]
        # Direct identifiers gone…
        assert "user_id" not in dims
        assert "scope_id" not in dims
        assert "exchange_id" not in dims
        # …but the aggregate dimensions survive.
        assert dims["scope_type"] == "session"
        assert dims["agent_id"] == "planner"

    # The other session is untouched.
    other = docs[2]["dims"]
    assert other["scope_id"] == "session-2"
    assert other["user_id"] == "bob"


def test_anonymise_for_session_is_idempotent() -> None:
    """A second anonymise finds no matching rows (scope_id already nulled) → 0."""
    docs: List[Dict[str, Any]] = [
        {
            "dims": {
                "scope_type": "session",
                "scope_id": "session-1",
                "user_id": "alice",
                "exchange_id": "ex-1",
            }
        }
    ]
    store = _store_with(docs)

    assert store.anonymise_for_session("session-1") == 1
    assert store.anonymise_for_session("session-1") == 0
    assert len(docs) == 1
