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

"""Unit tests for path-derived filesystem provenance (FILES-04 G4)."""

import pytest

from knowledge_flow_backend.features.filesystem.provenance import (
    ORIGIN_AGENT_GENERATED,
    ORIGIN_INGESTED,
    ORIGIN_SHARED_COPY,
    ORIGIN_UPLOADED,
    PRODUCER_HUMAN,
    PRODUCER_INGESTION,
    derive_provenance,
)


def test_agent_subtree_is_agent_generated():
    p = derive_provenance("/teams/acme/agents/inst-7/users/u-1/outputs/q3.pptx")
    assert p is not None
    assert p.origin == ORIGIN_AGENT_GENERATED
    assert p.producer == "agent:inst-7"
    assert p.created_by == "u-1"


def test_mon_espace_is_uploaded_by_owner():
    p = derive_provenance("/teams/acme/users/u-1/notes.txt")
    assert p is not None
    assert p.origin == ORIGIN_UPLOADED
    assert p.producer == PRODUCER_HUMAN
    assert p.created_by == "u-1"


def test_shared_is_uploaded_human_unknown_author_in_v1():
    # G5 refines genuine share-copies later; v1 has no share-copies yet.
    p = derive_provenance("/teams/acme/shared/templates/brand.pptx")
    assert p is not None
    assert p.origin == ORIGIN_UPLOADED
    assert p.producer == PRODUCER_HUMAN
    assert p.created_by is None


def test_shared_files_subdir_is_share_copy():
    # G5: human share-by-copy lands in shared/files/ and reads back as partagé,
    # while other shared/ files stay déposé (uploaded).
    p = derive_provenance("/teams/acme/shared/files/q3-review.pptx")
    assert p is not None
    assert p.origin == ORIGIN_SHARED_COPY
    assert p.producer == PRODUCER_HUMAN


def test_corpus_is_ingested():
    p = derive_provenance("/corpus/documents/doc-1/preview.md")
    assert p is not None
    assert p.origin == ORIGIN_INGESTED
    assert p.producer == PRODUCER_INGESTION
    assert p.created_by is None


def test_relative_path_is_normalized_before_derivation():
    # Paths without a leading slash derive the same way.
    p = derive_provenance("teams/acme/agents/inst-7/users/u-1/x.pptx")
    assert p is not None
    assert p.producer == "agent:inst-7"


@pytest.mark.parametrize(
    "path",
    [
        "",
        "/",
        "/teams",
        "/teams/acme",  # team box, no sub-area owner yet
        "/teams/acme/agents/inst-7",  # agent box, no user segment yet
        "/etc/models",  # config view, not a user file area
    ],
)
def test_paths_without_file_provenance_return_none(path):
    assert derive_provenance(path) is None
