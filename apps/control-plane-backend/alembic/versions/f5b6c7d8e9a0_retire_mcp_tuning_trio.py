"""retire the MCP tuning trio → mcp:<server> capability slices

#1978 (CAPAB-01, RFC AGENT-CAPABILITY §3.8, §6 Tier 1). An MCP server is now an
`mcp:<server>` capability, so the per-instance MCP trio stored inside the
serialized ``ManagedAgentTuning`` (``agent_instance.tuning_json``) is folded into
the capability fields:

- ``selected_mcp_server_ids`` → ``mcp:<id>`` entries in ``selected_capability_ids``
- ``mcp_config_values[id]``  → ``capability_config["mcp:<id>"]`` envelopes
- ``mcp_servers``            → dropped (the active set is materialized below)

The mapping is mechanical and 1:1. Crucially the retired ``None`` semantics of
``selected_mcp_server_ids`` (``None`` == "all declared servers active") differ from
``selected_capability_ids`` (``None`` == "template default = no capabilities"), so
every row that had ANY MCP involvement is MATERIALIZED to an exact
``selected_capability_ids`` set (never left ``None``) — otherwise the runtime's
template-default fallback would re-activate servers an admin explicitly
deselected. Model change, data migration, and pod release ship together; no
dual-read window.

Revision ID: f5b6c7d8e9a0
Revises: f4a5b6c7d8e9
Create Date: 2026-07-11 00:00:00.000000

"""

import json
from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f5b6c7d8e9a0"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "f4a5b6c7d8e9"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MCP_PREFIX = "mcp:"
_MCP_SCHEMA_VERSION = "1"


def _forward(tuning: dict[str, Any]) -> dict[str, Any]:
    """Fold the MCP trio into capability fields for one tuning payload."""

    selected_caps = tuning.get("selected_capability_ids")
    existing_caps = [
        c
        for c in (selected_caps or [])
        if isinstance(c, str) and not c.startswith(_MCP_PREFIX)
    ]

    mcp_servers = tuning.get("mcp_servers") or []
    declared_ids = [
        s["id"] for s in mcp_servers if isinstance(s, dict) and s.get("id")
    ]
    selected_server_ids = tuning.get("selected_mcp_server_ids")
    # None => all declared active (retired semantics); a list => exactly that set.
    active_ids = (
        list(declared_ids) if selected_server_ids is None else list(selected_server_ids)
    )
    mcp_caps = [f"{_MCP_PREFIX}{sid}" for sid in active_ids]

    capability_config = dict(tuning.get("capability_config") or {})
    for sid, values in (tuning.get("mcp_config_values") or {}).items():
        capability_config[f"{_MCP_PREFIX}{sid}"] = {
            "schema_version": _MCP_SCHEMA_VERSION,
            "config": values,
        }

    had_mcp = (
        bool(mcp_servers)
        or (selected_server_ids is not None)
        or bool(tuning.get("mcp_config_values"))
    )
    if selected_caps is None and not had_mcp:
        new_selected: list[str] | None = None
    else:
        new_selected = existing_caps + mcp_caps

    tuning.pop("mcp_servers", None)
    tuning.pop("selected_mcp_server_ids", None)
    tuning.pop("mcp_config_values", None)
    tuning["selected_capability_ids"] = new_selected
    tuning["capability_config"] = capability_config
    return tuning


def _backward(tuning: dict[str, Any]) -> dict[str, Any]:
    """Best-effort inverse: split `mcp:<id>` slices back into the MCP trio."""

    selected_caps = tuning.get("selected_capability_ids")
    non_mcp = [
        c
        for c in (selected_caps or [])
        if isinstance(c, str) and not c.startswith(_MCP_PREFIX)
    ]
    mcp_ids = [
        c[len(_MCP_PREFIX) :]
        for c in (selected_caps or [])
        if isinstance(c, str) and c.startswith(_MCP_PREFIX)
    ]

    capability_config = dict(tuning.get("capability_config") or {})
    mcp_config_values: dict[str, Any] = {}
    for cap_id in list(capability_config):
        if cap_id.startswith(_MCP_PREFIX):
            envelope = capability_config.pop(cap_id)
            config = (
                envelope.get("config") if isinstance(envelope, dict) else None
            ) or {}
            if config:
                mcp_config_values[cap_id[len(_MCP_PREFIX) :]] = config

    tuning["mcp_servers"] = [{"id": sid} for sid in mcp_ids]
    tuning["selected_mcp_server_ids"] = mcp_ids
    tuning["mcp_config_values"] = mcp_config_values
    tuning["selected_capability_ids"] = non_mcp if selected_caps is not None else None
    tuning["capability_config"] = capability_config
    return tuning


def _rewrite_all(transform) -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT agent_instance_id, tuning_json FROM agent_instance")
    ).fetchall()
    for agent_instance_id, tuning_json in rows:
        if not tuning_json:
            continue
        try:
            tuning = json.loads(tuning_json)
        except (TypeError, ValueError):
            continue
        if not isinstance(tuning, dict):
            continue
        new_json = json.dumps(transform(tuning))
        conn.execute(
            sa.text(
                "UPDATE agent_instance SET tuning_json = :tuning "
                "WHERE agent_instance_id = :id"
            ),
            {"tuning": new_json, "id": agent_instance_id},
        )


def upgrade() -> None:
    """Fold the MCP trio into capability slices in every stored tuning payload."""

    _rewrite_all(_forward)


def downgrade() -> None:
    """Best-effort restore of the MCP trio from `mcp:<id>` capability slices."""

    _rewrite_all(_backward)
