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

import logging
import time
from typing import Callable, Optional, Union

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from fred_core.kpi.base_kpi_writer import BaseKPIWriter
from fred_core.kpi.kpi_writer_structures import KPIActor
from fred_core.security.oidc import decode_jwt

logger = logging.getLogger(__name__)

# Paths whose suffixes are skipped — health and readiness probes add no analytics value.
_SKIP_SUFFIXES = ("/healthz", "/ready")

KPIWriterSource = Union[BaseKPIWriter, Callable[[], BaseKPIWriter]]


class KPIMiddleware(BaseHTTPMiddleware):
    """FastAPI/Starlette middleware that emits api.request_latency_ms for every request.

    Replaces prometheus_fastapi_instrumentator. Mount once per backend via:
        app.add_middleware(KPIMiddleware, kpi=<writer>)

    `kpi` can be a BaseKPIWriter instance (eager) or a zero-arg callable that
    returns one (lazy — for backends where the writer is initialised in lifespan).
    """

    def __init__(self, app, kpi: KPIWriterSource) -> None:
        super().__init__(app)
        self._kpi_source = kpi

    def _get_kpi(self) -> BaseKPIWriter:
        if callable(self._kpi_source) and not isinstance(
            self._kpi_source, BaseKPIWriter
        ):
            return self._kpi_source()
        return self._kpi_source  # type: ignore[return-value]

    async def dispatch(self, request: Request, call_next):
        if request.url.path.endswith(_SKIP_SUFFIXES):
            return await call_next(request)

        t0 = time.perf_counter()
        response: Optional[Response] = None
        exc_type: Optional[str] = None
        try:
            response = await call_next(request)
            return response
        except Exception as exc:
            exc_type = type(exc).__name__
            raise
        finally:
            latency_ms = (time.perf_counter() - t0) * 1000
            http_status = response.status_code if response is not None else 500
            # Use templated route path to avoid high-cardinality dims (e.g. /users/{id}).
            # Falls back to raw path only for unmatched routes (404s).
            route = getattr(request.scope.get("route"), "path", request.url.path)
            user_id = _extract_user_id(request)
            extra_dims: dict[str, str | None] | None = None
            if user_id:
                actor = KPIActor(type="human", user_id=user_id)
            else:
                # Unauthenticated call (pre-login browser request, public probe).
                # KPIActor has no "anonymous" type, so we use type="system" and
                # tag actor_subtype="anonymous" so OpenSearch can distinguish these
                # from real internal system calls.
                actor = KPIActor(type="system")
                extra_dims = {"actor_subtype": "anonymous"}
            try:
                self._get_kpi().api_call(
                    route=route,
                    method=request.method,
                    latency_ms=latency_ms,
                    http_status=http_status,
                    error_code=None,
                    exception_type=exc_type,
                    extra_dims=extra_dims,
                    actor=actor,
                    scope_type=None,
                    scope_id=None,
                )
            except Exception:
                # KPI failures must never abort a request.
                logger.debug("KPIMiddleware: failed to emit metric", exc_info=True)


def _extract_user_id(request: Request) -> Optional[str]:
    """Extract the JWT sub claim from the Authorization header without raising."""
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        user = decode_jwt(auth.split(" ", 1)[1])
        return user.uid
    except Exception:
        return None
