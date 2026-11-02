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

"""Source keys and versions remain opaque in the shared artifact format."""

import pytest
from fred_core.documents import DocumentMetadata, Identity, SourceInfo, SourceType


@pytest.mark.parametrize("version", [None, "etag-9"])
def test_source_key_and_optional_version_round_trip_in_metadata_json(version):
    key = "notes/../ç'est [drôle] ?&#.md"
    metadata = DocumentMetadata(
        identity=Identity(document_name="report.md", document_uid="doc-1"),
        source=SourceInfo(
            source_type=SourceType.PUSH,
            source_tag="uploads",
            pull_location=None,
            source_library_id="lib-1",
            source_key=key,
            document_version=version,
        ),
    )

    restored = DocumentMetadata.model_validate_json(metadata.model_dump_json())

    assert restored.source.source_library_id == "lib-1"
    assert restored.source.source_key == key
    assert restored.source.document_version == version
