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

A Knowledge Base is declared, given one synchronization handler, and published
into a Fred deployment by its own image:

    from fred_sdk.knowledge_base import (
        KnowledgeBase,
        KnowledgeBaseRunContext,
        KnowledgeBaseSyncResult,
        knowledge_base_main,
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

    raise SystemExit(knowledge_base_main(kb))

That image then exposes two commands: `publish` posts the declaration at
deployment time, `run` serves runs. Configuration is declared with the same
`FieldSpec` vocabulary the rest of the SDK uses — import it from
`fred_sdk.contracts.models`.
"""

from fred_sdk.knowledge_base.declaration import KnowledgeBaseDeclaration
from fred_sdk.knowledge_base.entrypoints import (
    knowledge_base_main,
    publish_knowledge_base,
    run_knowledge_base,
)
from fred_sdk.knowledge_base.environment import MissingPodEnvironment
from fred_sdk.knowledge_base.knowledge_base import (
    KNOWLEDGE_BASE_ID_PATTERN,
    KnowledgeBase,
    KnowledgeBaseDeclarationError,
    SynchronizeHandler,
)
from fred_sdk.knowledge_base.models import (
    MAX_ISSUE_MESSAGE_CHARS,
    MAX_ISSUE_SUBJECT_CHARS,
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
    "MAX_ISSUE_SUBJECT_CHARS",
    "MAX_SUMMARY_CHARS",
    "KnowledgeBase",
    "KnowledgeBaseDeclaration",
    "KnowledgeBaseDeclarationError",
    "KnowledgeBaseIssue",
    "KnowledgeBaseRunContext",
    "KnowledgeBaseRunOutcome",
    "KnowledgeBaseSyncResult",
    "MissingPodEnvironment",
    "SynchronizeHandler",
    "knowledge_base_main",
    "publish_knowledge_base",
    "run_knowledge_base",
]
