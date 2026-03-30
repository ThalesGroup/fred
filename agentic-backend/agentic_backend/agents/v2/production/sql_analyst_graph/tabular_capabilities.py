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

"""
Tabular helpers used by the SQL agent.

These functions keep the SQL steps focused on business flow: discover the
available databases, list tables in one database, and read query rows.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from agentic_backend.core.agents.v2 import GraphNodeContext


async def get_database_context(context: GraphNodeContext) -> dict[str, object]:
    """
    Load the current database and table context for the SQL agent.

    Example:
    ```python
    database_context = await get_database_context(context)
    ```
    """

    raw_context = await context.invoke_runtime_tool("get_context", {})
    return normalize_database_context(raw_context)


def normalize_database_context(raw_context: object) -> dict[str, object]:
    """
    Normalize raw tabular context into one predictable mapping.

    Example:
    ```python
    context_map = normalize_database_context('{"sales": []}')
    ```
    """

    if isinstance(raw_context, str):
        try:
            decoded = json.loads(raw_context)
        except Exception:
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return raw_context if isinstance(raw_context, dict) else {}


def tables_for_database(
    database_context: Mapping[str, object], db_name: str
) -> list[str]:
    """
    Return table names for one selected database.

    Example:
    ```python
    tables = tables_for_database(context_map, "analytics")
    ```
    """

    raw_tables = database_context.get(db_name)
    if not isinstance(raw_tables, list):
        return []
    table_names: list[str] = []
    for item in raw_tables:
        if not isinstance(item, dict):
            continue
        table_name = item.get("table_name")
        if isinstance(table_name, str) and table_name.strip():
            table_names.append(table_name.strip())
    return table_names


async def read_query_rows(
    context: GraphNodeContext,
    *,
    db_name: str,
    query: str,
    maximum: int,
) -> list[dict[str, object]]:
    """
    Execute one read query and return preview rows.

    Example:
    ```python
    rows = await read_query_rows(
        context,
        db_name="analytics",
        query="SELECT * FROM sales LIMIT 20",
        maximum=20,
    )
    ```
    """

    raw_result = await context.invoke_runtime_tool(
        "read_query",
        {"db_name": db_name, "query": query},
    )
    return extract_query_rows(raw_result, maximum=maximum)


def extract_query_rows(raw_result: object, *, maximum: int) -> list[dict[str, object]]:
    """
    Extract preview rows from a raw `read_query` payload.

    Example:
    ```python
    rows = extract_query_rows('{"rows": [{"count": 3}]}', maximum=20)
    ```
    """

    payload = raw_result
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            return []
    if not isinstance(payload, dict):
        return []
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return []
    normalized: list[dict[str, object]] = []
    for row in rows[:maximum]:
        if isinstance(row, dict):
            normalized.append(dict(row))
    return normalized
