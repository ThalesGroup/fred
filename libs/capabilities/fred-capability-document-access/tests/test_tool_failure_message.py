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

"""The failure message the user and the model actually see.

A failing document tool must RETURN an `is_error` artifact, never raise: the
default `ToolNode` handler re-raises, which leaves the call pending in the
trace and yields an empty error detail to the UI.

Redacting URLs out of `str(exc)` left the trailing clause meaningless: an
unbalanced quote and "For more information check:" pointing at nothing. Where
the adapter identified the failure, the structured cause is the whole message;
where it did not, the raw text is the only information there is and stays. The
redaction itself belongs to the adapter and is tested in fred-runtime
(`test_document_port_error_redaction.py`).
"""

from __future__ import annotations

from fred_capability_document_access.capability import _document_tool_failure
from fred_sdk.contracts.runtime import DocumentPortCallError


def _message(exc: Exception) -> str:
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
