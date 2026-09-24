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

"""Scoped document access over the Knowledge Flow corpus (`document_access`).

Installing this package registers the capability through its
`fred.capabilities` entry point; see `capability.py` for the scoping
precedence and the deliberate deferrals.
"""

from fred_capability_document_access.capability import (
    DOCUMENT_ACCESS_TOOL_REF,
    DocumentAccessCapability,
    DocumentAccessConfig,
    DocumentAccessTurnOptions,
    narrow_scope_ids,
)

__all__ = [
    "DOCUMENT_ACCESS_TOOL_REF",
    "DocumentAccessCapability",
    "DocumentAccessConfig",
    "DocumentAccessTurnOptions",
    "narrow_scope_ids",
]
