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

"""Tables the control-plane Alembic tree owns (#2314).

Consumed by ``alembic/env.py`` via ``make_alembic_env(owned_tables=...)`` so
autogenerate and ``alembic check`` never touch tables migrated by other
trees: knowledge-flow's ``tag``/``metadata``/``document_labels`` and
fred-runtime's ``session_history`` all live on the same shared ``CoreBase``,
and deriving ownership from that metadata is exactly what once made
control-plane's autogenerate propose creating knowledge-flow's tables.
"""

from __future__ import annotations

import fred_core.session.stores.session_models  # noqa: F401 — registers session with CoreBase
import fred_core.teams.team_metatada_models  # noqa: F401 — registers teammetadata with CoreBase
import fred_core.users.user_models  # noqa: F401 — registers users with CoreBase

# Explicit registration imports: OWNED_TABLES derives its app half from
# Base.metadata and claims three CoreBase tables by name, so every module
# registering one of those tables must be imported HERE — never rely on
# package-init side effects (fred_core/__init__ imports) that a later
# cleanup could make lazy, leaving a claimed table out of the metadata and
# turning it into an autogenerate DROP proposal.
import control_plane_backend.models.agent_instance_models  # noqa: F401
import control_plane_backend.models.bootstrap_models  # noqa: F401 — registers platformbootstrap with Base
import control_plane_backend.models.capability_settings_models  # noqa: F401
import control_plane_backend.models.model_reasoning_models  # noqa: F401
import control_plane_backend.models.platform_model_binding_models  # noqa: F401 — registers platform_model_binding with Base
import control_plane_backend.models.prompt_models  # noqa: F401
import control_plane_backend.models.purge_queue_models  # noqa: F401
import control_plane_backend.models.routing_policy_models  # noqa: F401
import control_plane_backend.models.session_attachment_models  # noqa: F401
import control_plane_backend.models.session_metadata_models  # noqa: F401
import control_plane_backend.models.task_models  # noqa: F401 — registers cp_task_run / cp_task_event_log with Base
from control_plane_backend.models.base import Base

# CoreBase tables whose migrations this tree owns — explicit names, never
# derived from CoreBase.metadata (that would claim every backend's tables).
SHARED_CORE_TABLES: frozenset[str] = frozenset({"users", "session", "teammetadata"})

# On control-plane's own Base but migrated by the separate fred-evaluation
# tree (`alembic_version_evaluation`, its own database) — subtracted
# explicitly so OWNED_TABLES stays correct even if a future import chain
# registers these models before this frozenset is computed.
_EVALUATION_TABLES: frozenset[str] = frozenset(
    {"evaluation_campaign", "evaluation_case", "evaluation_metric_result"}
)

OWNED_TABLES: frozenset[str] = (
    frozenset(Base.metadata.tables) - _EVALUATION_TABLES
) | SHARED_CORE_TABLES
