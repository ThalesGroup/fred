# app/features/osops/controller.py
import logging
from typing import Any, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Path
from fred_core import KeycloakUser, get_current_user
from opensearchpy.exceptions import TransportError  # ← surface OS error details

from app.application_context import get_app_context

logger = logging.getLogger(__name__)


class OpenSearchOpsController:
    """
    Read-only OpenSearch ops endpoints for MCP monitoring agents.

    Fred rationale:
    - MCP callers often know only the *index* when asking for an allocation explain.
      OpenSearch's API, however, requires (index, shard, primary) for POST requests.
    - To keep the API dev-friendly, we auto-pick a shard if the caller didn't pass one.
      This prevents the common 400 "shard must be specified; primary must be specified".
    - We also surface the underlying OpenSearch error text up to the MCP layer so agents
      (and humans) see the real cause without diving into server logs.
    """

    def __init__(
        self,
        router: APIRouter,
    ):
        self.client = get_app_context().get_opensearch_client()
        self.default_index_pattern = "*"

        def err(e: Exception) -> HTTPException:
            """
            Fred rationale:
            - Keep a single place that converts Python exceptions into HTTP errors.
            - If it's an OpenSearch TransportError, bubble up the OS message so MCP
              tools can display something actionable (privilege issue, bad arg, ...).
            """
            logger.error("[OSOPS] error: %s", e, exc_info=True)
            if isinstance(e, TransportError):
                status = getattr(e, "status_code", 500) or 500
                # e.error holds OS reason like 'action_request_validation_exception'
                return HTTPException(
                    status_code=status,
                    detail={"message": "OpenSearch error", "opensearch": getattr(e, "error", str(e))},
                )
            return HTTPException(status_code=500, detail={"message": "OpenSearch error", "exception": str(e)})

        # --- helper: choose a shard when only 'index' was provided ----------------
        def _pick_problem_shard(index: str) -> Optional[Tuple[str, int, bool]]:
            """
            Return (index, shard_number, is_primary) or None if no shards found.
            Prefers UNASSIGNED shards; otherwise returns the first shard.
            """
            shards = self.client.cat.shards(index=index, params={"format": "json"})
            if not isinstance(shards, list) or not shards:
                return None

            parsed: list[Tuple[str, int, bool, bool]] = []  # (idx, shard, is_primary, is_unassigned)
            for row in shards:
                idx: Any = row.get("index")
                sh: Any = row.get("shard")
                prirep: Any = row.get("prirep")
                state: Any = row.get("state")

                if not isinstance(idx, str):
                    continue
                try:
                    shard_num = int(sh)
                except Exception:
                    logger.warning("[OSOPS] failed to parse shard number: %s", sh)
                    continue

                is_primary = True if prirep == "p" else False
                is_unassigned = isinstance(state, str) and state.upper() == "UNASSIGNED"
                parsed.append((idx, shard_num, is_primary, is_unassigned))

            if not parsed:
                return None

            # Prefer UNASSIGNED
            for idx, shard_num, is_primary, is_unassigned in parsed:
                if is_unassigned:
                    return (idx, shard_num, is_primary)

            # Fallback: first shard
            first = parsed[0]
            return (first[0], first[1], first[2])

        # --------- cluster & health
        @router.get("/os/health", tags=["OpenSearch"], operation_id="os_health", summary="Cluster health")
        async def health(_: KeycloakUser = Depends(get_current_user)):
            try:
                return self.client.cluster.health()
            except Exception as e:
                raise err(e)

        @router.get("/os/pending_tasks", tags=["OpenSearch"], operation_id="os_pending_tasks", summary="Pending tasks")
        async def pending_tasks(_: KeycloakUser = Depends(get_current_user)):
            try:
                return self.client.cluster.pending_tasks()
            except Exception as e:
                raise err(e)

        @router.get(
            "/os/allocation/explain",
            tags=["OpenSearch"],
            operation_id="os_allocation_explain",
            summary="Shard allocation explanation",
        )
        async def allocation_explain(
            index: str | None = Query(None, description="Index name (optional)"),
            shard: int | None = Query(None, description="Shard number (optional)"),
            primary: bool | None = Query(None, description="Whether primary shard (optional)"),
            include_disk_info: bool = Query(True, description="Include disk info in explanation"),
            _: KeycloakUser = Depends(get_current_user),
        ):
            """
            Fred rationale:
            - Case 1: (index, shard, primary) provided → call POST as-is.
            - Case 2: only index provided → auto-pick a shard then POST.
            - Case 3: nothing provided → emulate GET /_cluster/allocation/explain
              (OS chooses a random unassigned shard if any).
            """
            try:
                # Case 1: full specification
                if index and shard is not None and primary is not None:
                    body = {
                        "index": index,
                        "shard": shard,
                        "primary": primary,
                        "include_disk_info": include_disk_info,
                    }
                    return self.client.cluster.allocation_explain(body=body)

                # Case 2: only index -> choose shard for caller
                if index and (shard is None or primary is None):
                    picked = _pick_problem_shard(index)
                    if not picked:
                        raise HTTPException(
                            status_code=404,
                            detail={"message": "No shards to explain for index", "index": index},
                        )
                    idx, sh, prim = picked
                    body = {
                        "index": idx,
                        "shard": sh,
                        "primary": prim,
                        "include_disk_info": include_disk_info,
                    }
                    return self.client.cluster.allocation_explain(body=body)

                # Case 3: nothing -> let OpenSearch pick (GET variant, no body)
                # opensearch-py doesn't expose GET for this; go through transport.
                return self.client.transport.perform_request(
                    "GET",
                    "/_cluster/allocation/explain",
                    params={"include_disk_info": str(include_disk_info).lower()},
                )
            except HTTPException:
                raise
            except Exception as e:
                raise err(e)

        # --------- nodes
        @router.get("/os/nodes/stats", tags=["OpenSearch"], operation_id="os_nodes_stats", summary="Node stats")
        async def nodes_stats(metric: str = Query("_all"), _: KeycloakUser = Depends(get_current_user)):
            try:
                return self.client.nodes.stats(metric=metric)
            except Exception as e:
                raise err(e)

        # --------- indices
        @router.get("/os/indices", tags=["OpenSearch"], operation_id="os_indices", summary="List indices (cat.indices)")
        async def cat_indices(pattern: str = Query("*"), bytes: str = Query("mb"), _: KeycloakUser = Depends(get_current_user)):
            try:
                return self.client.cat.indices(index=pattern or self.default_index_pattern, params={"format": "json", "bytes": "mb"})
            except Exception as e:
                raise err(e)

        @router.get("/os/index/{index}/stats", tags=["OpenSearch"], operation_id="os_index_stats", summary="Index stats")
        async def index_stats(index: str = Path(...), _: KeycloakUser = Depends(get_current_user)):
            try:
                return self.client.indices.stats(index=index)
            except Exception as e:
                raise err(e)

        @router.get("/os/index/{index}/mapping", tags=["OpenSearch"], operation_id="os_index_mapping", summary="Index mapping")
        async def index_mapping(index: str = Path(...), _: KeycloakUser = Depends(get_current_user)):
            try:
                return self.client.indices.get_mapping(index=index)
            except Exception as e:
                raise err(e)

        @router.get("/os/index/{index}/settings", tags=["OpenSearch"], operation_id="os_index_settings", summary="Index settings")
        async def index_settings(index: str = Path(...), _: KeycloakUser = Depends(get_current_user)):
            try:
                return self.client.indices.get_settings(index=index)
            except Exception as e:
                raise err(e)

        # --------- shards
        @router.get("/os/shards", tags=["OpenSearch"], operation_id="os_shards", summary="Shards overview (cat.shards)")
        async def cat_shards(pattern: str = Query("*"), _: KeycloakUser = Depends(get_current_user)):
            try:
                return self.client.cat.shards(index=pattern, params={"format": "json", "bytes": "mb"})
            except Exception as e:
                raise err(e)

        # --------- quick green/yellow diagnostic
        @router.get("/os/diagnostics", tags=["OpenSearch"], operation_id="os_diagnostics", summary="Simple green/yellow/red summary")
        async def diagnostics(_: KeycloakUser = Depends(get_current_user)):
            try:
                health = self.client.cluster.health()
                shards = self.client.cat.shards(index="*", params={"format": "json"})
                red = [s for s in shards if s.get("state") == "UNASSIGNED"]
                yellow = [s for s in shards if s.get("prirep") == "r" and s.get("state") != "STARTED"]
                return {
                    "cluster_status": health.get("status"),
                    "unassigned_shards": len(red),
                    "replica_issues": len(yellow),
                    "active_primary_shards": health.get("active_primary_shards"),
                    "active_shards_percent": health.get("active_shards_percent_as_number"),
                }
            except Exception as e:
                raise err(e)
