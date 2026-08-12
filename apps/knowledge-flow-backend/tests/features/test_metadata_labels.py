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

"""Unit tests for descriptive business labels.

Covers the stable interfaces: the pure label normalization helper and the
``DocumentMetadata.labels`` field contract. Assignment itself (add/remove) is
a `document_labels` row insert/delete, not a Python list transform — see
`test_metadata_service_labels.py` (service-level) and
`fred_core/tests/documents/test_postgres_document_store_labels.py`
(store-level) for that behavior.
"""

from fred_core.documents.document_structures import DocumentMetadata

from knowledge_flow_backend.features.metadata.metadata_utils import normalize_labels


def test_normalize_trims_dedupes_and_preserves_order() -> None:
    assert normalize_labels([" CV ", "DVA", "CV", "", "  ", "DVA"]) == ["CV", "DVA"]


def test_document_metadata_labels_field_defaults_to_empty_list() -> None:
    field = DocumentMetadata.model_fields["labels"]
    assert field.default_factory is not None
    assert field.default_factory() == []
