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

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fred_core import (
    ORGANIZATION_ID,
    KeycloakUser,
    LogQuery,
    LogQueryResult,
    OrganizationPermission,
    get_current_user,
)

from knowledge_flow_backend.application_context import get_app_context, get_rebac_engine
from knowledge_flow_backend.common.utils import log_exception

# --- Module-level router (MCP-friendly) ---
router = APIRouter(tags=["Logs"])

# --- I/O models kept tiny and explicit ---


def handle_exception(e: Exception) -> HTTPException | Exception:
    # Keep this open for future domain errors (e.g., LogStoreUnavailable)
    return HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# POST /mcp/logs/query
# - Primary entry point for the UI: time-window + filters via the LogStore.
# - Mirrors KPI controller shape so devs recognize the pattern instantly.
# ---------------------------------------------------------------------------
@router.post(
    "/logs/query",
    summary="Query logs via the configured LogStore (RAM/OpenSearch)",
    response_model=LogQueryResult,
)
async def query_logs(
    body: LogQuery,
    user: KeycloakUser = Depends(get_current_user),
):
    """
    Fred rationale:
    - Controllers stay skinny; query is delegated to the store.
    - Store is chosen by ApplicationContext (RAM for dev, OpenSearch for prod).
    - Authorization: unlike KPIs, logs have no per-user "personal scope" —
      every query is a platform-wide view across all users and services, so
      it requires CAN_OBSERVE_PLATFORM unconditionally (same capability that
      gates KPIController's `view_global` branch and `/admin/analytics`; see
      docs/swift/platform/OBSERVABILITY-AND-AUDIT.md §6).
    """
    # Outside the try/except below: an AuthorizationError must reach FastAPI's
    # registered handler as a 403, not get folded into this endpoint's
    # generic 500 (see register_exception_handlers).
    await get_rebac_engine().check_user_permission_or_raise(user, OrganizationPermission.CAN_OBSERVE_PLATFORM, ORGANIZATION_ID)
    try:
        store = get_app_context().get_log_store()
        return store.query(body)
    except Exception as e:
        log_exception(e)
        raise handle_exception(e)
