import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fred_core import Action, KeycloakUser, Resource, authorize_or_raise, get_current_user
from neo4j import Driver
from pydantic import BaseModel

from knowledge_flow_backend.application_context import get_app_context

logger = logging.getLogger(__name__)


class CypherQueryRequest(BaseModel):
    query: str
    parameters: Optional[Dict[str, Any]] = None
    database: Optional[str] = None
    limit: Optional[int] = None


class Neo4jController:
    """
    Read-only Neo4j exploration endpoints for MCP agents.

    Design goals:
    - Provide safe, read-oriented access to graph data for agents.
    - Offer simple schema discovery helpers (labels, relationship types).
    - Support parameterized Cypher queries with basic write-guarding.
    - Keep configuration minimal: rely on NEO4J_URI / NEO4J_USERNAME / NEO4J_PASSWORD env vars.
    """

    def __init__(self, router: APIRouter):
        # Lazily obtained driver from ApplicationContext so we share connections.
        self.driver: Driver = get_app_context().get_neo4j_driver()

        def run_read(query: str, parameters: Optional[Dict[str, Any]] = None, database: Optional[str] = None) -> List[Dict[str, Any]]:
            """Execute a read-only Cypher query and return list of dict records."""
            try:
                with self.driver.session(database=database) as session:
                    result = session.run(query, parameters or {})
                    # Convert to plain dicts for JSON serialization
                    return [record.data() for record in result]
            except Exception as e:  # noqa: BLE001
                logger.error("[NEO4J] query failed: %s", e, exc_info=True)
                raise HTTPException(status_code=500, detail={"message": "Neo4j query failed", "error": str(e)})

        def ensure_read_only(query: str) -> None:
            """
            Basic guardrail to prevent obvious write operations.

            This is intentionally conservative: anything containing common write
            keywords is rejected so that this MCP remains read-only.
            """
            upper = " ".join(query.upper().split())
            forbidden = [" CREATE ", " MERGE ", " DELETE ", " SET ", " DROP ", " REMOVE ", " CALL DBMS", " CALL APOC."]
            if any(token in upper for token in forbidden):
                raise HTTPException(
                    status_code=400,
                    detail={
                        "message": "Write operations are not allowed via this Neo4j MCP endpoint.",
                        "hint": "Restrict queries to MATCH/RETURN/UNWIND/WITH and other read-only patterns.",
                    },
                )

        @router.get(
            "/neo4j/health",
            tags=["Neo4j"],
            operation_id="neo4j_health",
            summary="Neo4j connectivity check",
        )
        async def health(user: KeycloakUser = Depends(get_current_user)):
            """
            Lightweight connectivity probe for Neo4j.

            Runs a trivial MATCH to ensure the driver can connect and run read queries.
            """
            authorize_or_raise(user, Action.READ, Resource.NEO4J)

            try:
                records = run_read("MATCH (n) RETURN count(n) AS node_count LIMIT 1")
                count = records[0]["node_count"] if records else 0
                return {"status": "ok", "node_count_sample": count}
            except HTTPException:
                raise
            except Exception as e:  # noqa: BLE001
                logger.error("[NEO4J] health check failed: %s", e, exc_info=True)
                raise HTTPException(status_code=500, detail={"message": "Neo4j health check failed", "error": str(e)})

        @router.get(
            "/neo4j/labels",
            tags=["Neo4j"],
            operation_id="neo4j_labels",
            summary="List node labels",
        )
        async def list_labels(
            database: Optional[str] = Query(None, description="Optional target database"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.NEO4J)

            rows = run_read("CALL db.labels() YIELD label RETURN label ORDER BY label", database=database)
            return {"labels": [row["label"] for row in rows]}

        @router.get(
            "/neo4j/relationship-types",
            tags=["Neo4j"],
            operation_id="neo4j_relationship_types",
            summary="List relationship types",
        )
        async def list_relationship_types(
            database: Optional[str] = Query(None, description="Optional target database"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.NEO4J)

            rows = run_read("CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType ORDER BY relationshipType", database=database)
            return {"relationship_types": [row["relationshipType"] for row in rows]}

        @router.get(
            "/neo4j/sample-neighbors",
            tags=["Neo4j"],
            operation_id="neo4j_sample_neighbors",
            summary="Sample neighbors around nodes matching a pattern",
        )
        async def sample_neighbors(
            label: str = Query(..., description="Label of starting nodes, e.g. 'Person'"),
            limit: int = Query(25, ge=1, le=200, description="Maximum number of paths to return"),
            database: Optional[str] = Query(None, description="Optional target database"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            """
            Sample a small neighborhood subgraph for visualization and exploration.

            Returns simple JSON nodes/relationships that MCP tools can render or analyze.
            """
            authorize_or_raise(user, Action.READ, Resource.NEO4J)

            cypher = """
            MATCH (n:`%s`)-[r]-(m)
            RETURN DISTINCT
                id(n) AS source_id,
                labels(n) AS source_labels,
                n AS source_properties,
                type(r) AS rel_type,
                id(r) AS rel_id,
                id(m) AS target_id,
                labels(m) AS target_labels,
                m AS target_properties
            LIMIT $limit
            """ % label.replace(
                "`", "``"
            )

            rows = run_read(cypher, parameters={"limit": limit}, database=database)

            nodes: Dict[int, Dict[str, Any]] = {}
            relationships: List[Dict[str, Any]] = []

            for row in rows:
                sid = row["source_id"]
                tid = row["target_id"]
                if sid not in nodes:
                    nodes[sid] = {
                        "id": sid,
                        "labels": row.get("source_labels", []),
                        "properties": dict(row.get("source_properties", {})),
                    }
                if tid not in nodes:
                    nodes[tid] = {
                        "id": tid,
                        "labels": row.get("target_labels", []),
                        "properties": dict(row.get("target_properties", {})),
                    }
                relationships.append(
                    {
                        "id": row["rel_id"],
                        "type": row["rel_type"],
                        "source_id": sid,
                        "target_id": tid,
                    }
                )

            return {"nodes": list(nodes.values()), "relationships": relationships}

        @router.post(
            "/neo4j/query",
            tags=["Neo4j"],
            operation_id="neo4j_query",
            summary="Run a read-only Cypher query",
        )
        async def cypher_query(body: CypherQueryRequest, user: KeycloakUser = Depends(get_current_user)):
            """
            Execute a parameterized, read-only Cypher query.

            Notes:
            - Write operations (CREATE/MERGE/DELETE/SET/DROP/REMOVE/DBMS/APOC writes) are rejected.
            - Use this for MATCH/RETURN-style graph exploration and analytics.
            """
            authorize_or_raise(user, Action.READ, Resource.NEO4J)
            ensure_read_only(body.query)

            rows = run_read(body.query, parameters=body.parameters, database=body.database)
            if body.limit is not None and body.limit >= 0:
                rows = rows[: body.limit]
            return {"rows": rows}
