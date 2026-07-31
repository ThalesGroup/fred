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
`DocumentSummarizeCapability` (RFC §10) — on-demand document summarization,
split out of the `document_access` pilot.

Installing fred-runtime registers it via the `fred.capabilities` entry point
(`document_summarize`), separate from `document_access` so a team admin opts
into it explicitly.
"""

from __future__ import annotations

from .capability import (
    DEFAULT_SUMMARIZE_MAX_CHARS,
    DocumentSummarizeCapability,
    DocumentSummarizeConfig,
    resolve_summarize_max_chars,
)

__all__ = [
    "DEFAULT_SUMMARIZE_MAX_CHARS",
    "DocumentSummarizeCapability",
    "DocumentSummarizeConfig",
    "resolve_summarize_max_chars",
]
