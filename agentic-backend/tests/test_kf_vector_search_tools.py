import httpx
import pytest

from agentic_backend.common.kf_base_client import KfBaseClient
from agentic_backend.common.kf_document_client import KfDocumentClient
from agentic_backend.common.structures import AgentSettings
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.integrations.kf_vector_search.kf_vector_search_tools import (
    build_kf_vector_search_tools,
)


class _FakeAgent:
    """Minimal KnowledgeFlowAgentContext stand-in for tool-closure unit tests."""

    def __init__(
        self, *, agent_settings: AgentSettings, runtime_context: RuntimeContext
    ):
        self.agent_settings = agent_settings
        self.runtime_context = runtime_context

    def refresh_user_access_token(self) -> str:
        raise NotImplementedError("not exercised by these tests")


def _response(payload: object) -> httpx.Response:
    return httpx.Response(
        200, json=payload, request=httpx.Request("POST", "http://example.test/")
    )


@pytest.fixture(autouse=True)
def _bypass_real_client_construction(monkeypatch):
    """The tool closures construct a real KfDocumentClient(agent=agent), whose
    KfBaseClient.__init__ needs a live ApplicationContext (HTTP client, KPI writer,
    timeouts). Unit tests for the tool closures don't need any of that -- only the
    agent/agent_settings/runtime_context wiring and the final HTTP call (stubbed
    separately via _request_with_token_refresh). Skip __init__'s real setup so
    construction succeeds with just the `agent` reference.
    """

    def fake_init(self, agent=None, **_kwargs):
        self._agent = agent
        self._static_access_token = None
        self._refresh_cb = None
        # Timeout attributes normally resolved from ApplicationContext config; the
        # real summarize() reads _summarize_read_timeout to set a per-request override.
        self._connect_timeout = 5.0
        self._read_timeout = 15.0
        self._summarize_read_timeout = 120.0
        # Global summary-length default/cap (ai.summarize_max_chars); None = unset.
        self._summarize_max_chars_default = None

    monkeypatch.setattr(KfBaseClient, "__init__", fake_init)


@pytest.fixture(autouse=True)
def _stub_request_with_token_refresh(monkeypatch):
    """Replace KfDocumentClient's HTTP call with a fake keyed by path, so tool
    closures can be exercised without any real network access."""
    responses: dict[str, httpx.Response] = {}

    async def fake_request(self, *, method, path, phase_name, **kwargs):
        return responses[path]

    monkeypatch.setattr(KfDocumentClient, "_request_with_token_refresh", fake_request)
    return responses


def _tool_by_name(tools, name: str):
    return next(t for t in tools if t.name == name)


@pytest.mark.asyncio
async def test_list_document_tree_returns_rendered_tree_text(
    _stub_request_with_token_refresh,
):
    _stub_request_with_token_refresh["/documents/tree"] = _response(
        {"tree": "Sales/\n  HR/\n", "truncated": False}
    )
    agent = _FakeAgent(
        agent_settings=AgentSettings(id="a-1", name="Agent"),
        runtime_context=RuntimeContext(),
    )
    tools = build_kf_vector_search_tools(agent)
    list_document_tree = _tool_by_name(tools, "list_document_tree")

    content, artifact = await list_document_tree.coroutine(
        working_directory="Sales", max_chars=4000
    )

    assert content == "Sales/\n  HR/\n"
    assert artifact.tool_ref == "list_document_tree"


@pytest.mark.asyncio
async def test_list_document_tree_appends_session_attachments(
    monkeypatch, _stub_request_with_token_refresh
):
    """Files attached to the current conversation are listed in a trailing
    'Session attachments' section, in the same 'name [uid] (uploaded date)'
    format as tree docs, so the agent can summarize/search them by uid."""
    from datetime import datetime, timezone

    from agentic_backend.core.session.stores.base_session_attachment_store import (
        SessionAttachmentRecord,
    )

    _stub_request_with_token_refresh["/documents/tree"] = _response(
        {"tree": "Sales/\n  HR/\n", "truncated": False}
    )

    records = [
        SessionAttachmentRecord(
            session_id="sess-1",
            attachment_id="att-1",
            name="report.pdf",
            summary_md="",
            document_uid="doc-att-1",
            created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        ),
        # No document_uid -> failed to ingest -> must be skipped (not summarizable).
        SessionAttachmentRecord(
            session_id="sess-1",
            attachment_id="att-2",
            name="broken.pdf",
            summary_md="",
            document_uid=None,
        ),
    ]

    class _FakeStore:
        async def list_for_session(self, session_id):
            assert session_id == "sess-1"
            return records

    monkeypatch.setattr(
        "agentic_backend.application_context.get_session_attachment_store",
        lambda: _FakeStore(),
    )

    agent = _FakeAgent(
        agent_settings=AgentSettings(id="a-1", name="Agent"),
        runtime_context=RuntimeContext(session_id="sess-1"),
    )
    tools = build_kf_vector_search_tools(agent)
    list_document_tree = _tool_by_name(tools, "list_document_tree")

    content, _ = await list_document_tree.coroutine()

    assert "Sales/\n  HR/\n" in content
    assert "Session attachments:" in content
    assert "report.pdf [doc-att-1] (uploaded 2026-06-01)" in content
    assert "broken.pdf" not in content


@pytest.mark.asyncio
async def test_list_document_tree_without_session_has_no_attachments_section(
    _stub_request_with_token_refresh,
):
    """No session_id -> no attachment lookup -> the tree text is returned as-is."""
    _stub_request_with_token_refresh["/documents/tree"] = _response(
        {"tree": "Sales/\n", "truncated": False}
    )
    agent = _FakeAgent(
        agent_settings=AgentSettings(id="a-1", name="Agent"),
        runtime_context=RuntimeContext(),
    )
    tools = build_kf_vector_search_tools(agent)
    list_document_tree = _tool_by_name(tools, "list_document_tree")

    content, _ = await list_document_tree.coroutine()

    assert content == "Sales/\n"
    assert "Session attachments" not in content


@pytest.mark.asyncio
async def test_list_document_tree_respects_hard_library_binding(
    monkeypatch, _stub_request_with_token_refresh
):
    """Hard binding (document_library_tags_ids on the agent's tuning) should be
    forwarded as the tag_ids scope, not left unset."""
    seen_payloads: list[dict] = []

    async def fake_request(self, *, method, path, phase_name, **kwargs):
        seen_payloads.append(kwargs.get("json", {}))
        return _response({"tree": "(empty)", "truncated": False})

    monkeypatch.setattr(KfDocumentClient, "_request_with_token_refresh", fake_request)

    from agentic_backend.common.structures import AgentTuning
    from agentic_backend.core.agents.agent_spec import MCPServerRef
    from agentic_backend.integrations.kf_vector_search.kf_vector_search_params import (
        KfVectorSearchParams,
    )

    agent_settings = AgentSettings(
        id="a-1",
        name="Agent",
        tuning=AgentTuning(
            role="r",
            description="d",
            mcp_servers=[
                MCPServerRef(
                    id="mcp-knowledge-flow-mcp-text",
                    params=KfVectorSearchParams(document_library_tags_ids=["lib-1"]),
                )
            ],
        ),
    )
    agent = _FakeAgent(agent_settings=agent_settings, runtime_context=RuntimeContext())
    tools = build_kf_vector_search_tools(agent)
    list_document_tree = _tool_by_name(tools, "list_document_tree")

    await list_document_tree.coroutine()

    assert seen_payloads[-1].get("tag_ids") == ["lib-1"]


@pytest.mark.asyncio
async def test_summarize_document_returns_summary_text(
    _stub_request_with_token_refresh,
):
    _stub_request_with_token_refresh["/documents/doc-1/summarize"] = _response(
        {
            "document_uid": "doc-1",
            "summary": "Key risks: A, B, C.",
            "shrunk_for_budget": False,
            "keywords": ["risk"],
        }
    )
    agent = _FakeAgent(
        agent_settings=AgentSettings(id="a-1", name="Agent"),
        runtime_context=RuntimeContext(),
    )
    tools = build_kf_vector_search_tools(agent)
    summarize_document = _tool_by_name(tools, "summarize_document")

    content, artifact = await summarize_document.coroutine(
        document_uid="doc-1", instruction="focus on risks", max_chars=1000
    )

    assert content == "Key risks: A, B, C."
    assert artifact.tool_ref == "summarize_document"


def _http_status_error(path: str, status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", f"http://example.test{path}")
    response = httpx.Response(status_code, request=request, text="boom")
    return httpx.HTTPStatusError(
        f"Server error '{status_code}'", request=request, response=response
    )


@pytest.mark.asyncio
async def test_summarize_document_uses_long_read_timeout(monkeypatch):
    """summarize() must override the read timeout per-request with the configured
    long value so large documents don't trip the short default read timeout."""
    seen_kwargs: dict = {}

    async def fake_request(self, *, method, path, phase_name, **kwargs):
        seen_kwargs.update(kwargs)
        return _response(
            {
                "document_uid": "doc-1",
                "summary": "ok",
                "shrunk_for_budget": False,
                "keywords": [],
            }
        )

    monkeypatch.setattr(KfDocumentClient, "_request_with_token_refresh", fake_request)

    agent = _FakeAgent(
        agent_settings=AgentSettings(id="a-1", name="Agent"),
        runtime_context=RuntimeContext(),
    )
    tools = build_kf_vector_search_tools(agent)
    summarize_document = _tool_by_name(tools, "summarize_document")

    await summarize_document.coroutine(document_uid="doc-1")

    assert seen_kwargs.get("read_timeout") == 120.0


@pytest.mark.asyncio
async def test_summarize_document_timeout_yields_error_result(monkeypatch):
    """A read timeout (empty-message httpx.ReadTimeout, as raised in production) must
    become a tool_result with is_error=True and a non-empty, actionable detail —
    never a raised exception (which would leave the trace pending with a blank
    detail)."""

    async def fake_request(self, *, method, path, phase_name, **kwargs):
        raise httpx.ReadTimeout("")  # real read timeouts stringify to ""

    monkeypatch.setattr(KfDocumentClient, "_request_with_token_refresh", fake_request)

    agent = _FakeAgent(
        agent_settings=AgentSettings(id="a-1", name="Agent"),
        runtime_context=RuntimeContext(session_id="sess-1"),
    )
    tools = build_kf_vector_search_tools(agent)
    summarize_document = _tool_by_name(tools, "summarize_document")

    content, artifact = await summarize_document.coroutine(document_uid="doc-1")

    assert artifact.tool_ref == "summarize_document"
    assert artifact.is_error is True
    assert content.strip()  # detail is never empty
    assert "doc-1" in content
    assert "timed out" in content
    assert "ReadTimeout" in content


@pytest.mark.asyncio
async def test_summarize_document_http_error_yields_error_result(monkeypatch):
    """A Knowledge Flow 5xx must surface as an is_error tool_result carrying the
    status code and document uid, not as a raised exception."""

    async def fake_request(self, *, method, path, phase_name, **kwargs):
        raise _http_status_error(path, 500)

    monkeypatch.setattr(KfDocumentClient, "_request_with_token_refresh", fake_request)

    agent = _FakeAgent(
        agent_settings=AgentSettings(id="a-1", name="Agent"),
        runtime_context=RuntimeContext(),
    )
    tools = build_kf_vector_search_tools(agent)
    summarize_document = _tool_by_name(tools, "summarize_document")

    content, artifact = await summarize_document.coroutine(document_uid="doc-1")

    assert artifact.is_error is True
    assert "doc-1" in content
    assert "HTTP 500" in content


@pytest.mark.asyncio
async def test_list_document_tree_then_summarize_failure(monkeypatch):
    """End-to-end-ish: list_document_tree succeeds (as in the bug report) and a
    subsequent summarize_document failure still produces a clean error result rather
    than blowing up the turn."""
    tree_response = _response(
        {"tree": "Documents/\n  RFP.pdf [doc-1]\n", "truncated": False}
    )

    async def fake_request(self, *, method, path, phase_name, **kwargs):
        if path == "/documents/tree":
            return tree_response
        raise httpx.ReadTimeout("")

    monkeypatch.setattr(KfDocumentClient, "_request_with_token_refresh", fake_request)

    agent = _FakeAgent(
        agent_settings=AgentSettings(id="a-1", name="Agent"),
        runtime_context=RuntimeContext(),
    )
    tools = build_kf_vector_search_tools(agent)

    tree_content, tree_artifact = await _tool_by_name(
        tools, "list_document_tree"
    ).coroutine()
    assert "doc-1" in tree_content
    assert tree_artifact.is_error is False

    summary_content, summary_artifact = await _tool_by_name(
        tools, "summarize_document"
    ).coroutine(document_uid="doc-1")
    assert summary_artifact.is_error is True
    assert "doc-1" in summary_content


@pytest.mark.parametrize(
    "cap,requested,global_default,expected",
    [
        (None, None, None, 5000),  # built-in default
        (None, 8000, None, 8000),  # no cap -> honor request
        (3000, None, None, 3000),  # per-agent cap is the default
        (3000, 8000, None, 3000),  # per-agent cap clamps a larger request
        (10000, 2000, None, 2000),  # smaller request honored under a higher cap
        (None, None, 4000, 4000),  # global default applies when no per-agent cap
        (None, 9000, 4000, 4000),  # global default also caps the request
        (3000, None, 4000, 3000),  # per-agent cap overrides the global default
    ],
)
def test_resolve_summarize_max_chars(cap, requested, global_default, expected):
    from agentic_backend.common.kf_document_client import resolve_summarize_max_chars
    from agentic_backend.integrations.kf_vector_search.kf_vector_search_params import (
        KfVectorSearchParams,
    )

    params = KfVectorSearchParams(summarize_max_chars=cap)
    assert resolve_summarize_max_chars(params, requested, global_default) == expected


@pytest.mark.asyncio
async def test_summarize_document_clamps_to_configured_max_chars(monkeypatch):
    """A configured summarize_max_chars cap must clamp the length sent to Knowledge
    Flow, even when the model requests a larger value."""
    seen_payloads: list[dict] = []

    async def fake_request(self, *, method, path, phase_name, **kwargs):
        seen_payloads.append(kwargs.get("json", {}))
        return _response(
            {
                "document_uid": "doc-1",
                "summary": "ok",
                "shrunk_for_budget": False,
                "keywords": [],
            }
        )

    monkeypatch.setattr(KfDocumentClient, "_request_with_token_refresh", fake_request)

    from agentic_backend.common.structures import AgentTuning
    from agentic_backend.core.agents.agent_spec import MCPServerRef
    from agentic_backend.integrations.kf_vector_search.kf_vector_search_params import (
        KfVectorSearchParams,
    )

    agent_settings = AgentSettings(
        id="a-1",
        name="Agent",
        tuning=AgentTuning(
            role="r",
            description="d",
            mcp_servers=[
                MCPServerRef(
                    id="mcp-knowledge-flow-mcp-text",
                    params=KfVectorSearchParams(summarize_max_chars=2000),
                )
            ],
        ),
    )
    agent = _FakeAgent(agent_settings=agent_settings, runtime_context=RuntimeContext())
    tools = build_kf_vector_search_tools(agent)
    summarize_document = _tool_by_name(tools, "summarize_document")

    await summarize_document.coroutine(document_uid="doc-1", max_chars=9000)

    assert seen_payloads[-1].get("max_chars") == 2000


@pytest.mark.asyncio
async def test_builder_returns_all_three_tools():
    agent = _FakeAgent(
        agent_settings=AgentSettings(id="a-1", name="Agent"),
        runtime_context=RuntimeContext(),
    )
    tools = build_kf_vector_search_tools(agent)

    assert {t.name for t in tools} == {
        "search_documents_using_vectorization",
        "list_document_tree",
        "summarize_document",
    }
