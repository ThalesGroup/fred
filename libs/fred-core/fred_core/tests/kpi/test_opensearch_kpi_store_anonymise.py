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

The rows here mirror the shape the runtime KPI emitters *actually* produce for a
conversation — `dims.session_id` + `dims.user_id` (and `dims.exchange_id` on
tool rows) — NOT a `scope_type=session`/`scope_id` shape (nothing in the runtime
emits that). This is the regression guard for CTRLP-12 blocker: the anonymise
query must match the emitted `dims.session_id`, or erasure silently misses every
real KPI row.
"""

from __future__ import annotations

from typing import Any, Dict, List, cast

from fred_core.kpi.opensearch_kpi_store import OpenSearchKPIStore


class _FakeOpenSearchClient:
    """In-memory OpenSearch stand-in that applies an `update_by_query` body.

    It supports just enough to exercise the anonymise path: a bool/filter with
    `term` clauses and a painless script that removes `params.fields` from each
    matched doc's `dims`. Returns `{"updated": n}` like the real API. It records
    the last `params` kwarg so a test can assert the query-string params
    (`conflicts`/`refresh`) the store forwards.
    """

    def __init__(self, docs: List[Dict[str, Any]]) -> None:
        self.docs = docs
        self.last_params: Dict[str, Any] | None = None

    def update_by_query(
        self,
        *,
        index: str,
        body: Dict[str, Any],
        params: Dict[str, Any] | None = None,
        **_: Any,
    ) -> Dict[str, Any]:
        self.last_params = params
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
    """Anonymise matches the emitted `dims.session_id` and nulls identifiers.

    Rows mirror the real emitters: a react phase row and two tool rows carry
    `dims.session_id`; a pure aggregate (`llm.call_latency_ms`, no session_id)
    and a different session must both survive untouched.
    """
    docs: List[Dict[str, Any]] = [
        # react/graph phase row: session_id + user_id, no exchange_id.
        {
            "dims": {
                "session_id": "session-1",
                "user_id": "alice",
                "agent_id": "planner",
                "phase": "react_stream",
            }
        },
        # tool rows: session_id + user_id + exchange_id.
        {
            "dims": {
                "session_id": "session-1",
                "user_id": "alice",
                "exchange_id": "ex-1",
                "tool_name": "search",
            }
        },
        {
            "dims": {
                "session_id": "session-1",
                "user_id": "alice",
                "exchange_id": "ex-2",
                "tool_name": "search",
            }
        },
        # A different session — must be left untouched.
        {
            "dims": {
                "session_id": "session-2",
                "user_id": "bob",
                "exchange_id": "ex-9",
            }
        },
        # A pure aggregate with no session_id (system-actor llm latency) — no
        # personal identifier, out of per-conversation scope, must be untouched.
        {"dims": {"agent_id": "planner", "model_name": "claude", "operation": "chat"}},
    ]
    store = _store_with(docs)

    updated = store.anonymise_for_session("session-1")

    assert updated == 3
    # Row count unchanged — anonymised, not deleted.
    assert len(docs) == 5

    session_1 = [d for d in docs[:3]]
    for doc in session_1:
        dims = doc["dims"]
        # Direct identifiers gone…
        assert "user_id" not in dims
        assert "session_id" not in dims
        assert "exchange_id" not in dims
        # …but the aggregate dimensions survive (counts stay attributable).
        assert dims.get("agent_id") == "planner" or dims.get("tool_name") == "search"

    # The other session is untouched.
    other = docs[3]["dims"]
    assert other["session_id"] == "session-2"
    assert other["user_id"] == "bob"

    # The pure aggregate is untouched.
    aggregate = docs[4]["dims"]
    assert aggregate == {
        "agent_id": "planner",
        "model_name": "claude",
        "operation": "chat",
    }


def test_anonymise_for_session_is_idempotent() -> None:
    """A second anonymise finds no matching rows (session_id already nulled) → 0."""
    docs: List[Dict[str, Any]] = [
        {
            "dims": {
                "session_id": "session-1",
                "user_id": "alice",
                "exchange_id": "ex-1",
            }
        }
    ]
    store = _store_with(docs)

    assert store.anonymise_for_session("session-1") == 1
    assert store.anonymise_for_session("session-1") == 0
    assert len(docs) == 1


def test_anonymise_forwards_conflicts_and_refresh_as_query_params() -> None:
    """The store forwards `conflicts=proceed` + `refresh=true` as query params.

    opensearch-py forwards these to the REST call as query-string params; passing
    them via `params=` (not bare kwargs) is the explicit, version-robust form.
    """
    docs: List[Dict[str, Any]] = [
        {"dims": {"session_id": "session-1", "user_id": "alice"}}
    ]
    store = _store_with(docs)

    store.anonymise_for_session("session-1")

    fake = cast(_FakeOpenSearchClient, store.client)
    assert fake.last_params == {"conflicts": "proceed", "refresh": "true"}
