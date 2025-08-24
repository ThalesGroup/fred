# app/features/osops/controller.py
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from fred_core import KeycloakUser, get_current_user

from app.application_context import get_app_context

logger = logging.getLogger(__name__)

class OpenSearchOpsController:
    """
    Read-only OpenSearch ops endpoints for MCP monitoring agents.
    """

    def __init__(
        self,
        router: APIRouter,
    ):
        self.client = get_app_context().get_opensearch_client() 
        self.default_index_pattern ="*"

        def err(e: Exception) -> HTTPException:
            logger.error(f"[OSOPS] error: {e}", exc_info=True)
            return HTTPException(status_code=500, detail="OpenSearch error")

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

        @router.get("/os/allocation/explain", tags=["OpenSearch"], operation_id="os_allocation_explain", summary="Shard allocation explanation")
        async def allocation_explain(index: str | None = Query(None), _: KeycloakUser = Depends(get_current_user)):
            try:
                body = {"index": index} if index else {}
                return self.client.cluster.allocation_explain(body=body)
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
