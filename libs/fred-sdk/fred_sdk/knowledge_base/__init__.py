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
Knowledge Base authoring surface.

A Knowledge Base is declared, given one synchronization handler, and installed
into a Fred deployment as a JSON-safe manifest:

    from fred_sdk.knowledge_base import (
        KnowledgeBase,
        KnowledgeBaseRunContext,
        KnowledgeBaseSyncResult,
    )

    kb = KnowledgeBase(
        id="http-markdown",
        version="1.0.0",
        name="HTTP Markdown",
        description="Synchronize Markdown documents",
        configuration_fields=[...],
    )

    @kb.synchronize
    async def synchronize(
        context: KnowledgeBaseRunContext,
    ) -> KnowledgeBaseSyncResult:
        ...

Configuration is declared with the same `FieldSpec` vocabulary the rest of the
SDK uses — import it from `fred_sdk.contracts.models`.
"""

from fred_sdk.knowledge_base.declaration import (
    KNOWLEDGE_BASE_ID_PATTERN,
    KnowledgeBase,
    KnowledgeBaseDeclarationError,
    SynchronizeHandler,
)
from fred_sdk.knowledge_base.manifest import KnowledgeBaseManifest
from fred_sdk.knowledge_base.models import (
    MAX_ISSUE_MESSAGE_CHARS,
    MAX_ISSUES,
    MAX_SUMMARY_CHARS,
    KnowledgeBaseIssue,
    KnowledgeBaseRunContext,
    KnowledgeBaseRunOutcome,
    KnowledgeBaseSyncResult,
)

__all__ = [
    "KNOWLEDGE_BASE_ID_PATTERN",
    "MAX_ISSUES",
    "MAX_ISSUE_MESSAGE_CHARS",
    "MAX_SUMMARY_CHARS",
    "KnowledgeBase",
    "KnowledgeBaseDeclarationError",
    "KnowledgeBaseIssue",
    "KnowledgeBaseManifest",
    "KnowledgeBaseRunContext",
    "KnowledgeBaseRunOutcome",
    "KnowledgeBaseSyncResult",
    "SynchronizeHandler",
]
