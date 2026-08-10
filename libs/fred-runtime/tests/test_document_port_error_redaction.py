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

"""`_wrap_document_port_error` must not leak service topology (§8.46).

Why this file exists: the redaction shipped with no coverage at all. Disabling
it (`return text.strip()`) left the whole 869-case suite green, so nothing
distinguished the guard from a no-op — the same failure mode that let
`is_async_refresh_callable` ship wrong in both directions on this branch.

What makes this worth a test rather than a code comment: the detail built here
is NOT log-only. `_document_tool_failure` renders it into the tool result the
MODEL reads and into the trace block persisted to chat history, so an unredacted
`str(exc)` puts the internal host, port and route into the LLM context and the
stored history of every user who triggers a downstream failure.

Every test below fails when `_redact_urls` is reduced to `text.strip()`, except
the two that pin the non-URL and status-code behaviour (noted individually).
"""

from __future__ import annotations

import httpx
import pytest
from fred_runtime.integrations.v2_runtime.adapters import _wrap_document_port_error
from fred_sdk.contracts.runtime import DocumentPortCallError

KF_URL = "http://knowledge-flow:8111/knowledge-flow/v1/vector/search"


def _status_error(code: int, url: str = KF_URL) -> httpx.HTTPStatusError:
    """The real httpx exception, built the way httpx builds it.

    `raise_for_status()` is what produces the two-line message this guard has to
    cope with — a hand-written HTTPStatusError would not carry the MDN link, and
    would silently under-test the regex.
    """
    request = httpx.Request("POST", url)
    response = httpx.Response(code, request=request)
    with pytest.raises(httpx.HTTPStatusError) as excinfo:
        response.raise_for_status()
    return excinfo.value


def test_status_error_detail_carries_no_host_port_or_route() -> None:
    """The topology must not survive into the model-facing detail."""
    err = _wrap_document_port_error(_status_error(401))
    detail = str(err)

    assert "knowledge-flow" not in detail
    assert "8111" not in detail
    assert "/knowledge-flow/v1/" not in detail
    assert "http://" not in detail


def test_both_urls_in_httpx_two_line_message_are_redacted() -> None:
    """httpx emits TWO urls — the request and an MDN docs link.

    A regex that stopped at the first would leave the second in place. Observed
    live: the 401 message is
    `Client error '401 Unauthorized' for url '<kf>'\\nFor more information
    check: https://developer.mozilla.org/...`.
    """
    raw = str(_status_error(401))
    assert raw.count("http") >= 2, f"fixture no longer has two urls: {raw!r}"

    err = _wrap_document_port_error(_status_error(401))
    detail = str(err)

    assert "http" not in detail
    assert detail.count("[redacted url]") == 2


def test_placeholder_survives_markdown_rendering() -> None:
    """The marker must not look like an HTML tag.

    `<redacted-url>` was stored correctly but vanished in the chat UI, which
    parses the message as markdown and drops unknown tags — so the user saw
    `for url ' For more information check: ]` and could not tell deliberate
    sanitisation from a corrupt error string.
    """
    err = _wrap_document_port_error(_status_error(401))
    detail = str(err)

    assert "[redacted url]" in detail
    assert "<" not in detail and ">" not in detail


def test_status_code_survives_the_redaction() -> None:
    """Topology goes, diagnosis stays.

    (Passes without redaction too — it pins the other half of the contract, so
    a future "just drop the whole detail" fix cannot take the status with it.)
    """
    err = _wrap_document_port_error(_status_error(401))
    detail = str(err)

    assert err.status_code == 401
    assert "401" in detail
    assert err.timed_out is False


def test_connection_error_is_wrapped_without_inventing_a_status() -> None:
    """A dead service yields no status code, and nothing to redact.

    This is the shape the connection-refused test produced live: httpx's
    ConnectError message contains no url, which is exactly why that test could
    not exercise the redaction and this file had to exist.

    (Passes without redaction — it guards the no-url path against over-eager
    stripping.)
    """
    err = _wrap_document_port_error(
        httpx.ConnectError("All connection attempts failed")
    )
    detail = str(err)

    assert err.status_code is None
    assert detail == "All connection attempts failed"


def test_timeout_is_flagged_and_still_redacted() -> None:
    """`timed_out` drives caller retry logic, so it must survive too."""
    request = httpx.Request("POST", KF_URL)
    err = _wrap_document_port_error(
        httpx.ReadTimeout(f"timed out reading {KF_URL}", request=request)
    )
    detail = str(err)

    assert err.timed_out is True
    assert "knowledge-flow" not in detail
    assert "[redacted url]" in detail


def test_empty_message_degrades_to_the_exception_type() -> None:
    """An exception with no message must not produce an empty detail.

    `_wrap_document_port_error` falls back to the type name; without it the
    model receives a tool failure with no explanation at all.
    """
    err = _wrap_document_port_error(httpx.ConnectError(""))
    detail = str(err)

    assert detail == "ConnectError"


# ---------------------------------------------------------------------------
# The message the user and the model actually see.
#
# Redacting URLs out of `str(exc)` left the trailing clause meaningless: an
# unbalanced quote and "For more information check:" pointing at nothing. Where
# the adapter identified the failure, the structured cause is the whole message;
# where it did not, the raw text is the only information there is and stays.
# ---------------------------------------------------------------------------


def _message(exc: Exception) -> str:
    from fred_runtime.capabilities.document_access.capability import (
        _document_tool_failure,
    )

    message, result = _document_tool_failure(
        tool_ref="doc.search", action="search documents", exc=exc, elapsed_s=0.116
    )
    # The artifact must carry the same text — a Graph agent's plain-dict
    # invocation keeps only the artifact half of a content_and_artifact return.
    assert result.is_error is True
    assert result.blocks[0].text == message
    return message


def test_http_status_failure_states_the_status_and_stops() -> None:
    """No repetition, no class name, no redaction rubble."""
    msg = _message(
        DocumentPortCallError(
            "Client error '401 Unauthorized' for url '[redacted url]\n"
            "For more information check: [redacted url]",
            status_code=401,
        )
    )

    assert (
        msg
        == "Could not search documents: the Knowledge Flow service returned HTTP 401."
    )
    assert "redacted url" not in msg
    assert "DocumentPortCallError" not in msg


def test_timeout_failure_states_the_timeout_and_stops() -> None:
    msg = _message(
        DocumentPortCallError("timed out reading [redacted url]", timed_out=True)
    )

    assert (
        msg
        == "Could not search documents: the Knowledge Flow service timed out after 0s."
    )
    assert "redacted url" not in msg


def test_unstructured_failure_keeps_the_raw_detail() -> None:
    """A dead service has no status to report, so the text is all there is."""
    msg = _message(DocumentPortCallError("All connection attempts failed"))

    assert "All connection attempts failed" in msg
    assert "DocumentPortCallError" in msg


def test_unexpected_exception_still_names_its_type() -> None:
    """The case the broad `except Exception` exists for.

    A TypeError from a renamed port kwarg must not degrade into an anonymous
    "service call failed" — the type is what tells a developer it is a bug in
    Fred, not an outage downstream.
    """
    msg = _message(TypeError("search() got an unexpected keyword argument 'topk'"))

    assert "TypeError" in msg
    assert "unexpected keyword argument 'topk'" in msg
