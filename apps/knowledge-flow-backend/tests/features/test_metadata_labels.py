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

"""Unit tests for descriptive business labels (DOCUMENT-TAGS-RFC).

Covers the stable interfaces: the pure label-list helpers and the
``DocumentMetadata.labels`` field contract. The service/controller wiring is
integration-level (it depends on the metadata store + ApplicationContext) and is
deliberately not unit-tested here.
"""

from fred_core.documents.document_structures import DocumentMetadata
from knowledge_flow_backend.features.metadata.metadata_utils import (
    normalize_labels,
    with_label_added,
    with_label_removed,
)


def test_normalize_trims_dedupes_and_preserves_order() -> None:
    assert normalize_labels([" CV ", "DVA", "CV", "", "  ", "DVA"]) == ["CV", "DVA"]


def test_with_label_added_is_idempotent_and_normalized() -> None:
    assert with_label_added(["CV"], "DVA") == ["CV", "DVA"]
    assert with_label_added(["CV"], "CV") == ["CV"]
    assert with_label_added(["CV"], "  DVA  ") == ["CV", "DVA"]
    assert with_label_added([], "") == []


def test_with_label_removed_removes_and_normalizes() -> None:
    assert with_label_removed(["CV", "DVA"], "CV") == ["DVA"]
    assert with_label_removed(["CV", "DVA"], "missing") == ["CV", "DVA"]
    assert with_label_removed([" CV ", "CV", "DVA"], "DVA") == ["CV"]


def test_document_metadata_labels_field_defaults_to_empty_list() -> None:
    field = DocumentMetadata.model_fields["labels"]
    assert field.default_factory is not None
    assert field.default_factory() == []
