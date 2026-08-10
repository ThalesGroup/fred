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

"""Minimal read-through proxy serving objects behind an application-signed URL.

Why this exists:
- `docs/swift/rfc/CONTENT-URL-STRATEGY-RFC.md`: when the content store cannot mint
  browser-facing presigned URLs (GCS without `iam.serviceAccounts.signBlob`, local
  filesystem), `ContentUrlResolver` mints `{base}/objects/{key}?token=…` instead.
  This router is the other half — it verifies the signature and streams the bytes.

Security model — read before touching this file:
- The signature **is** the authorization decision. It was minted by code that had
  already run its ReBAC check, exactly like a presigned URL. There is no session
  here by construction, so there is no user to re-check and no key→resource map to
  consult; a short TTL is the control, in this mode and in `presigned` alike.
- The route is mounted **only** when `url_strategy == "proxy"`, so `presigned`
  deployments have no dormant unauthenticated endpoint.
- `include_in_schema=False` (RFC §6.3): generated frontend clients never call it,
  URLs arrive embedded in markdown or in a DTO field.
- Never log the token or the full URL.

How to use it:
```python
router.include_router(
    build_object_proxy_router(reader=content_store, secret=secret),
)
```
"""

from __future__ import annotations

import logging
import time
from typing import BinaryIO, Iterator, Optional, Protocol

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from fred_core.store.content_url_resolver import OBJECT_PROXY_PATH
from fred_core.store.signed_token import token_expiry, verify_signed_token

logger = logging.getLogger(__name__)

# Matches the streaming reference implementation for document downloads.
_CHUNK_SIZE = 8192


class ObjectStat(Protocol):
    """The metadata the proxy needs before it can answer a Range request.

    Read-only members on purpose, so both a frozen dataclass (`fred_core.store.
    ObjectInfo`) and a pydantic model (knowledge-flow's `StoredObjectInfo`) satisfy it.
    """

    @property
    def size(self) -> int: ...

    @property
    def content_type(self) -> str | None: ...

    @property
    def etag(self) -> str | None: ...


class ObjectReader(Protocol):
    """The minimal read interface this route depends on.

    Both store families already satisfy it: knowledge-flow's `BaseContentStore`
    implements these two methods directly, and fred-core's `LocalContentStore` /
    `MinioContentStore` / `GcsContentStore` gained them for this route.
    """

    def stat_object(self, key: str) -> ObjectStat: ...

    def get_object_stream(
        self, key: str, *, start: Optional[int] = None, length: Optional[int] = None
    ) -> BinaryIO: ...


def _validate_key(key: str) -> str:
    """Return `key` normalized, or raise 400 when it could escape the store root.

    Why this exists:
    - There is no ReBAC check downstream. The signature already pins the key, but
      a traversal-shaped key must never reach a filesystem-backed store even if the
      minting side is ever changed to accept user input.
    """

    normalized = key.lstrip("/")
    parts = normalized.split("/")
    if (
        not normalized
        or "\\" in normalized
        or "\x00" in normalized
        or any(part in ("..", ".") for part in parts)
    ):
        raise HTTPException(status_code=400, detail="Invalid object key")
    return normalized


def _parse_range(
    range_header: Optional[str],
) -> Optional[tuple[int | None, int | None]]:
    """Parse a single `bytes=START-END` range; None when absent or unsupported."""

    if not range_header or not range_header.startswith("bytes="):
        return None
    spec = range_header[len("bytes=") :].strip()
    if "," in spec or "-" not in spec:
        return None
    start_s, _, end_s = spec.partition("-")
    if (start_s and not start_s.isdigit()) or (end_s and not end_s.isdigit()):
        return None
    start = int(start_s) if start_s else None
    end = int(end_s) if end_s else None
    if start is None and end is None:
        return None
    return start, end


def _chunks(stream: BinaryIO) -> Iterator[bytes]:
    """Yield the stream in fixed-size chunks (sync generator → Starlette threadpool)."""

    while chunk := stream.read(_CHUNK_SIZE):
        yield chunk


def build_object_proxy_router(*, reader: ObjectReader, secret: str) -> APIRouter:
    """Return a router serving `GET {OBJECT_PROXY_PATH}/{key}?token=…`.

    Mount it under the application's API prefix, and only when the configured
    `url_strategy` is `proxy`.
    """

    router = APIRouter()

    # Sync handler on purpose: content stores are blocking (MinIO/GCS/disk), so
    # FastAPI runs the whole route in a worker thread instead of stalling the loop.
    @router.get(f"{OBJECT_PROXY_PATH}/{{object_key:path}}", include_in_schema=False)
    def serve_object(
        object_key: str,
        token: str = Query(default=""),
        range_header: Optional[str] = Header(default=None, alias="Range"),
    ) -> StreamingResponse:
        key = _validate_key(object_key)
        if not verify_signed_token(token, [key], secret=secret):
            # Never echo the token, and do not distinguish "expired" from "forged".
            logger.info(
                "[CONTENT][PROXY] refused object key=%s: invalid or expired signature",
                key,
            )
            raise HTTPException(status_code=403, detail="Invalid or expired object URL")

        try:
            info = reader.stat_object(key)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Object not found") from exc

        total_size = info.size
        media_type = info.content_type or "application/octet-stream"
        remaining_ttl = max((token_expiry(token) or 0) - int(time.time()), 0)
        headers: dict[str, str] = {
            "Accept-Ranges": "bytes",
            # Cache no longer than the capability itself; `private` (not `public`)
            # keeps a bearer URL out of shared proxy caches (RFC §2.4).
            "Cache-Control": f"private, max-age={remaining_ttl}",
        }
        if info.etag:
            headers["ETag"] = (
                info.etag if info.etag.startswith('"') else f'"{info.etag}"'
            )

        window = _parse_range(range_header)
        if window is None:
            stream = reader.get_object_stream(key)
            headers["Content-Length"] = str(total_size)
            return StreamingResponse(
                content=_chunks(stream),
                media_type=media_type,
                headers=headers,
                status_code=200,
                background=BackgroundTask(getattr(stream, "close", lambda: None)),
            )

        start, end = window
        if start is None and end is not None:
            # Suffix form `bytes=-N`
            if end <= 0:
                headers["Content-Range"] = f"bytes */{total_size}"
                raise HTTPException(
                    status_code=416, detail="Range Not Satisfiable", headers=headers
                )
            start = max(total_size - end, 0)
            end = total_size - 1
        else:
            if start is None or start >= total_size:
                headers["Content-Range"] = f"bytes */{total_size}"
                raise HTTPException(
                    status_code=416, detail="Range Not Satisfiable", headers=headers
                )
            end = total_size - 1 if end is None else min(end, total_size - 1)
            if end < start:
                headers["Content-Range"] = f"bytes */{total_size}"
                raise HTTPException(
                    status_code=416, detail="Range Not Satisfiable", headers=headers
                )

        length = end - start + 1
        stream = reader.get_object_stream(key, start=start, length=length)
        headers["Content-Range"] = f"bytes {start}-{end}/{total_size}"
        # No Content-Length on 206: avoids a server error when a client aborts early.
        return StreamingResponse(
            content=_chunks(stream),
            media_type=media_type,
            headers=headers,
            status_code=206,
            background=BackgroundTask(getattr(stream, "close", lambda: None)),
        )

    return router
