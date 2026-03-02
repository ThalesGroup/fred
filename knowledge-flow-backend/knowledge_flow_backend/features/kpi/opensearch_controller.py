# app/features/osops/controller.py
import logging
from typing import Any, Optional, Tuple
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fred_core import Action, KeycloakUser, Resource, authorize_or_raise, get_current_user
from opensearchpy.exceptions import TransportError  # ← surface OS error details

from knowledge_flow_backend.application_context import get_app_context

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

        def err(e: Exception) -> HTTPException | Exception:
            """
            If it's an OpenSearch TransportError, bubble up the OS message so MCP
            tools can display something actionable (privilege issue, bad arg, ...).
            """
            logger.error("[OSOPS] error: %s", e, exc_info=True)
            if isinstance(e, TransportError):
                raw_status = getattr(e, "status_code", 500)
                try:
                    status = int(raw_status) if raw_status is not None else 500
                except (TypeError, ValueError):
                    status = 500
                # e.error holds OS reason like 'action_request_validation_exception'
                return HTTPException(
                    status_code=status,
                    detail={"message": "OpenSearch error", "opensearch": getattr(e, "error", str(e))},
                )

            return e  # Will be handled by generic_exception_handler as 500

        def _build_query_params(**params: Any) -> dict[str, Any]:
            """
            Remove None values and serialize booleans the way OpenSearch expects
            in query params ("true"/"false").
            """
            cleaned: dict[str, Any] = {}
            for key, value in params.items():
                if value is None:
                    continue
                cleaned[key] = str(value).lower() if isinstance(value, bool) else value
            return cleaned

        def _opensearch_get_with_sanitized_params(path: str, params: Optional[dict[str, Any]] = None) -> Any:
            """
            opensearch-py's low-level transport treats a query param named "timeout"
            as a client-side request timeout (expects int/float), which collides with
            several OpenSearch APIs that legitimately use a string query param like "5s".

            To preserve the API-level `timeout` query param, encode it in the URL and
            send the remaining params normally.
            """
            params = dict(params or {})
            api_timeout = params.pop("timeout", None)
            if api_timeout is not None:
                # If we pass remaining params via `params=...`, opensearch-py will append
                # another "?" and produce malformed URLs like `...?timeout=5s?detailed=true`.
                # Encode the whole query string in the path in this specific case.
                all_query = {"timeout": api_timeout, **params}
                sep = "&" if "?" in path else "?"
                path = f"{path}{sep}{urlencode(all_query)}"
                params = None
            return self.client.transport.perform_request("GET", path, params=params)

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
        @router.get(
            "/os/health",
            tags=["OpenSearch"],
            operation_id="os_health",
            summary="Cluster health",
            description=(
                "Quick cluster-wide health snapshot. Returns the health color (green/yellow/red), "
                "shard counts, node counts, and other top-level allocation indicators. "
                "Use this first for triage before calling heavier endpoints such as cluster state."
            ),
        )
        async def health(user: KeycloakUser = Depends(get_current_user)):
            authorize_or_raise(user, Action.READ, Resource.OPENSEARCH)

            try:
                return self.client.cluster.health()
            except Exception as e:
                raise err(e)

        @router.get(
            "/os/pending_tasks",
            tags=["OpenSearch"],
            operation_id="os_pending_tasks",
            summary="Pending tasks",
            description=(
                "Returns pending cluster coordination tasks (cluster-state update queue), not the generic "
                "runtime task API. Useful when the cluster-manager/master is slow or when allocation/settings "
                "changes appear stuck."
            ),
        )
        async def pending_tasks(user: KeycloakUser = Depends(get_current_user)):
            authorize_or_raise(user, Action.READ, Resource.OPENSEARCH)

            try:
                return self.client.cluster.pending_tasks()
            except Exception as e:
                raise err(e)

        @router.get(
            "/os/cluster/settings",
            tags=["OpenSearch"],
            operation_id="os_cluster_settings",
            summary="Cluster settings (persistent/transient/defaults)",
            description=(
                "Reads effective cluster settings for debugging routing, allocation, disk watermarks, "
                "rebalance behavior, and other cluster-wide controls. By default this wrapper includes "
                "defaults and flattens nested keys so agents can inspect values easily."
            ),
        )
        async def cluster_settings(
            include_defaults: bool = Query(True, description="Include default settings"),
            flat_settings: bool = Query(True, description="Flatten nested settings"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.OPENSEARCH)

            try:
                return self.client.transport.perform_request(
                    "GET",
                    "/_cluster/settings",
                    params=_build_query_params(include_defaults=include_defaults, flat_settings=flat_settings),
                )
            except Exception as e:
                raise err(e)

        @router.get(
            "/os/cluster/state",
            tags=["OpenSearch"],
            operation_id="os_cluster_state",
            summary="Cluster state (routing, metadata, blocks)",
            description=(
                "Low-level cluster state endpoint exposing routing tables, metadata, node definitions, "
                "and cluster blocks. This response can be very large on big clusters: prefer `metric`, "
                "`index`, and especially `filter_path` to reduce payload size when debugging."
            ),
        )
        async def cluster_state(
            metric: str = Query("_all", description="State metric(s), e.g. routing_table,metadata,nodes,blocks"),
            index: str | None = Query(None, description="Optional index expression for filtered state"),
            local: bool = Query(False, description="Read local node state instead of cluster-manager state"),
            filter_path: str | None = Query(None, description="Filter response fields to reduce payload size"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.OPENSEARCH)

            try:
                path = "/_cluster/state"
                if index:
                    metric_path = metric or "_all"
                    path = f"/_cluster/state/{metric_path}/{index}"
                elif metric and metric != "_all":
                    path = f"/_cluster/state/{metric}"

                return _opensearch_get_with_sanitized_params(path, _build_query_params(local=local, filter_path=filter_path))
            except Exception as e:
                raise err(e)

        @router.get(
            "/os/cluster/stats",
            tags=["OpenSearch"],
            operation_id="os_cluster_stats",
            summary="Cluster stats (nodes, indices, store, docs)",
            description=(
                "Aggregated operational statistics across the cluster (indices, docs, storage, node roles, "
                "versions, etc.). Use this for capacity and topology overview when `health` is not enough "
                "but you do not need the full cluster state payload."
            ),
        )
        async def cluster_stats(
            node_id: str | None = Query(None, description="Optional node id/name expression"),
            timeout: str | None = Query(None, description="Timeout, e.g. 5s"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.OPENSEARCH)

            try:
                path = "/_cluster/stats" if not node_id else f"/_cluster/stats/nodes/{node_id}"
                return _opensearch_get_with_sanitized_params(path, _build_query_params(timeout=timeout))
            except Exception as e:
                raise err(e)

        @router.get(
            "/os/allocation/explain",
            tags=["OpenSearch"],
            operation_id="os_allocation_explain",
            summary="Shard allocation explanation",
            description=(
                "Explains why a shard is or is not allocated. This wrapper is MCP-friendly: if only an "
                "index is provided, it automatically picks a shard (preferring UNASSIGNED) to avoid the "
                "common OpenSearch validation error requiring `shard` and `primary`. With no arguments, "
                "it delegates to the OpenSearch GET variant so the cluster can pick a problematic shard."
            ),
        )
        async def allocation_explain(
            index: str | None = Query(None, description="Index name (optional)"),
            shard: int | None = Query(None, description="Shard number (optional)"),
            primary: bool | None = Query(None, description="Whether primary shard (optional)"),
            include_disk_info: bool = Query(True, description="Include disk info in explanation"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            """
            Fred rationale:
            - Case 1: (index, shard, primary) provided → call POST as-is.
            - Case 2: only index provided → auto-pick a shard then POST.
            - Case 3: nothing provided → emulate GET /_cluster/allocation/explain
              (OS chooses a random unassigned shard if any).
            """
            authorize_or_raise(user, Action.READ, Resource.OPENSEARCH)

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
                return _opensearch_get_with_sanitized_params(
                    "/_cluster/allocation/explain",
                    {"include_disk_info": str(include_disk_info).lower()},
                )
            except HTTPException:
                raise
            except Exception as e:
                raise err(e)

        # --------- nodes
        @router.get(
            "/os/nodes/stats",
            tags=["OpenSearch"],
            operation_id="os_nodes_stats",
            summary="Node stats",
            description=(
                "Per-node runtime statistics (JVM, FS, thread pools, indexing/search counters, caches, "
                "transport/http, etc.) depending on the requested metric. Useful for performance and "
                "resource debugging; can be heavy when `metric=_all`."
            ),
        )
        async def nodes_stats(metric: str = Query("_all"), user: KeycloakUser = Depends(get_current_user)):
            authorize_or_raise(user, Action.READ, Resource.OPENSEARCH)

            try:
                return self.client.nodes.stats(metric=metric)
            except Exception as e:
                raise err(e)

        @router.get(
            "/os/nodes/info",
            tags=["OpenSearch"],
            operation_id="os_nodes_info",
            summary="Node info (roles, plugins, versions, settings)",
            description=(
                "Returns mostly static node metadata such as roles, versions, plugin list, node attributes, "
                "and configuration details. Use this to diagnose version/plugin mismatches, missing roles, "
                "or allocation attribute issues."
            ),
        )
        async def nodes_info(
            node_id: str | None = Query(None, description="Optional node id/name expression"),
            metric: str = Query("_all", description="Info metric(s), e.g. settings,os,jvm,process,plugins"),
            flat_settings: bool = Query(True, description="Flatten nested node settings"),
            timeout: str | None = Query(None, description="Timeout, e.g. 5s"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.OPENSEARCH)

            try:
                path = "/_nodes"
                if node_id and metric and metric != "_all":
                    path = f"/_nodes/{node_id}/{metric}"
                elif node_id:
                    path = f"/_nodes/{node_id}"
                elif metric and metric != "_all":
                    path = f"/_nodes/{metric}"

                return _opensearch_get_with_sanitized_params(path, _build_query_params(flat_settings=flat_settings, timeout=timeout))
            except Exception as e:
                raise err(e)

        @router.get(
            "/os/nodes/hot_threads",
            tags=["OpenSearch"],
            operation_id="os_nodes_hot_threads",
            summary="Hot threads (plain text wrapped in JSON)",
            description=(
                "Samples the hottest threads on one or more nodes to debug CPU spikes, blocking, or waiting "
                "threads. OpenSearch often returns plain text; this wrapper preserves it and wraps it in "
                'JSON as `{ "raw": ... }` when needed so MCP tools can display it safely.'
            ),
        )
        async def nodes_hot_threads(
            node_id: str | None = Query(None, description="Optional node id/name expression"),
            threads: int = Query(3, ge=1, le=9999, description="Number of hot threads to report"),
            snapshots: int = Query(10, ge=1, le=9999, description="Number of stack trace snapshots"),
            interval: str = Query("500ms", description="Sampling interval"),
            ignore_idle_threads: bool = Query(True, description="Skip idle threads"),
            type: str = Query("cpu", description="cpu|wait|block"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.OPENSEARCH)

            try:
                path = "/_nodes/hot_threads" if not node_id else f"/_nodes/{node_id}/hot_threads"
                resp = _opensearch_get_with_sanitized_params(
                    path,
                    _build_query_params(
                        threads=threads,
                        snapshots=snapshots,
                        interval=interval,
                        ignore_idle_threads=ignore_idle_threads,
                        type=type,
                    ),
                )
                if isinstance(resp, str):
                    return {"raw": resp}
                return resp
            except Exception as e:
                raise err(e)

        # --------- indices
        @router.get(
            "/os/indices",
            tags=["OpenSearch"],
            operation_id="os_indices",
            summary="List indices (cat.indices)",
            description=(
                "Compact index inventory based on `cat.indices`, useful for quick troubleshooting of "
                "document counts, storage usage, index health, and open/closed state across many indices. "
                "Prefer this over full index stats when you need a lightweight overview."
            ),
        )
        async def cat_indices(pattern: str = Query("*"), bytes: str = Query("mb"), user: KeycloakUser = Depends(get_current_user)):
            authorize_or_raise(user, Action.READ, Resource.OPENSEARCH)

            try:
                return self.client.cat.indices(index=pattern or self.default_index_pattern, params={"format": "json", "bytes": bytes})
            except Exception as e:
                raise err(e)

        @router.get(
            "/os/index/{index}/stats",
            tags=["OpenSearch"],
            operation_id="os_index_stats",
            summary="Index stats",
            description=(
                "Detailed index statistics for one index (docs, store, indexing/search activity, merges, "
                "refreshes, caches, segments, translog, etc.). Use this when `cat.indices` is not enough "
                "and you need root-cause detail for a specific index."
            ),
        )
        async def index_stats(index: str = Path(...), user: KeycloakUser = Depends(get_current_user)):
            authorize_or_raise(user, Action.READ, Resource.OPENSEARCH)

            try:
                return self.client.indices.stats(index=index)
            except Exception as e:
                raise err(e)

        @router.get(
            "/os/index/{index}/mapping",
            tags=["OpenSearch"],
            operation_id="os_index_mapping",
            summary="Index mapping",
            description=("Returns the mapping for a specific index. Use this to debug field types, multi-fields, dynamic mappings, and analyzer-related issues that break queries or aggregations."),
        )
        async def index_mapping(index: str = Path(...), user: KeycloakUser = Depends(get_current_user)):
            authorize_or_raise(user, Action.READ, Resource.OPENSEARCH)

            try:
                return self.client.indices.get_mapping(index=index)
            except Exception as e:
                raise err(e)

        @router.get(
            "/os/index/{index}/settings",
            tags=["OpenSearch"],
            operation_id="os_index_settings",
            summary="Index settings",
            description=(
                "Returns settings for a specific index (shards/replicas, refresh interval, allocation "
                "filters, lifecycle-related settings, analyzers, etc.). Useful for debugging unexpected "
                "performance, allocation, or indexing behavior on one index."
            ),
        )
        async def index_settings(index: str = Path(...), user: KeycloakUser = Depends(get_current_user)):
            authorize_or_raise(user, Action.READ, Resource.OPENSEARCH)

            try:
                return self.client.indices.get_settings(index=index)
            except Exception as e:
                raise err(e)

        @router.get(
            "/os/index/{index}/recovery",
            tags=["OpenSearch"],
            operation_id="os_index_recovery",
            summary="Index recovery details",
            description=(
                "Shows shard recovery progress for a specific index (including active recoveries and optional "
                "file-level details). Use this to diagnose slow allocation, relocation, or post-restart "
                "recovery for one problematic index."
            ),
        )
        async def index_recovery(
            index: str = Path(...),
            detailed: bool = Query(False, description="Include file-level details"),
            active_only: bool = Query(False, description="Only active recoveries"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.OPENSEARCH)

            try:
                return _opensearch_get_with_sanitized_params(f"/{index}/_recovery", _build_query_params(detailed=detailed, active_only=active_only))
            except Exception as e:
                raise err(e)

        # --------- tasks
        @router.get(
            "/os/tasks",
            tags=["OpenSearch"],
            operation_id="os_tasks",
            summary="Running tasks",
            description=(
                "Lists runtime tasks (`/_tasks`) such as searches, reindexing, snapshots, and internal "
                "operations. This is different from `/os/pending_tasks`, which only covers pending cluster "
                "coordination tasks. Use filters (`actions`, `nodes`, `parent_task_id`) to keep results focused."
            ),
        )
        async def tasks_list(
            detailed: bool = Query(False, description="Return detailed task information"),
            actions: str | None = Query(None, description="Action filters, e.g. *search,*reindex"),
            nodes: str | None = Query(None, description="Node id/name filters"),
            parent_task_id: str | None = Query(None, description="Filter by parent task id"),
            wait_for_completion: bool = Query(False, description="Wait until tasks finish"),
            timeout: str | None = Query(None, description="Wait timeout, e.g. 5s"),
            group_by: str = Query("nodes", description="Group by: nodes|parents|none"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.OPENSEARCH)

            try:
                return _opensearch_get_with_sanitized_params(
                    "/_tasks",
                    _build_query_params(
                        detailed=detailed,
                        actions=actions,
                        nodes=nodes,
                        parent_task_id=parent_task_id,
                        wait_for_completion=wait_for_completion,
                        timeout=timeout,
                        group_by=group_by,
                    ),
                )
            except Exception as e:
                raise err(e)

        @router.get(
            "/os/tasks/{task_id}",
            tags=["OpenSearch"],
            operation_id="os_task_get",
            summary="Task details",
            description=(
                "Fetches status/details for a single runtime task by id (`nodeId:taskNumber`). Useful after listing tasks to monitor progress, inspect errors, or optionally wait for completion."
            ),
        )
        async def task_get(
            task_id: str = Path(..., description="Task id in the form nodeId:taskNumber"),
            wait_for_completion: bool = Query(False, description="Wait until the task completes"),
            timeout: str | None = Query(None, description="Wait timeout, e.g. 10s"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.OPENSEARCH)

            try:
                return _opensearch_get_with_sanitized_params(
                    f"/_tasks/{task_id}",
                    _build_query_params(wait_for_completion=wait_for_completion, timeout=timeout),
                )
            except Exception as e:
                raise err(e)

        # --------- shards
        @router.get(
            "/os/shards",
            tags=["OpenSearch"],
            operation_id="os_shards",
            summary="Shards overview (cat.shards)",
            description=(
                "Compact shard-level view based on `cat.shards` across indices. Useful to quickly spot "
                "UNASSIGNED/INITIALIZING/RELOCATING shards and to identify which index and shard number "
                "should be investigated with allocation explain or recovery endpoints."
            ),
        )
        async def cat_shards(pattern: str = Query("*"), user: KeycloakUser = Depends(get_current_user)):
            authorize_or_raise(user, Action.READ, Resource.OPENSEARCH)

            try:
                return self.client.cat.shards(index=pattern, params={"format": "json", "bytes": "mb"})
            except Exception as e:
                raise err(e)

        @router.get(
            "/os/cat/nodes",
            tags=["OpenSearch"],
            operation_id="os_cat_nodes",
            summary="Nodes overview (cat.nodes)",
            description=(
                "Lightweight per-node operational summary (`cat.nodes`) for triage: CPU, heap, RAM/load, "
                "disk usage, roles, and basic health indicators depending on selected columns. Prefer this "
                "when you need a fast snapshot before fetching heavier node stats."
            ),
        )
        async def cat_nodes(
            bytes: str = Query("mb", description="Byte unit (b|kb|mb|gb|...)"),
            columns: str | None = Query(None, description="Column list (cat 'h' parameter)"),
            sort: str | None = Query(None, description="Sort columns (cat 's' parameter)"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.OPENSEARCH)

            try:
                return _opensearch_get_with_sanitized_params("/_cat/nodes", _build_query_params(format="json", bytes=bytes, h=columns, s=sort))
            except TransportError as e:
                # Some OpenSearch versions reject sort keys that the agent may infer from
                # displayed column names (e.g. `disk.percent`). Return an unsorted view
                # instead of failing the whole tool call.
                if sort and getattr(e, "error", None) == "unsupported_operation_exception":
                    if "Unable to sort by unknown sort key" in str(e):
                        logger.warning("[OSOPS] cat.nodes unsupported sort key '%s'; retrying without sort", sort)
                        try:
                            return _opensearch_get_with_sanitized_params("/_cat/nodes", _build_query_params(format="json", bytes=bytes, h=columns))
                        except Exception as retry_e:
                            raise err(retry_e)
                raise err(e)
            except Exception as e:
                raise err(e)

        @router.get(
            "/os/cat/allocation",
            tags=["OpenSearch"],
            operation_id="os_cat_allocation",
            summary="Shard allocation overview (cat.allocation)",
            description=(
                "Shows shard distribution and disk usage per node (`cat.allocation`). This is one of the most "
                "useful endpoints when debugging unassigned shards, disk watermarks, and cluster imbalance."
            ),
        )
        async def cat_allocation(
            node: str | None = Query(None, description="Optional node name/id filter"),
            bytes: str = Query("mb", description="Byte unit (b|kb|mb|gb|...)"),
            columns: str | None = Query(None, description="Column list (cat 'h' parameter)"),
            sort: str | None = Query(None, description="Sort columns (cat 's' parameter)"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.OPENSEARCH)

            try:
                path = "/_cat/allocation" if not node else f"/_cat/allocation/{node}"
                return _opensearch_get_with_sanitized_params(path, _build_query_params(format="json", bytes=bytes, h=columns, s=sort))
            except Exception as e:
                raise err(e)

        @router.get(
            "/os/cat/thread_pool",
            tags=["OpenSearch"],
            operation_id="os_cat_thread_pool",
            summary="Thread pools overview (cat.thread_pool)",
            description=(
                "Compact thread-pool view (`cat.thread_pool`) to inspect queue size, active threads, completed "
                "tasks, and rejections by pool. Use this to identify saturation in pools like `search`, `write`, "
                "or `management` during incidents."
            ),
        )
        async def cat_thread_pool(
            node_id: str | None = Query(None, description="Optional node id/name expression"),
            columns: str | None = Query(None, description="Column list (cat 'h' parameter)"),
            sort: str | None = Query(None, description="Sort columns (cat 's' parameter)"),
            thread_pool_patterns: str | None = Query(None, description="Thread pool name patterns, comma-separated"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.OPENSEARCH)

            try:
                path = "/_cat/thread_pool"
                if node_id and thread_pool_patterns:
                    path = f"/_cat/thread_pool/{node_id}/{thread_pool_patterns}"
                elif node_id:
                    path = f"/_cat/thread_pool/{node_id}"
                elif thread_pool_patterns:
                    path = f"/_cat/thread_pool/{thread_pool_patterns}"

                return _opensearch_get_with_sanitized_params(path, _build_query_params(format="json", h=columns, s=sort))
            except Exception as e:
                raise err(e)

        @router.get(
            "/os/recovery",
            tags=["OpenSearch"],
            operation_id="os_recovery",
            summary="Cluster recovery details",
            description=(
                "Cluster-wide shard recovery view (`/_recovery`) across indices. Use this to debug slow "
                "startup/restart recovery, relocations, or replica catch-up. `detailed=true` may return "
                "large payloads because it includes file-level information."
            ),
        )
        async def recovery(
            detailed: bool = Query(False, description="Include file-level details"),
            active_only: bool = Query(False, description="Only active recoveries"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.OPENSEARCH)

            try:
                return _opensearch_get_with_sanitized_params("/_recovery", _build_query_params(detailed=detailed, active_only=active_only))
            except Exception as e:
                raise err(e)

        # --------- quick green/yellow diagnostic
        @router.get(
            "/os/diagnostics",
            tags=["OpenSearch"],
            operation_id="os_diagnostics",
            summary="Simple green/yellow/red summary",
            description=(
                "Very lightweight derived summary computed by this service from cluster health and shard state. "
                "It reports basic counts for unassigned shards and replica issues for quick MCP triage. "
                "It is intentionally simplified and should not replace detailed endpoints like allocation "
                "explain, recovery, or thread-pool diagnostics."
            ),
        )
        async def diagnostics(user: KeycloakUser = Depends(get_current_user)):
            authorize_or_raise(user, Action.READ, Resource.OPENSEARCH)

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
