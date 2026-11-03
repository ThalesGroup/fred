# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Structured corpus navigation shared by KF and the SDK; no rendering policy."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TreeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DocumentTreeSpace(TreeRecord):
    space_id: UUID
    name: str


class DocumentTreeFolder(TreeRecord):
    folder_id: UUID
    space_id: UUID
    parent_id: UUID | None
    name: str


class DocumentTreeDocument(TreeRecord):
    document_uid: UUID
    space_id: UUID
    folder_id: UUID | None
    name: str
    mime: str
    added_at: datetime


class DocumentTreeResult(TreeRecord):
    spaces: tuple[DocumentTreeSpace, ...] = ()
    folders: tuple[DocumentTreeFolder, ...] = ()
    documents: tuple[DocumentTreeDocument, ...] = ()
    truncated: bool = False
