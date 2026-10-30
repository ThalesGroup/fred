# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Offline input adapter for the retained DuckDB engine tests.

These tests exercise SQL, Parquet, limits and serialization only. They deliberately
replace document resolution; the real Weaver boundary has its own regressions in
tests/features/tabular/test_weaver_tabular.py. Never used by application code.
"""

import hashlib
from types import SimpleNamespace

from fred_core.documents.access import PublishedArtifact

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.features.tabular.artifacts import TabularTableArtifactV1, build_default_query_alias, read_tabular_artifact, read_tabular_multi_artifact
from knowledge_flow_backend.features.tabular.service import ResolvedDataset, TabularService


class TabularEngineHarness(TabularService):
    def __init__(self):
        context = ApplicationContext.get_instance()
        self.metadata_store = context.get_metadata_store()
        self.content_store = context.get_content_store()
        self.tabular_config = context.get_config().storage.tabular_store
        self.artifact_reader = SimpleNamespace(read_bytes=lambda prefix, artifact: self.content_store.get_output_artifact(prefix + artifact.path))

    async def _resolve_authorized_datasets(self, user, *, document_uids=None):
        metadata = await self.metadata_store.get_all_metadata({}) if document_uids is None else await self.metadata_store.get_metadata_by_uids(document_uids)
        datasets = []
        for document in sorted(metadata, key=lambda doc: doc.document_uid):
            single, multi = read_tabular_artifact(document), read_tabular_multi_artifact(document)
            tables = [single] if single else list(multi.tables) if multi else []
            catalog = None
            if multi:
                try:
                    data = self.content_store.get_output_artifact(f"{document.document_uid}/output/output.md")
                except FileNotFoundError:
                    pass
                else:
                    catalog = PublishedArtifact(prefix=f"{document.document_uid}/output/", size=len(data), sha256=hashlib.sha256(data).hexdigest())
            for table in tables:
                alias = table.query_alias if isinstance(table, TabularTableArtifactV1) else build_default_query_alias(document.document_uid, document.document_name)
                datasets.append(ResolvedDataset(metadata=document, artifact=table, query_alias=alias, catalog=catalog))
        return datasets

    def _resolve_dataset_location(self, object_key):
        path = self.content_store.object_root / object_key
        if not path.is_file():
            raise FileNotFoundError("Tabular artifact is missing")
        return str(path)
