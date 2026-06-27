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

from fred_core.documents.document_models import DocumentMetadataRow
from fred_core.documents.document_store import (
    BaseDocumentMetadataStore,
    DocumentMetadataDeserializationError,
)
from fred_core.documents.document_structures import (
    AccessInfo,
    DocSummary,
    DocumentMetadata,
    FileInfo,
    FileType,
    Identity,
    Processing,
    ProcessingGraph,
    ProcessingGraphEdge,
    ProcessingGraphNode,
    ProcessingStage,
    ProcessingStatus,
    ProcessingSummary,
    ReportExtensionV1,
    ReportFormat,
    SourceInfo,
    SourceType,
    Tagging,
)
from fred_core.documents.postgres_document_store import PostgresDocumentMetadataStore
from fred_core.documents.tag_models import TagRow

__all__ = [
    # Pydantic models / enums
    "AccessInfo",
    "DocSummary",
    "DocumentMetadata",
    "FileInfo",
    "FileType",
    "Identity",
    "Processing",
    "ProcessingGraph",
    "ProcessingGraphEdge",
    "ProcessingGraphNode",
    "ProcessingStage",
    "ProcessingStatus",
    "ProcessingSummary",
    "ReportExtensionV1",
    "ReportFormat",
    "SourceInfo",
    "SourceType",
    "Tagging",
    # Store
    "BaseDocumentMetadataStore",
    "DocumentMetadataDeserializationError",
    "DocumentMetadataRow",
    "PostgresDocumentMetadataStore",
    "TagRow",
]
