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

from knowledge_flow_backend.features.content.content_controller import (
    build_content_disposition_header,
)


def test_build_content_disposition_header_keeps_unicode_filename_via_filename_star() -> None:
    header = build_content_disposition_header("inline", "Rapport d’avril 2026.pdf")

    assert header.startswith('inline; filename="Rapport d?avril 2026.pdf"; ')
    assert "filename*=UTF-8''Rapport%20d%E2%80%99avril%202026.pdf" in header
    header.encode("latin-1")
