from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from control_plane_backend.models.base import Base, utcnow


class TeamPolicyOverrideRow(Base):
    """ORM model for the ``team_policy_override`` table.

    Why this table exists:
    - the conversation retention policy is otherwise static, ops-owned YAML
      (``conversation_policy_catalog.yaml``) resolved at startup; a team owner
      cannot set their own value from the product UI.
    - this is the first concrete ``TeamPlatformPolicy`` slice (FRED-TEAM-CONFIG-RFC
      §5.2): a per-team DB override the policy resolver layers over the YAML.

    Design rule (FRED-2.0.2-RGPD-READY-RFC §3.B): **platform caps, team may only
    tighten**. Both override fields are nullable ISO-8601 durations; ``None`` means
    "inherit the platform value". The resolver clamps any team value to the
    platform maximum, so this row can never relax a guardrail — only shorten it.
    """

    __tablename__ = "team_policy_override"

    team_id: Mapped[str] = mapped_column(String, primary_key=True)
    # ISO-8601 durations (e.g. ``P30D``); None = inherit the platform value.
    team_delete_grace: Mapped[str | None] = mapped_column(String, nullable=True)
    max_idle: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
    # Keycloak ``sub`` of the team owner who last set the override (audit).
    updated_by: Mapped[str] = mapped_column(String, nullable=False)
