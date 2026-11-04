# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Verify migrated PostgreSQL conversation ownership without repairing schema."""

from collections.abc import Mapping

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


async def verify_conversation_ownership(
    connection: AsyncConnection,
    tables: Mapping[str, str],
    *,
    optional_tables: Mapping[str, str] | None = None,
) -> None:
    if connection.dialect.name != "postgresql":
        return  # Standalone SQLite has no Control Plane lifecycle root.
    tables = dict(tables)
    for name, source in (optional_tables or {}).items():
        if await connection.scalar(text("SELECT to_regclass(:name)"), {"name": name}):
            tables[name] = source
    rows = await connection.execute(
        text("""
            SELECT t.relname, pg_get_expr(d.adbin, d.adrelid) AS expression
            FROM pg_class t
            JOIN pg_namespace n ON n.oid = t.relnamespace
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attname = 'conversation_id'
            JOIN pg_attrdef d ON d.adrelid = t.oid AND d.adnum = a.attnum
            JOIN pg_constraint c ON c.conrelid = t.oid AND c.conkey = ARRAY[a.attnum]
            JOIN pg_attribute parent ON parent.attrelid = c.confrelid
                AND c.confkey = ARRAY[parent.attnum]
            WHERE n.nspname = current_schema() AND t.relname = ANY(:tables)
                AND a.attgenerated = 's' AND a.attnotnull AND a.atttypid = 'uuid'::regtype
                AND c.contype = 'f' AND c.convalidated AND NOT c.condeferrable
                AND c.confdeltype = 'c'
                AND c.confrelid = 'control_plane.session_metadata'::regclass
                AND parent.attname = 'session_id'
        """),
        {"tables": list(tables)},
    )
    expressions = {
        row.relname: str(row.expression)
        .replace("::text", "")
        .replace("(", "")
        .replace(")", "")
        .replace(" ", "")
        for row in rows
    }
    for name, source in tables.items():
        expected = (
            "split_partthread_id,':',1::uuid"
            if source == "thread_id"
            else "session_id::uuid"
        )
        if expressions.get(name) != expected:
            raise RuntimeError(
                f"Conversation ownership schema is missing or invalid for {name}; "
                "run python -m fred_runtime migrate before starting this pod"
            )
