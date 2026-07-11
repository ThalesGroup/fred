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
`DocumentAccessCapability` — the #1906 pilot capability (CAPAB-01).

This package is the in-tree reference capability the RFC §10 pilot row names: a
real, working vector-search capability wired through the SDK
`DocumentSearchPort`. Installing fred-runtime registers it via the
`fred.capabilities` entry point (`document_access`).
"""

from __future__ import annotations

from .capability import (
    DOCUMENT_ACCESS_TOOL_REF,
    DocumentAccessCapability,
    DocumentAccessConfig,
    DocumentAccessTurnOptions,
    DocumentScopeControlParams,
    narrow_scope_ids,
)

__all__ = [
    "DOCUMENT_ACCESS_TOOL_REF",
    "DocumentAccessCapability",
    "DocumentAccessConfig",
    "DocumentAccessTurnOptions",
    "DocumentScopeControlParams",
    "narrow_scope_ids",
]
