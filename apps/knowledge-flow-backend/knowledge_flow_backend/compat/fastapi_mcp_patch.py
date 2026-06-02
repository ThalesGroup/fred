"""
Monkey patches for fastapi_mcp.

Patch 1 — Schema resolver infinite recursion fix.
    See https://github.com/tadata-org/fastapi_mcp/pull/156 for upstream fix.

Patch 2 — Force stateless HTTP transport for horizontal scaling.
    fastapi-mcp hardcodes stateless=False in FastApiHttpSessionManager,
    which stores MCP sessions in-memory on a single pod.  When Kubernetes
    load-balances across multiple KnowledgeFlow pods, a request may land on a
    pod that doesn't own the session -> HTTP 400.

TODO: Remove this file once the project depends on releases that include these fixes.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional, Set

from fastapi_mcp.openapi import utils as fastapi_mcp_utils
from fastapi_mcp.transport.http import FastApiHttpSessionManager
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Patch 1 — Schema resolver infinite recursion fix
# ---------------------------------------------------------------------------


def resolve_schema_references(
    schema_part: Dict[str, Any],
    reference_schema: Dict[str, Any],
    seen: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """
    Resolve schema references in OpenAPI schemas.

    Args:
        schema_part: The part of the schema being processed that may contain references
        reference_schema: The complete schema used to resolve references from
        seen: A set of already seen references to avoid infinite recursion

    Returns:
        The schema with references resolved
    """
    seen = seen or set()

    # Make a copy to avoid modifying the input schema
    schema_part = schema_part.copy()

    # Handle $ref directly in the schema
    if "$ref" in schema_part:
        ref_path = schema_part["$ref"]
        # Standard OpenAPI references are in the format "#/components/schemas/ModelName"
        if ref_path.startswith("#/components/schemas/"):
            if ref_path in seen:
                return {"$ref": ref_path}
            seen.add(ref_path)
            model_name = ref_path.split("/")[-1]
            if "components" in reference_schema and "schemas" in reference_schema["components"]:
                if model_name in reference_schema["components"]["schemas"]:
                    # Replace with the resolved schema
                    ref_schema = reference_schema["components"]["schemas"][model_name].copy()
                    # Remove the $ref key and merge with the original schema
                    schema_part.pop("$ref")
                    schema_part.update(ref_schema)

    # Recursively resolve references in all dictionary values
    for key, value in schema_part.items():
        if isinstance(value, dict):
            schema_part[key] = resolve_schema_references(value, reference_schema, seen)
        elif isinstance(value, list):
            # Only process list items that are dictionaries since only they can contain refs
            schema_part[key] = [resolve_schema_references(item, reference_schema, seen) if isinstance(item, dict) else item for item in value]

    return schema_part


fastapi_mcp_utils.resolve_schema_references = resolve_schema_references

# ---------------------------------------------------------------------------
# Patch 2 — Force stateless HTTP transport for horizontal scaling
# ---------------------------------------------------------------------------
# This patch replaces _ensure_session_manager_started() so that the
# StreamableHTTPSessionManager is created with stateless=True instead.
#
# TODO: Remove once fastapi-mcp exposes a `stateless` parameter on mount_http().
# ---------------------------------------------------------------------------


async def _ensure_session_manager_started_stateless(self) -> None:
    """Patched version: creates the session manager with stateless=True."""
    if self._manager_started:
        return

    async with self._startup_lock:
        if self._manager_started:
            return

        _logger.debug("Starting StreamableHTTP session manager (stateless=True)")

        self._session_manager = StreamableHTTPSessionManager(
            app=self.mcp_server,
            event_store=self.event_store,
            json_response=self.json_response,
            stateless=True,  # THE FIX: no in-memory session
            security_settings=self.security_settings,
        )

        async def _run_manager():
            try:
                async with self._session_manager.run():
                    _logger.info("StreamableHTTP session manager is running (stateless)")
                    await asyncio.Event().wait()
            except asyncio.CancelledError:
                _logger.info("StreamableHTTP session manager is shutting down")
                raise
            except Exception:
                _logger.exception("Error in StreamableHTTP session manager")
                raise

        self._manager_task = asyncio.create_task(_run_manager())
        self._manager_started = True
        await asyncio.sleep(0.1)


FastApiHttpSessionManager._ensure_session_manager_started = _ensure_session_manager_started_stateless
