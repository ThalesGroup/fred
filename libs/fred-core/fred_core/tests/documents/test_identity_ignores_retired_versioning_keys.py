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

"""`canonical_name` and `version` were removed from `Identity`, but nearly every
stored document still carries them: the retired model defaulted `version` to 0
and always backfilled `canonical_name`, and the migration that retired the
mechanism deliberately rewrites only the documents it renames — clearing the keys
corpus-wide was a full-table rewrite against a statement timeout.

So the contract that makes that safe is this one: a document still carrying
either key reads correctly, and neither key reaches the API. If `Identity` ever
gained `extra="forbid"`, every such document would fail to deserialise instead.
"""

from __future__ import annotations

from fred_core.documents.document_structures import Identity


def _stored_document() -> dict:
    """The shape a pre-migration row still holds in its `doc` JSON."""
    return {
        "document_name": "report.pdf",
        "document_uid": "uid-1",
        "canonical_name": "report.pdf",
        "version": 0,
        "title": "Rapport annuel",
    }


def test_a_document_still_carrying_the_retired_keys_reads_correctly() -> None:
    identity = Identity.model_validate(_stored_document())

    assert identity.document_name == "report.pdf"
    assert identity.document_uid == "uid-1"
    assert identity.title == "Rapport annuel"


def test_neither_retired_key_reaches_the_api() -> None:
    dumped = Identity.model_validate(_stored_document()).model_dump()

    assert "canonical_name" not in dumped
    assert "version" not in dumped


def test_an_alternate_version_that_escaped_the_migration_still_reads() -> None:
    """A document migrated on one deployment and imported into another could
    still arrive with `version` above zero."""
    stored = _stored_document() | {"version": 1}

    identity = Identity.model_validate(stored)

    assert identity.document_name == "report.pdf"
    assert "version" not in identity.model_dump()
