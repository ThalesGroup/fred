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

"""Alembic table ownership and startup schema needs of knowledge-flow (#2314).

Two distinct sets, because "my tree migrates it" and "my code queries it" are
different questions on a shared database:

- ``OWNED_TABLES`` — what the knowledge-flow Alembic tree migrates.
  ``alembic/env.py`` passes it to ``make_alembic_env(owned_tables=...)`` so
  autogenerate and ``alembic check`` never touch tables migrated by
  control-plane or fred-runtime.
- ``REQUIRED_TABLES`` — what a knowledge-flow process cannot serve without:
  the owned set plus foreign tables it reads at runtime (``users`` and
  ``teammetadata``, both migrated by control-plane's tree but queried by
  ingestion/metadata code). Both entrypoints (``main.py`` and
  ``main_worker.py``) pass it to ``require_tables`` so a deployment that
  skipped its migration jobs fails at boot instead of self-creating tables
  (the #2313 defect: an unfiltered ``create_all`` over the shared
  ``CoreBase`` created ``document_labels`` in production ahead of its
  migration, wedging the migration job on ``DuplicateTableError``).

``tag``/``metadata``/``document_labels`` live on the shared ``CoreBase``
(control-plane's import/export reads them directly) but their DDL belongs to
this tree alone. ``sched_workflow_tasks`` (Alembic-only, no ORM model) is
deliberately absent from both sets: it is not in any metadata, so owning it
would make autogenerate propose its DROP.
"""

from __future__ import annotations

# Explicit registration imports: OWNED_TABLES derives its app half from
# Base.metadata, so every module registering an owned table must be imported
# HERE — never rely on package-init side effects that a later cleanup could
# make lazy.
import fred_core.documents.document_models  # noqa: F401 — registers metadata + tag with CoreBase
import fred_core.documents.label_models  # noqa: F401 — registers document_labels with CoreBase
import knowledge_flow_backend.core.stores.resources.resource_models  # noqa: F401 — registers resource with Base
import knowledge_flow_backend.models.task_models  # noqa: F401 — registers kf_task_run / kf_task_event_log with Base
from knowledge_flow_backend.models.base import Base

# CoreBase tables whose migrations this tree owns — explicit names, never
# derived from CoreBase.metadata (that would claim every backend's tables).
SHARED_CORE_TABLES: frozenset[str] = frozenset({"tag", "metadata", "document_labels"})

OWNED_TABLES: frozenset[str] = frozenset(Base.metadata.tables) | SHARED_CORE_TABLES

# Foreign tables knowledge-flow queries at runtime without owning their DDL:
# `users` (user store lookups in ingestion) and `teammetadata`
# (TeamMetadataStore in ingestion/metadata services). Their migrations belong
# to control-plane's tree — listing them here only makes the startup guard
# honest about what this component needs to serve traffic.
REQUIRED_TABLES: frozenset[str] = OWNED_TABLES | frozenset({"users", "teammetadata"})
