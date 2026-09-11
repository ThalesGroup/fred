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

"""One translation from a service exception to an HTTP response."""

from __future__ import annotations

from fastapi import HTTPException
from fred_core.security.models import AuthorizationError


def map_error(exc: Exception) -> HTTPException:
    """Map a service exception to its HTTP status, or re-raise it.

    Service exceptions carry their own `http_status`; anything without one is
    a bug rather than a client error, so it is re-raised and surfaces as a 500
    instead of being flattened into a misleading 4xx. Shared so two admin
    surfaces cannot drift into different status codes for the same exception.
    """

    if isinstance(exc, AuthorizationError):
        return HTTPException(status_code=403, detail=str(exc))
    status = getattr(exc, "http_status", None)
    if isinstance(status, int):
        return HTTPException(status_code=status, detail=str(exc))
    raise exc
