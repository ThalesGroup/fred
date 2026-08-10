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
`DocumentExtractCapability` (DOCREAD-01) — exhaustive, paginated document
extraction.

Installing fred-runtime registers it via the `fred.capabilities` entry point
(`document_extract`). Pairs with `document_verbatim` over the shared
`document_markdown` port; see `document_read_common`.
"""

from __future__ import annotations

from .capability import DocumentExtractCapability

__all__ = ["DocumentExtractCapability"]
