# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""MCP diagnostics retain metadata without revealing error bodies."""

import logging

import httpx2
import pytest

from knowledge_flow_backend.mcp_mount import _log_inner_failure


@pytest.mark.asyncio
async def test_inner_http_failure_logs_only_route_status_and_validated_ids(caplog: pytest.LogCaptureFixture) -> None:
    request = httpx2.Request("POST", "http://fastapi/tabular/query?token=private", content=b"private SQL")
    response = httpx2.Response(
        500,
        request=request,
        headers={"X-Request-ID": "d12ce01a-bc54-4fd1-8984-2dbd518b5684", "X-Correlation-ID": "private"},
        text="private upstream response",
    )

    with caplog.at_level(logging.INFO):
        await _log_inner_failure(response)

    record = next(record for record in caplog.records if record.message == "mcp.inner_http_failure")
    assert record.upstream_http_status == 500
    assert record.method == "POST"
    assert record.upstream_route == "/tabular/query"
    assert record.upstream_request_id == "d12ce01a-bc54-4fd1-8984-2dbd518b5684"
    assert not hasattr(record, "upstream_correlation_id")
    assert "private" not in str(record.__dict__)
