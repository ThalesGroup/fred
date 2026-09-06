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
Pull-corpus sync (docs/swift/rfc/INDEXED-CORPUS-RFC.md §6/§7/§10 plan step 2)
— proof of concept only.

Reuses the exact same ingestion primitives a manual push upload calls
(`IngestionService.extract_metadata`/`save_input`, `push_input_process`,
`output_process`) rather than a parallel pull-specific pipeline: per the RFC,
a `rag_sql` corpus is the existing pipeline, just fed by a connector instead
of an HTTP upload. Called in-process (no Temporal) — the same style already
used by `InMemoryScheduler` for push.

State this function owns (distinct from the connector's own opaque cursor,
which it never parses): a `{source_item_id: document_uid}` map, because
`SourceItem`/`SourceChange` deliberately carry no FRED document identity —
that mapping is this pipeline's concern, not the connector contract's
(`fred_sdk.contracts.connector`).

A changed file (same `source_item_id`, new `revision`) is handled as
delete-then-recreate, not update-in-place — an accepted limitation carried
over verbatim from the RFC's own design notes, not a new one.

Not addressed here (RFC §7 — deliberately not decided by this POC): what
calls this on what cadence, and serializing concurrent calls for the same
corpus. Calling this function twice concurrently for the same `corpus.corpus_id`
is the caller's responsibility to prevent, not this function's.

`Corpus` (instance) and `CorpusType` (registered kind) are two objects
since the RFC's 2026-09-06 revision (§2/§4) — `mode` lives on `CorpusType`,
not on the instance, so this function takes both rather than just `corpus`.
"""

from __future__ import annotations

import json
import logging
import pathlib
import tempfile
from typing import Any

from fred_core import KeycloakUser
from fred_core.documents.document_structures import SourceType
from fred_sdk.contracts.connector import ChangeKind, SourceConnector
from fred_sdk.contracts.corpus import Corpus, CorpusMode, CorpusType

from knowledge_flow_backend.common.structures import IngestionProcessingProfile
from knowledge_flow_backend.features.ingestion.ingestion_service import get_ingestion_service
from knowledge_flow_backend.features.metadata.service import MetadataService
from knowledge_flow_backend.features.scheduler.activities import output_process
from knowledge_flow_backend.features.scheduler.push_files_activities import push_input_process
from knowledge_flow_backend.features.scheduler.scheduler_structures import FileToProcess

logger = logging.getLogger(__name__)


async def sync_pull_corpus(
    *,
    user: KeycloakUser,
    corpus: Corpus,
    corpus_type: CorpusType,
    connector: SourceConnector,
    state: str | None,
    profile: IngestionProcessingProfile = IngestionProcessingProfile.medium,
) -> str:
    """Discover changes via `connector`, ingest/delete through the existing
    push-shaped pipeline, return the next opaque `state` to pass back in.

    `user` performs every ingestion/delete call and must be authorized for
    `corpus.scope.tag_ids` — this function makes no authorization decision
    of its own, including the connector-kind usage-enablement check the RFC
    describes (§6, not yet implemented).
    """
    if corpus.corpus_type_id != corpus_type.corpus_type_id:
        raise ValueError(f"corpus.corpus_type_id ({corpus.corpus_type_id!r}) does not match corpus_type ({corpus_type.corpus_type_id!r})")
    if corpus_type.mode is not CorpusMode.PULL:
        raise ValueError(f"sync_pull_corpus requires a pull-mode corpus type, got {corpus_type.mode}")

    parsed: dict[str, Any] = json.loads(state) if state else {}
    documents: dict[str, str] = dict(parsed.get("documents", {}))

    changes, next_connector_cursor = connector.discover_changes(parsed.get("connector_cursor"))
    tags = list(corpus.scope.tag_ids)

    for change in changes:
        item = change.item
        existing_uid = documents.pop(item.source_item_id, None)

        if change.kind is ChangeKind.DELETE:
            if existing_uid:
                await MetadataService().delete_document_and_artifacts(user, existing_uid)
            continue

        if existing_uid:
            # Changed content: delete + recreate — see module docstring.
            await MetadataService().delete_document_and_artifacts(user, existing_uid)

        with tempfile.TemporaryDirectory(prefix="pull-corpus-") as tmpdir:
            input_dir = pathlib.Path(tmpdir) / "input"
            fetched_path = connector.fetch(item, input_dir)

            ingestion_service = get_ingestion_service()
            metadata = await ingestion_service.extract_metadata(
                user,
                file_path=fetched_path,
                tags=tags,
                source_tag=corpus.corpus_id,
                profile=profile,
            )
            # `extract_metadata`'s own pull-detection reads `document_sources`
            # config, which this corpus is not registered in (RFC §6/§10) — set
            # explicitly rather than relying on that unrelated mechanism.
            metadata.source.source_type = SourceType.PULL
            metadata.source.pull_location = item.display_path

            ingestion_service.save_input(user, metadata=metadata, input_dir=input_dir)
            metadata = await push_input_process(user=user, metadata=metadata, input_file=str(fetched_path), profile=profile)

            file_to_process = FileToProcess(
                document_uid=metadata.document_uid,
                source_tag=corpus.corpus_id,
                tags=tags,
                profile=profile,
                processed_by=user,
            )
            metadata = await output_process(file=file_to_process, metadata=metadata, accept_memory_storage=True)

        documents[item.source_item_id] = metadata.document_uid

    return json.dumps({"connector_cursor": next_connector_cursor, "documents": documents}, sort_keys=True)
