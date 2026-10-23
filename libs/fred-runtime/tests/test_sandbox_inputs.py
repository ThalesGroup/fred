import hashlib
import hmac
from types import SimpleNamespace

import pytest
from fred_sdk.contracts.sandbox import SandboxError, SandboxSessionIdentity

from fred_runtime.sandbox_http import SandboxHttpAdapter
from fred_runtime.sandbox_inputs import SandboxInputHttpAdapter


@pytest.mark.asyncio
async def test_input_adapter_signs_selected_path_and_rejects_escaping_response(
    monkeypatch,
) -> None:
    secret = "s" * 32
    monkeypatch.setenv("FRED_SANDBOX_FILE_GATEWAY_SECRET", secret)
    requests = []
    returned_path = ["/inputs/corpus/doc-1/report.txt"]

    class FakeKfClient:
        def __init__(self, **kwargs):
            pass

        async def _request_with_token_refresh(self, **kwargs):
            requests.append(kwargs)
            return SimpleNamespace(json=lambda: {"path": returned_path[0]})

    monkeypatch.setattr("fred_runtime.sandbox_inputs.KfBaseClient", FakeKfClient)
    broker = SandboxHttpAdapter(base_url="https://broker.example", token="b" * 32)

    async def view_key(session):
        return "a" * 64

    monkeypatch.setattr(broker, "view_key", view_key)
    adapter = SandboxInputHttpAdapter(
        broker, access_token="user-token", credentials=None
    )
    session = SandboxSessionIdentity(
        user_id="user-1", session_id="chat-1", team_id="team-1"
    )
    path = await adapter.bind_corpus("doc-1", session)
    assert path == returned_path[0]
    key = "a" * 64
    assert requests[0]["path"] == f"/sandbox-mount/views/{key}/corpus"
    payload = b"\0".join(
        (b"fred-sandbox-files-bind-v1", key.encode(), b"chat-1", b"user-1", b"team-1")
    )
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    assert requests[0]["headers"] == {"X-Fred-Sandbox-Bind": expected}

    returned_path[0] = "/inputs/../secret"
    with pytest.raises(SandboxError, match="unavailable"):
        await adapter.bind_corpus("doc-1", session)
    await broker.aclose()


@pytest.mark.asyncio
async def test_missing_file_secret_only_disables_input_selection(monkeypatch) -> None:
    monkeypatch.delenv("FRED_SANDBOX_FILE_GATEWAY_SECRET", raising=False)
    monkeypatch.setattr(
        "fred_runtime.sandbox_inputs.KfBaseClient",
        lambda **kwargs: SimpleNamespace(),
    )
    broker = SandboxHttpAdapter(base_url="https://broker.example", token="b" * 32)
    adapter = SandboxInputHttpAdapter(
        broker, access_token="user-token", credentials=None
    )
    session = SandboxSessionIdentity(
        user_id="user-1", session_id="chat-1", team_id="team-1"
    )
    with pytest.raises(SandboxError, match="unavailable"):
        await adapter.bind_corpus("doc-1", session)
    await broker.aclose()
