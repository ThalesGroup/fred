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

"""A mistaken document identifier must not revoke a live delegated run."""

from __future__ import annotations

from collections.abc import Iterator, Sequence

import httpx
import pytest
from conftest import MockIdentityProvider, admitted_provider
from fred_core.documents.selection import DocumentScope
from fred_core.documents.transport import DOCUMENT_CONTEXT_HEADER, DocumentAccessContext
from fred_runtime.common.outbound_credentials import DelegatedCredentialProvider
from fred_runtime.integrations.v2_runtime.adapters import DocumentMarkdownAdapter
from fred_runtime.model_routing.turn import TurnAuthority
from fred_runtime.runtime_context import RuntimeConfig, set_runtime_context
from fred_runtime.runtime_context import RuntimeContext as FredRuntimeContext
from fred_runtime.runtime_support.authority import AuthorityLostError
from fred_runtime.runtime_support.run_scope import RunScope
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.models import AgentTuning, MCPServerRef
from fred_sdk.contracts.runtime import DocumentPortCallError
from weaver_fixtures import INSTANCE_ID, SPACE_ID, turn_binding

UID = "00000000-0000-0000-0000-000000000101"
FOLDER = "00000000-0000-0000-0000-000000000201"
NAME = "02-technical-requirements.md"
MARKER = "private-upstream-detail"


class _Settings:
    id = "agent-a"
    team_id: str | None = "team-1"
    tuning: AgentTuning | None = None
    active_mcp_servers: Sequence[MCPServerRef] = ()


@pytest.fixture(autouse=True)
def _runtime_context() -> Iterator[None]:
    set_runtime_context(
        FredRuntimeContext(RuntimeConfig(knowledge_flow_url="http://kf.invalid/kf/v1"))
    )
    authority = TurnAuthority(turn_binding("agent-a", session="s-1", run="run-7"), None)
    with RunScope.open() as run:
        run.turn_authority = authority
        authority.start(run)
        yield
    set_runtime_context(None)


def _reader(provider: DelegatedCredentialProvider) -> DocumentMarkdownAdapter:
    """Use the real adapter and HTTP client with one admitted person's grant."""
    return DocumentMarkdownAdapter(
        binding=BoundRuntimeContext(
            runtime_context=RuntimeContext(
                user_id="alice",
                session_id="s-1",
                team_id="team-1",
                space_id=SPACE_ID,
                agent_instance_id=INSTANCE_ID,
            ),
            portable_context=PortableContext(
                request_id="r-1",
                correlation_id="c-1",
                actor="alice",
                tenant="team-1",
                environment=PortableEnvironment.DEV,
            ),
        ),
        settings=_Settings(),
        credentials=provider,
        document_scope=DocumentScope.from_ids([FOLDER]),
    )


@pytest.mark.asyncio
async def test_wrong_name_can_be_corrected_without_token_renewal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    iam = MockIdentityProvider(monkeypatch)
    provider = admitted_provider(iam.provider)
    reader = _reader(provider)
    seen: list[httpx.Request] = []

    def receive(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/" + UID + "/markdown"):
            return httpx.Response(200, json={"content": "Authorized document text"})
        return httpx.Response(
            403,
            headers={"X-Fred-Denial-Cause": "permission_refused"},
            text=MARKER,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(receive)) as client:
        reader._client.client = client
        for incorrect in (NAME, "another-inaccessible-opaque-id"):
            with pytest.raises(DocumentPortCallError) as failure:
                await reader.fetch_markdown(incorrect)
            assert failure.value.status_code == 403
            assert MARKER not in str(failure.value)
        result = await reader.fetch_markdown(UID)

    assert result.text == "Authorized document text"
    assert len(seen) == 3  # Each explicit call made exactly one request.
    assert iam.issued == ["workload-token-1"]
    for request in seen:
        assert request.headers["authorization"] == "Bearer workload-token-1"
        assert request.url.params["person"] == "alice"
        assert request.url.params["run"] == "run-7"
        context = DocumentAccessContext.model_validate_json(
            request.headers[DOCUMENT_CONTEXT_HEADER]
        )
        assert str(context.space_id) == SPACE_ID
        assert context.document_scope == DocumentScope.from_ids([FOLDER])
        assert "space_id" not in request.url.params
        assert "document_scope" not in request.url.params
    assert provider.record.run_id == "run-7"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "cause", "requests"),
    [
        (403, None, 1),
        (403, "unknown", 1),
        (403, "permission_refused, account_suspended", 1),
        (403, "account_suspended", 1),
        (403, "delegation_not_allowed", 1),
        (503, "account_status_unavailable", 1),
        (401, "permission_refused", 2),
    ],
)
async def test_document_reader_preserves_terminal_authority_refusals(
    monkeypatch: pytest.MonkeyPatch, status: int, cause: str | None, requests: int
) -> None:
    iam = MockIdentityProvider(monkeypatch, "workload-token-1", "workload-token-2")
    reader = _reader(admitted_provider(iam.provider))
    seen: list[httpx.Request] = []

    def receive(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            status,
            headers={"X-Fred-Denial-Cause": cause} if cause is not None else {},
            text=MARKER,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(receive)) as client:
        reader._client.client = client
        with pytest.raises(AuthorityLostError) as failure:
            await reader.fetch_markdown(UID)
    assert MARKER not in str(failure.value)
    assert len(seen) == requests


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "document_uid",
    [
        "../raw_content/denied",
        "doc/artifact/secret",
        "%2e%2e%2fraw_content%2fdenied",
        "doc%2fartifact%2fsecret",
        "doc?query=value",
        "doc#fragment",
        "doc\\artifact\\secret",
        ".",
        "..",
        "",
    ],
)
async def test_path_shaped_identifiers_do_not_extend_recovery(
    monkeypatch: pytest.MonkeyPatch, document_uid: str
) -> None:
    iam = MockIdentityProvider(monkeypatch)
    reader = _reader(admitted_provider(iam.provider))
    seen: list[httpx.Request] = []

    def receive(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            403,
            headers={"X-Fred-Denial-Cause": "permission_refused"},
            text=MARKER,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(receive)) as client:
        reader._client.client = client
        with pytest.raises(AuthorityLostError):
            await reader.fetch_markdown(document_uid)
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_other_document_operations_keep_permission_refusals_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    iam = MockIdentityProvider(monkeypatch)
    reader = _reader(admitted_provider(iam.provider))
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                403,
                headers={"X-Fred-Denial-Cause": "permission_refused"},
                text=MARKER,
            )
        )
    ) as client:
        reader._client.client = client
        with pytest.raises(AuthorityLostError):
            await reader._client.fetch_raw_content(document_uid=UID)


@pytest.mark.asyncio
async def test_successful_renewal_preserves_selection_and_trusted_space(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    iam = MockIdentityProvider(monkeypatch, "workload-token-1", "workload-token-2")
    reader = _reader(admitted_provider(iam.provider))
    seen: list[httpx.Request] = []

    def receive(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return (
            httpx.Response(401)
            if len(seen) == 1
            else httpx.Response(200, json={"content": "selected"})
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(receive)) as client:
        reader._client.client = client
        assert (await reader.fetch_markdown(UID)).text == "selected"
    assert len(seen) == 2
    assert seen[0].url.params == seen[1].url.params
    assert seen[1].headers["authorization"] == "Bearer workload-token-2"
