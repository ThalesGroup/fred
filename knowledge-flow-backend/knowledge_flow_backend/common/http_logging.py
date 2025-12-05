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
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("http")

# Only log slow requests and errors at INFO/above. Routine probes stay at DEBUG.
SLOW_THRESHOLD_MS = 500  # tweak if you want more/less verbosity


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
        t0 = time.perf_counter()
        path = request.url.path
        hdrs = {k.lower(): v for k, v in request.headers.items()}
        auth_info = _jwt_preview(hdrs.get("authorization"))

        # Downgrade noisy probes to DEBUG
        is_probe = path.endswith("/healthz") or path.endswith("/ready")
        if not is_probe:
            logger.debug(
                ">>> %s %s qs='%s' client=%s auth=%s",
                request.method,
                path,
                request.url.query,
                request.client.host if request.client else None,
                auth_info,
            )

        response: Response = await call_next(request)

        dt_ms = (time.perf_counter() - t0) * 1000
        is_redirect = response.status_code in (301, 302, 303, 307, 308)
        location = response.headers.get("location")

        # Only surface slow or failing requests above DEBUG
        if response.status_code >= 500:
            level = logging.ERROR
        elif response.status_code >= 400:
            level = logging.WARNING
        elif dt_ms >= SLOW_THRESHOLD_MS:
            level = logging.INFO
        elif is_probe:
            level = logging.DEBUG
        else:
            # Routine 2xx/3xx under the threshold stay at DEBUG to avoid noise
            level = logging.DEBUG

        logger.log(
            level,
            "<<< %s %s status=%s ms=%.1f redirect=%s location=%s",
            request.method,
            path,
            response.status_code,
            dt_ms,
            is_redirect,
            location,
        )
        return response
