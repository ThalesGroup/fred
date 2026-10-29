# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Document selection is a data filter, never an authorization grant."""

from collections.abc import Sequence
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DocumentSelection(BaseModel):
    """Union of direct folder contents and explicit documents, using Weaver IDs.

    No recursive expansion: a picker represents a subtree by selecting its folders.
    An empty selection covers no documents.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    folder_ids: tuple[UUID, ...] = ()
    document_ids: tuple[UUID, ...] = ()

    def covers(self, document_id: UUID, folder_id: UUID | None) -> bool:
        return document_id in self.document_ids or folder_id in self.folder_ids


class DocumentScope(BaseModel):
    """Intersection of selections, evaluated on document placement in Knowledge Flow.

    No selections means unrestricted; one empty selection means nothing. Keeping
    the clauses separate preserves folder/document overlap without enumerating a corpus.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    selections: tuple[DocumentSelection, ...] = ()

    @classmethod
    def from_ids(
        cls,
        folder_ids: Sequence[str] | None = None,
        document_ids: Sequence[str] | None = None,
    ) -> "DocumentScope":
        if folder_ids is None and document_ids is None:
            return cls()
        return cls(
            selections=(
                DocumentSelection(
                    folder_ids=tuple(UUID(value) for value in folder_ids or ()),
                    document_ids=tuple(UUID(value) for value in document_ids or ()),
                ),
            )
        )

    def intersect(self, other: "DocumentScope") -> "DocumentScope":
        return DocumentScope(
            selections=tuple(dict.fromkeys((*self.selections, *other.selections)))
        )

    def covers(self, document_id: UUID, folder_id: UUID | None) -> bool:
        return all(
            selection.covers(document_id, folder_id) for selection in self.selections
        )

    @property
    def is_empty(self) -> bool:
        return any(
            not item.folder_ids and not item.document_ids for item in self.selections
        )
