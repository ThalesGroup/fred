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
Shared plumbing for the document-reading capability pair (DOCREAD-01):
`document_verbatim` (verbatim positional read) and `document_extract`
(exhaustive extraction). Both sit on the SAME `RuntimeServices.document_markdown`
port and differ only in tool intent and how the pagination footer is worded, so
the config model, length resolution, error shaping, and page-to-tool-result
formatting live here once.

`document_tool_failure` has outgrown that pair - `document_similarity` uses it
too, since the error shaping is about the document ports in general, not about
paginated reading. It stays here rather than moving to a new module: two other
capabilities (`document_access`, `document_summarize`) still carry their own
private copies, and folding all four into one home is a cleanup of its own, not
something to smuggle into a feature change.

Doctrine (RFC §3.5, §3.8, §10), identical to `document_summarize`:
- the capability reaches the platform ONLY through the typed
  `RuntimeServices.document_markdown` port; the per-turn binding and the raw
  access token NEVER enter `CapabilityContext`;
- the tool signature exposes ONLY LLM arguments (uid + page window); identity
  and config reach the tool through the middleware closure, never the schema;
- `document_uid` is an internal working identifier — tools instruct the model to
  NEVER repeat it to the end user (answers refer to documents by display name).
"""

from __future__ import annotations

import time

from fred_sdk.contracts.context import (
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationResult,
)
from fred_sdk.contracts.runtime import DocumentMarkdownResult
from pydantic import BaseModel, Field

_KF_SERVICE = "Knowledge Flow"

# Built-in default page length when neither the caller (the LLM) nor the
# capability config specifies one. Matches the adapter's default page size.
DEFAULT_PAGE_MAX_CHARS = 8000
# Wire bounds clamped client-side so an out-of-range LLM value degrades
# gracefully instead of a surprising page.
_PAGE_MAX_CHARS_BOUNDS = (200, 50_000)


def _clamp(value: int, bounds: tuple[int, int]) -> int:
    low, high = bounds
    return max(low, min(value, high))


def resolve_page_max_chars(cap: int | None, requested: int | None) -> int:
    """
    Resolve the effective page length from the configured cap and the caller's
    request.

    The per-agent cap (`page_max_chars` config) is both the default (when the
    caller asks for nothing) and a hard upper bound on whatever the caller
    requests; without one, the built-in default applies and the caller's request
    is honored verbatim (within wire bounds).
    """

    default = cap if cap is not None else DEFAULT_PAGE_MAX_CHARS
    effective = requested if requested is not None else default
    if cap is not None:
        effective = min(effective, cap)
    return _clamp(effective, _PAGE_MAX_CHARS_BOUNDS)


class DocumentReadConfig(BaseModel):
    """Shared agent-creation / stored config of the document-reading pair.

    A single knob today: the default AND hard cap for the per-call page length
    (chars). None = built-in default, caller's request honored verbatim.
    """

    page_max_chars: int | None = Field(default=None, ge=200, le=50_000)


def document_tool_failure(
    *,
    tool_ref: str,
    action: str,
    exc: Exception,
    elapsed_s: float,
    document_uid: str,
) -> tuple[str, ToolInvocationResult]:
    """Turn a document-read tool-call failure into a non-empty, actionable error
    message plus an ``is_error=True`` artifact.

    The v2 ReAct runtime surfaces ``ToolInvocationResult.is_error`` directly to
    the user (and suppresses LLM hallucination), so a failing tool MUST return
    such a result instead of raising. Transport detail (timeout, HTTP status)
    arrives via the SDK-typed ``DocumentPortCallError`` attributes the adapters
    stamp — this module never imports the adapter's HTTP stack.
    """

    err_type = type(exc).__name__
    raw = str(exc).strip()
    timed_out = bool(getattr(exc, "timed_out", False))
    status_code = getattr(exc, "status_code", None)

    if timed_out:
        cause = f"the {_KF_SERVICE} service timed out after {elapsed_s:.0f}s"
    elif status_code is not None:
        cause = f"the {_KF_SERVICE} service returned HTTP {status_code}"
    else:
        cause = f"the {_KF_SERVICE} service call failed after {elapsed_s:.0f}s"

    detail = f": {raw}" if raw else ""
    message = (
        f"Could not {action} (document_uid={document_uid}): {cause} "
        f"[{err_type}{detail}]."
    )
    if status_code in (403, 404):
        message += (
            " Likely cause: document_uid was not a document's opaque uid. If you "
            "passed a file NAME, resolve the uid first — it is in the "
            "conversation's attached-files list (the bracketed value after the "
            "file name), in a search hit's 'uid' field, or on a DOCUMENT line of "
            "the document tree. Then retry with a real document uid. Do not "
            "repeat the uid to the user."
        )
    return message, ToolInvocationResult(
        tool_ref=tool_ref,
        is_error=True,
        blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=message),),
    )


def _pagination_footer(result: DocumentMarkdownResult, *, exhaustive: bool) -> str:
    """Machine-readable page/continuation banner appended to the tool content.

    This is the signal that structurally prevents `document_summarize`'s "half
    answer" failure mode: the model is told, in-band, exactly how much of the
    document it has seen and whether it MUST keep paging. `exhaustive` (the
    `extract` tool) makes the "keep going" directive imperative; the verbatim
    tool states it as a plain option.
    """

    end = result.offset + len(result.text)
    seen = f"chars {result.offset}–{end} of {result.total_chars}"
    if result.next_offset is not None:
        if exhaustive:
            return (
                f"\n\n[MORE TEXT REMAINS — {seen} read. You have NOT seen the "
                f"whole document yet; do not conclude. Call this tool again with "
                f"offset={result.next_offset} and keep accumulating matches until "
                f"the end is reached.]"
            )
        return (
            f"\n\n[{seen}. More text remains — call again with "
            f"offset={result.next_offset} to continue reading.]"
        )
    if result.offset == 0 and result.total_chars == 0:
        return "\n\n[The document has no readable text content.]"
    if exhaustive:
        return (
            f"\n\n[END OF DOCUMENT reached ({result.total_chars} chars total). "
            f"You now have the complete text — produce your exhaustive answer.]"
        )
    return f"\n\n[End of document ({result.total_chars} chars total).]"


async def read_document_page(
    *,
    port,
    tool_ref: str,
    document_uid: str,
    offset: int,
    max_chars: int,
    exhaustive: bool,
) -> tuple[str, ToolInvocationResult]:
    """Fetch one page through the `document_markdown` port and format it as a
    `(content, ToolInvocationResult)` return (shared by both tools).

    `content_and_artifact` convention (see `document_summarize`): the artifact's
    `blocks` carries the same text as `content` so a Graph agent — which keeps
    only the artifact half — still sees the page and its continuation footer.
    """

    if port is None:
        raise RuntimeError(
            f"{tool_ref}: RuntimeServices.document_markdown is not available on "
            "this execution path."
        )

    started = time.monotonic()
    try:
        result = await port.fetch_markdown(
            document_uid, offset=offset, max_chars=max_chars
        )
    except Exception as exc:
        action = "extract from the document" if exhaustive else "read the document"
        return document_tool_failure(
            tool_ref=tool_ref,
            action=action,
            exc=exc,
            elapsed_s=time.monotonic() - started,
            document_uid=document_uid,
        )

    content = result.text + _pagination_footer(result, exhaustive=exhaustive)
    artifact = ToolInvocationResult(
        tool_ref=tool_ref,
        blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=content),),
    )
    return content, artifact
