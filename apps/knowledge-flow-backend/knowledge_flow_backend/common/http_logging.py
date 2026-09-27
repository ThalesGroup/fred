# Copyright Thales 2025
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

import base64
import json
import logging
import time
from typing import Any, Dict, Optional

from fastapi import Request, Response
from fred_core.security.delegation import GRANT_PARAM_NAMES, get_delegation_config
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("http")
SKIP_PATHS = frozenset({"/knowledge-flow/v1/healthz", "/knowledge-flow/v1/ready"})


def _query_without_grant(request: Request) -> str:
    """Return the query string with delegated identity parameters removed."""

    return str(request.query_params.__class__([(name, value) for name, value in request.query_params.multi_items() if name not in GRANT_PARAM_NAMES]))


def _jwt_preview(auth_header: Optional[str]) -> Dict[str, Any]:
    """Non-validating peek at JWT claims (never logs the token)."""
    if not auth_header or not auth_header.startswith("Bearer "):
        return {"present": False}
    token = auth_header.split(" ", 1)[1]
    parts = token.split(".")
    if len(parts) != 3:
        return {"present": True, "malformed": True}
    try:
        payload = parts[1] + "=="
        data = json.loads(base64.urlsafe_b64decode(payload))
        keep = {k: data.get(k) for k in ("iss", "sub", "aud", "azp", "exp", "nbf")}
        return {"present": True, "claims": keep}
    except Exception as e:
        return {"present": True, "decode_error": str(e)}


class RequestResponseLogger(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        skip_logging = request.url.path in SKIP_PATHS
        delegated_request = get_delegation_config().in_use
        method = request.method if request.method in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"} else "OTHER"
        t0 = time.perf_counter()
        if not skip_logging:
            if delegated_request:
                logger.debug(
                    "http event=delegated_request outcome=started method=%s",
                    method,
                )
            else:
                hdrs = {k.lower(): v for k, v in request.headers.items()}
                auth_info = _jwt_preview(hdrs.get("authorization"))
                logger.debug(
                    ">>> %s %s qs='%s' client=%s auth=%s",
                    request.method,
                    request.url.path,
                    _query_without_grant(request),
                    request.client.host if request.client else None,
                    auth_info,
                )
        try:
            response: Response = await call_next(request)
        except Exception:
            if not skip_logging and delegated_request:
                logger.info(
                    "http event=delegated_request outcome=failed method=%s",
                    method,
                )
            raise
        dt = (time.perf_counter() - t0) * 1000
        is_redirect = response.status_code in (301, 302, 303, 307, 308)
        location = response.headers.get("location")
        if not skip_logging:
            if delegated_request:
                logger.info(
                    "http event=delegated_request outcome=completed method=%s status=%s",
                    method,
                    response.status_code,
                )
            else:
                logger.info(f"<<< {request.method} {request.url.path} status={response.status_code} ms={dt:.1f} redirect={is_redirect} location={location}")
        return response
