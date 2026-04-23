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

"""backfill_agent_kf_vector_search_mcp_params

Three independent tasks are applied cumulatively to every agent:

Task 1 — Always remove superseded FieldSpec entries:
  Remove chat_options.attach_files and chat_options.libraries_selection from
  tuning.fields whenever they are present.

Task 2 — Backfill params on existing MCP server entry:
  If the agent already has MCPServerRef id='mcp-knowledge-flow-mcp-text' with
  params=null, set params to a KfVectorSearchParams stub whose attach_files /
  libraries_selection values are read from the FieldSpec defaults (Task 1 values).

Task 3 — Add missing MCP server when fields implied it was enabled:
  If the agent does NOT have that MCP server but at least one of the two
  REMOVED_FIELD_KEYS had a true default, add the MCP server entry with params
  built from those defaults.

document_library_tags_ids is intentionally left empty here.
Run developer_tools/backfill/backfill_agent_kf_vector_search_tags.py
after deploying this migration to populate tag IDs from ReBAC.

Revision ID: 5978e4ad3e1b
Revises: 82d43cf766d9
Create Date: 2026-04-22 00:00:00.000000
"""

from __future__ import annotations

import json
import logging
from copy import deepcopy
from typing import Sequence, Union

from sqlalchemy import text

from alembic import op

logger = logging.getLogger(__name__)

# revision identifiers, used by Alembic.
revision: str = "5978e4ad3e1b"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "82d43cf766d9"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

KF_MCP_TEXT_SERVER_ID = "mcp-knowledge-flow-mcp-text"
KF_VECTOR_SEARCH_PROVIDER = "kf_vector_search"
REMOVED_FIELD_KEYS = {"chat_options.attach_files", "chat_options.libraries_selection"}


def _extract_chat_option_defaults(fields: list) -> tuple[bool, bool]:
    """Read attach_files / libraries_selection defaults from FieldSpec entries."""
    attach = False
    libraries = False
    for f in fields:
        if f.get("key") == "chat_options.attach_files":
            attach = bool(f.get("default", False))
        elif f.get("key") == "chat_options.libraries_selection":
            libraries = bool(f.get("default", False))
    return attach, libraries


def _migrate_payload(payload: dict) -> dict | None:
    """Return an updated payload dict, or None if no change is needed."""
    tuning = payload.get("tuning") or {}
    mcp_servers = tuning.get("mcp_servers") or []
    fields = tuning.get("fields") or []

    has_removed_fields = any(f.get("key") in REMOVED_FIELD_KEYS for f in fields)
    null_params_indices = [
        i
        for i, srv in enumerate(mcp_servers)
        if srv.get("id") == KF_MCP_TEXT_SERVER_ID and srv.get("params") is None
    ]
    has_target_server = any(
        srv.get("id") == KF_MCP_TEXT_SERVER_ID for srv in mcp_servers
    )

    if not has_removed_fields and not null_params_indices:
        return None

    attach, libraries = _extract_chat_option_defaults(fields)
    params = {
        "provider": KF_VECTOR_SEARCH_PROVIDER,
        "document_library_tags_ids": [],
        "attach_files": attach,
        "libraries_selection": libraries,
    }

    updated = deepcopy(payload)

    # Task 1 — always strip superseded FieldSpec entries.
    if has_removed_fields:
        updated["tuning"]["fields"] = [
            f
            for f in updated["tuning"].get("fields") or []
            if f.get("key") not in REMOVED_FIELD_KEYS
        ]

    # Task 2 — backfill params on existing MCP server entry.
    for idx in null_params_indices:
        updated["tuning"]["mcp_servers"][idx]["params"] = params

    # Task 3 — add missing MCP server when the old fields implied it was enabled.
    if not has_target_server and has_removed_fields and (attach or libraries):
        updated["tuning"].setdefault("mcp_servers", []).append(
            {"id": KF_MCP_TEXT_SERVER_ID, "params": params}
        )

    return updated


def upgrade() -> None:
    """Apply three cumulative tasks across all agents (see module docstring)."""
    bind = op.get_bind()
    dialect = bind.dialect.name

    rows = bind.execute(
        text("SELECT id, payload_json FROM agent WHERE payload_json IS NOT NULL")
    ).fetchall()

    updated_count = 0
    for row in rows:
        agent_id = row[0]
        raw = row[1]
        payload = raw if isinstance(raw, dict) else json.loads(raw)

        updated = _migrate_payload(payload)
        if updated is None:
            continue

        updated_json = json.dumps(updated)
        if dialect == "postgresql":
            bind.execute(
                text("UPDATE agent SET payload_json = :p ::jsonb WHERE id = :id"),
                {"p": updated_json, "id": agent_id},
            )
        else:
            bind.execute(
                text("UPDATE agent SET payload_json = :p WHERE id = :id"),
                {"p": updated_json, "id": agent_id},
            )
        updated_count += 1

    logger.info("[MIGRATION] %d agent(s) updated.", updated_count)


def downgrade() -> None:
    """No-op — setting params back to null is unnecessary and loses intent."""
    pass
