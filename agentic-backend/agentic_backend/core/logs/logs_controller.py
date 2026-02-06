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
    Action,
    KeycloakUser,
    LogQuery,
    LogQueryResult,
    Resource,
    authorize_or_raise,
    get_current_user,
)

from agentic_backend.application_context import get_app_context
from agentic_backend.common.utils import log_exception

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
    - Authorization aligns with KPI: READ on Resource.LOGS.
    """
    try:
        authorize_or_raise(user, Action.READ, Resource.LOGS)
        store = get_app_context().get_log_store()
        return store.query(body)
    except Exception as e:
        log_exception(e)
        raise handle_exception(e)
