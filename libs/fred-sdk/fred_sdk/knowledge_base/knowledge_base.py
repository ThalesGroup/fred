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
The live Knowledge Base an author writes: identity, configuration fields and
one synchronization handler.

It holds a callable and is therefore not serializable; the JSON-safe
declaration its image publishes is projected from it (see `declaration.py`).
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Coroutine, Sequence
from typing import Any

from fred_core import CONTRIBUTED_NAME_PATTERN, require_contributed_name

from fred_sdk.contracts.models import FieldSpec
from fred_sdk.knowledge_base.models import (
    KnowledgeBaseRunContext,
    KnowledgeBaseSyncResult,
)

# One naming rule across everything a contributor adds to Fred: a dotted name
# under a prefix they own. See fred_core.common.naming.
KNOWLEDGE_BASE_ID_PATTERN = CONTRIBUTED_NAME_PATTERN

# `Coroutine`, not `Awaitable`: the resolved handler is handed straight to
# `asyncio.run` (and to the SDK's own activity adapter), which accepts a
# coroutine and rejects a bare awaitable — typing it loosely forced consumers
# into a cast, found while writing the first real implementation.
SynchronizeHandler = Callable[
    [KnowledgeBaseRunContext], Coroutine[Any, Any, KnowledgeBaseSyncResult]
]


class KnowledgeBaseDeclarationError(ValueError):
    """Raised when a declaration is malformed or used incorrectly."""


class KnowledgeBase:
    """One Knowledge Base an author declares and an image publishes.

    Example:
        kb = KnowledgeBase(
            id="http-markdown",
            version="1.0.0",
            name="HTTP Markdown",
            description="Synchronize Markdown documents",
            configuration_fields=[FieldSpec(key="base_url", type="url", title="URL")],
        )

        @kb.synchronize
        async def synchronize(
            context: KnowledgeBaseRunContext,
        ) -> KnowledgeBaseSyncResult:
            ...
    """

    def __init__(
        self,
        *,
        id: str,
        version: str,
        name: str,
        description: str,
        configuration_fields: Sequence[FieldSpec] = (),
    ) -> None:
        try:
            require_contributed_name(id)
        except ValueError as error:
            raise KnowledgeBaseDeclarationError(
                f"Knowledge Base id is not a contributed name: {error}"
            ) from error
        for label, value in (
            ("version", version),
            ("name", name),
            ("description", description),
        ):
            if not value.strip():
                raise KnowledgeBaseDeclarationError(
                    f"Knowledge Base {label} must not be empty"
                )

        seen: set[str] = set()
        for field in configuration_fields:
            if field.key in seen:
                raise KnowledgeBaseDeclarationError(
                    f"Duplicate configuration field key {field.key!r}"
                )
            seen.add(field.key)

        self.id = id
        self.version = version
        self.name = name
        self.description = description
        self.configuration_fields: list[FieldSpec] = list(configuration_fields)
        self._handler: SynchronizeHandler | None = None

    def synchronize(self, handler: SynchronizeHandler) -> SynchronizeHandler:
        """Register the one synchronization handler, and return it unchanged."""
        if not inspect.iscoroutinefunction(handler):
            raise KnowledgeBaseDeclarationError(
                f"Synchronization handler {handler.__name__!r} must be async"
            )
        if self._handler is not None:
            raise KnowledgeBaseDeclarationError(
                f"Knowledge Base {self.id!r} already declares a synchronization "
                f"handler ({self._handler.__name__!r})"
            )
        self._handler = handler
        return handler

    def resolve_handler(self) -> SynchronizeHandler:
        """Return the registered handler. For the SDK runtime, not for authors."""
        if self._handler is None:
            raise KnowledgeBaseDeclarationError(
                f"Knowledge Base {self.id!r} declares no synchronization handler; "
                "decorate one with @kb.synchronize"
            )
        return self._handler
