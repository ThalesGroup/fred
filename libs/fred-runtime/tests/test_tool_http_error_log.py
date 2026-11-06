# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

import logging

import httpx
from fred_runtime.common.context_aware_tool import _log_http_error


def test_http_failure_log_keeps_the_response_body_out(caplog) -> None:
    request = httpx.Request("GET", "http://kf.invalid/documents")
    error = httpx.HTTPStatusError(
        "refused",
        request=request,
        response=httpx.Response(403, request=request, content=b"SENTINEL document"),
    )
    with caplog.at_level(logging.ERROR):
        _log_http_error("search", error)
    assert "HTTP 403 on GET http://kf.invalid/documents" in caplog.text
    assert "SENTINEL" not in caplog.text
