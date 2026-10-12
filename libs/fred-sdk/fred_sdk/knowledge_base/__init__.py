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
        DocumentPublisher,
        FieldSpec,
        KnowledgeBase,
        KnowledgeBaseRunContext,
        KnowledgeBaseSyncResult,
        knowledge_base_main,
    )

    kb = KnowledgeBase(
        id="acme.kb.http-markdown",
        version="1.0.0",
        name="HTTP Markdown",
        description="Synchronize Markdown documents",
        configuration_fields=[...],
    )

    @kb.synchronize
    async def synchronize(
        context: KnowledgeBaseRunContext,
    ) -> KnowledgeBaseSyncResult:
        async with DocumentPublisher.for_run(context) as library:
            ...

    raise SystemExit(knowledge_base_main(kb))

That image then exposes two commands: `publish` posts the declaration at
deployment time, `run` serves runs. Configuration is declared with the same
`FieldSpec` vocabulary the rest of the SDK uses; it is re-exported here, with
`UIHints` and `TuningValue`, so a Knowledge Base needs this one package.
"""

# The form vocabulary agents use too, re-exported so an author imports from one
# place. Same objects, not copies: `fred_sdk.contracts.models` keeps working.
from fred_sdk.contracts.models import FieldSpec, TuningValue, UIHints
from fred_sdk.knowledge_base.configuration import MissingPodConfiguration
from fred_sdk.knowledge_base.declaration import KnowledgeBaseDeclaration
from fred_sdk.knowledge_base.documents import (
    DocumentHandle,
    DocumentOutcome,
    DocumentPublisher,
    DocumentPublishError,
    DocumentRetractError,
    DocumentWaitTimeout,
    KnowledgeFlowNotConfigured,
)
from fred_sdk.knowledge_base.entrypoints import (
    knowledge_base_main,
    publish_knowledge_base,
    run_knowledge_base,
)
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
    KnowledgeBaseReconciliation,
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
    "DocumentHandle",
    "DocumentOutcome",
    "DocumentPublishError",
    "DocumentPublisher",
    "DocumentRetractError",
    "DocumentWaitTimeout",
    "FieldSpec",
    "KnowledgeBase",
    "KnowledgeBaseDeclaration",
    "KnowledgeBaseDeclarationError",
    "KnowledgeBaseIssue",
    "KnowledgeBaseReconciliation",
    "KnowledgeBaseRunContext",
    "KnowledgeBaseRunOutcome",
    "KnowledgeBaseSyncResult",
    "KnowledgeFlowNotConfigured",
    "MissingPodConfiguration",
    "SynchronizeHandler",
    "TuningValue",
    "UIHints",
    "knowledge_base_main",
    "publish_knowledge_base",
    "run_knowledge_base",
]
