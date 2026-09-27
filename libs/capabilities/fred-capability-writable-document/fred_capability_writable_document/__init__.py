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

"""Writable Document capability — a session-scoped collaborative Markdown document.

Swift port of Kea's "Writable Document" feature (#1905) as a single out-of-tree
`AgentCapability`. Public surface:

- :class:`~fred_capability_writable_document.capability.WritableDocumentCapability`
  and its contributed :class:`WritableDocumentPart` chat part.
- The pure Markdown->docx export
  (:func:`~fred_capability_writable_document.docx_export.markdown_to_docx_bytes`).
- The persistence seam
  (:func:`~fred_capability_writable_document.store.get_writable_document_store`).
"""

from fred_capability_writable_document.capability import (
    WritableDocumentCapability,
    WritableDocumentPart,
)

__all__ = [
    "WritableDocumentCapability",
    "WritableDocumentPart",
]
