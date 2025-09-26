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

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fred_core import KeycloakUser, get_current_user, Action, Resource, authorize_or_raise
from fred_core.logs import (
    LogQuery,
    LogQueryResult,
    TailFileResponse
)

from app.common.utils import log_exception
from app.application_context import get_app_context

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


# ---------------------------------------------------------------------------
# GET /mcp/logs/tail
# - Pragmatic "micro-tail" straight from the rotating JSON log file under
#   ~/.fred/agentic.logs/<service>.log
# - Complements /mcp/logs/query; handy when the store is disabled in dev.
# ---------------------------------------------------------------------------
@router.get(
    "/logs/tail",
    summary="Tail the local rolling JSON log file (best-effort)",
    response_model=TailFileResponse,
)
async def tail_logs_file(
    service: str = Query(..., description="Service name, e.g. 'agentic-backend' or 'knowledge-flow'"),
    bytes_back: int = Query(50_000, ge=1_000, le=5_000_000, description="How many bytes from file end to read"),
    user: KeycloakUser = Depends(get_current_user),
):
    """
    Fred rationale:
    - Not all environments wire a store; file tail gives 'what is on disk now'.
    - We return *raw lines* (each a JSON log) to avoid controller-side parsing cost.
    """
    try:
        authorize_or_raise(user, Action.READ, Resource.LOGS)

        log_path = Path.home() / ".fred" / "agentic.logs" / f"{service}.log"
        if not log_path.exists():
            return TailFileResponse(lines=[])

        size = log_path.stat().st_size
        start = max(0, size - bytes_back)
        lines: list[str] = []

        with log_path.open("rb") as f:
            f.seek(start)
            chunk = f.read()

        # Each line is a JSON object written by CompactJsonFormatter
        for raw in chunk.splitlines():
            try:
                # Keep a stable UTF-8 decode; skip partial/broken lines on rotation.
                s = raw.decode("utf-8", errors="strict")
                # Optional sanity check: only keep well-formed JSON lines
                json.loads(s)
                lines.append(s)
            except Exception:
                # Best-effort: ignore decode/JSON errors (rotation/races)
                continue

        return TailFileResponse(lines=lines)
    except Exception as e:
        log_exception(e)
        raise handle_exception(e)
