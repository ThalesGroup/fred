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
`DocumentSearchPort` contract tests (CAPAB-01 #1906, RFC §3.8, §10).

Covers the SDK half of the pilot's platform-service seam:
- the port is a typed ABC taking scope PARAMETERS (no context/identity/token);
- `RuntimeServices.document_search` is an OPTIONAL, additive, default-None field
  — the same class of change as its other optional ports (backward-compatible).
"""

from __future__ import annotations

import asyncio
import dataclasses
import inspect
import logging

import fred_sdk.contracts.runtime as runtime_contract
import pytest
from fred_core.store.vector_search import VectorSearchHit


def _hit(uid: str) -> VectorSearchHit:
    return VectorSearchHit(
        uid=uid, title=f"Doc {uid}", content="body", score=1.0, type="document"
    )


class _FakePort(runtime_contract.DocumentSearchPort):
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def search(
        self,
        query: str,
        *,
        top_k: int = 8,
        library_tag_ids=None,
        document_uids=None,
        search_policy=None,
        include_attachments: bool = True,
        include_team_documents: bool = True,
        attachments_only: bool | None = None,
    ) -> runtime_contract.DocumentSearchResult:
        self.calls.append(
            {
                "query": query,
                "top_k": top_k,
                "library_tag_ids": library_tag_ids,
                "document_uids": document_uids,
                "search_policy": search_policy,
                "include_attachments": include_attachments,
                "include_team_documents": include_team_documents,
            }
        )
        return runtime_contract.DocumentSearchResult(hits=(_hit("d1"),))


def test_port_is_abstract() -> None:
    with pytest.raises(TypeError):
        runtime_contract.DocumentSearchPort()  # type: ignore[abstract]


def test_search_signature_takes_scope_params_not_identity() -> None:
    sig = inspect.signature(runtime_contract.DocumentSearchPort.search)
    params = set(sig.parameters)
    assert {
        "query",
        "top_k",
        "library_tag_ids",
        "document_uids",
        "search_policy",
        "include_attachments",
        "include_team_documents",
    } <= params
    assert sig.parameters["include_attachments"].default is True
    assert sig.parameters["include_team_documents"].default is True
    # No context/identity/token parameter may leak into the capability-facing
    # surface (RFC §10 doctrine).
    assert not ({"context", "identity", "token", "access_token", "binding"} & params)


def test_runtime_services_field_is_optional_and_additive() -> None:
    fields = {f.name: f for f in dataclasses.fields(runtime_contract.RuntimeServices)}
    assert "document_search" in fields
    # Default None → existing construction sites keep working unchanged.
    assert runtime_contract.RuntimeServices().document_search is None
    assert fields["document_search"].default is None


def test_runtime_services_carries_a_concrete_port() -> None:
    port = _FakePort()
    services = runtime_contract.RuntimeServices(document_search=port)
    assert services.document_search is port
    result = asyncio.run(port.search("q", top_k=3, library_tag_ids=["a"]))
    assert isinstance(result, runtime_contract.DocumentSearchResult)
    assert result.hits[0].uid == "d1"
    assert port.calls[0]["library_tag_ids"] == ["a"]


def test_deprecated_attachments_only_alias_maps_onto_the_ceilings(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(runtime_contract, "_attachments_only_warned", False)
    unchanged = runtime_contract.resolve_search_sources(
        include_attachments=False, include_team_documents=True, attachments_only=None
    )
    assert unchanged == (False, True)
    with caplog.at_level(logging.WARNING, logger=runtime_contract.__name__):
        pinned = runtime_contract.resolve_search_sources(
            include_attachments=True, include_team_documents=True, attachments_only=True
        )
        narrowed_off = runtime_contract.resolve_search_sources(
            include_attachments=False,
            include_team_documents=True,
            attachments_only=True,
        )
        off = runtime_contract.resolve_search_sources(
            include_attachments=True,
            include_team_documents=True,
            attachments_only=False,
        )
    assert pinned == (True, False)
    assert narrowed_off == (False, False)
    assert off == (True, True)
    assert len([r for r in caplog.records if "deprecated" in r.getMessage()]) == 1
