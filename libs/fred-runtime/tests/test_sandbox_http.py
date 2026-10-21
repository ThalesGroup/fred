import json

import httpx
import pytest
from fred_runtime.sandbox_http import SandboxHttpAdapter
from fred_sdk.contracts.sandbox import SandboxError, SandboxRequest


def test_transport_requires_https_and_credential() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        SandboxHttpAdapter(base_url="http://broker.internal", token="x" * 32)
    with pytest.raises(ValueError, match="at least 32"):
        SandboxHttpAdapter(base_url="https://broker.internal", token="short")


@pytest.mark.asyncio
async def test_adapter_sends_only_code_contract_and_maps_broker_error() -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if len(seen) == 1:
            return httpx.Response(
                200,
                json={
                    "exit_code": 0,
                    "stdout": "ok\n",
                    "stderr": "",
                    "timed_out": False,
                    "truncated": False,
                },
            )
        return httpx.Response(409, json={"error_code": "runtime_unavailable"})

    adapter = SandboxHttpAdapter(
        base_url="https://broker.internal",
        token="x" * 32,
        transport=httpx.MockTransport(handler),
    )
    assert adapter._client.timeout.read is not None
    assert adapter._client.timeout.read >= 438
    request = SandboxRequest(language="python", code="print('ok')")
    assert (await adapter.execute(request)).stdout == "ok\n"
    assert seen[0].url.path == "/v1/execute"
    assert seen[0].headers["Authorization"] == f"Bearer {'x' * 32}"
    assert json.loads(seen[0].content) == request.model_dump()
    with pytest.raises(SandboxError, match="runtime_unavailable"):
        await adapter.execute(request)
    await adapter.aclose()
