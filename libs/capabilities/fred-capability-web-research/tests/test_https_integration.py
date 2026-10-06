# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
import asyncio

import httpx
import pytest
import pytest_asyncio
from fred_runtime.app.web_research import WebResearchService
from fred_runtime.app.web_research_activity import (
    WebResearchActivityBase,
)
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.web_research import (
    WebResearchDeploymentConfig,
    WebResearchError,
    WebSearchRequest,
)
from sqlalchemy.ext.asyncio import create_async_engine


@pytest_asyncio.fixture
async def service(monkeypatch):
    monkeypatch.setenv(
        "WEB_RESEARCH_EGRESS_TOKEN", "test-service-token-01234567890123456789"
    )
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(WebResearchActivityBase.metadata.create_all)

    async def reply(request):
        assert "user_id" not in request.content.decode()
        assert request.headers["x-request-id"]
        return httpx.Response(
            200,
            json={
                "results": [{"url": "https://example.com", "snippet": "PAGE-CONTENT"}]
            },
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(reply), base_url="https://egress/"
    )
    backend = WebResearchService(
        WebResearchDeploymentConfig(enabled=True, egress_url="https://egress"),
        engine,
        client=client,
    )
    yield backend, engine
    await backend.close()
    await engine.dispose()


def binding(user="user"):
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(user_id=user),
        portable_context=PortableContext(
            request_id="request",
            correlation_id="correlation",
            actor=user,
            tenant="default",
            environment=PortableEnvironment.DEV,
            user_id=user,
            session_id="session",
        ),
    )


@pytest.mark.asyncio
async def test_split_service_https_native_tool_and_activity(
    service, tmp_path, monkeypatch
):
    """Exercise a real TLS socket between runtime and separately hosted egress."""
    import socket
    import subprocess

    import uvicorn
    from fred_capability_web_research.capability import WebResearchCapability
    from fred_capability_web_research.egress import EgressConfig, create_app
    from fred_sdk.contracts.capability import (
        CapabilityContext,
        CapabilityIdentity,
        EmptyModel,
    )
    from fred_sdk.contracts.runtime import RuntimeServices
    from fred_sdk.contracts.web_research import WebPage

    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    await asyncio.to_thread(
        subprocess.run,
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=localhost",
            "-addext",
            "subjectAltName=DNS:localhost,IP:127.0.0.1",
            "-keyout",
            str(key),
            "-out",
            str(cert),
        ],
        check=True,
        capture_output=True,
    )

    class Provider:
        async def search(self, request, run):
            assert request.query == "TLS-QUERY"
            return [WebPage(url="https://example.com", snippet="evidence")]

    async def resolve(host, port):
        return "8.8.8.8"

    monkeypatch.setattr("fred_capability_web_research.egress.resolve_public", resolve)
    token = "test-service-token-01234567890123456789"  # pragma: allowlist secret
    app = create_app(EgressConfig(), token=token, provider=Provider())
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            log_level="critical",
            access_log=False,
            ssl_certfile=str(cert),
            ssl_keyfile=str(key),
            lifespan="on",
        )
    )
    serving = asyncio.create_task(server.serve(sockets=[listener]))
    backend, engine = service
    remote = None
    try:
        async with asyncio.timeout(10):
            while not server.started:
                if serving.done():
                    await serving
                await asyncio.sleep(0.01)
        remote = WebResearchService(
            WebResearchDeploymentConfig(
                enabled=True, egress_url=f"https://127.0.0.1:{port}", ca_file=str(cert)
            ),
            engine,
        )
        capability = WebResearchCapability()
        ctx = CapabilityContext(
            identity=CapabilityIdentity(user_id="user"),
            config=EmptyModel(),
            turn_options=EmptyModel(),
            services=RuntimeServices(web_research=remote.bind(binding())),
        )
        tool = next(tool for tool in capability.tools(ctx) if tool.name == "web_search")
        result = await tool.ainvoke({"query": "TLS-QUERY"})
        assert "evidence" in str(result)
        rows = await backend.store.list(user_id="user", limit=10)
        assert (
            len(rows) == 1
            and rows[0].query == "TLS-QUERY"
            and rows[0].outcome == "succeeded"
        )
        # A runtime without the private CA fails instead of bypassing verification.
        untrusted = WebResearchService(
            WebResearchDeploymentConfig(
                enabled=True, egress_url=f"https://127.0.0.1:{port}"
            ),
            engine,
        )
        try:
            with pytest.raises(WebResearchError, match="unavailable"):
                await untrusted.bind(binding()).execute(
                    WebSearchRequest(query="TLS-QUERY")
                )
        finally:
            await untrusted.close()
    finally:
        if remote:
            await remote.close()
        server.should_exit = True
        await serving
        listener.close()
