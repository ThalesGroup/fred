# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Resolve one corpus file within the conversation's team or personal scope."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import PurePosixPath

from fred_core.common import OwnerFilter
from fred_core.common.team_id import is_personal_team_id
from fred_core.security.rebac.rebac_engine import DocumentPermission, TeamPermission
from fred_pod.security.structure import KeycloakUser

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.features.tag.tag_service import TagService

MAX_MOUNTED_FILE_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class AuthorizedCorpusSource:
    document_uid: str
    name: str
    size: int


async def authorize_corpus_source(
    user: KeycloakUser,
    team_id: str,
    document_uid: str,
    *,
    context: ApplicationContext | None = None,
    tag_service: TagService | None = None,
) -> AuthorizedCorpusSource:
    context = context or ApplicationContext.get_instance()
    metadata = await context.get_metadata_store().get_metadata_by_uid(document_uid)
    if metadata is None or metadata.source.source_tag == "fast_ingest":
        raise FileNotFoundError("Corpus document is unavailable")

    rebac = context.get_rebac_engine()
    await rebac.require_active_account(user.uid)
    personal = is_personal_team_id(team_id)
    if not personal:
        await rebac.check_user_team_permission_or_raise(user, TeamPermission.CAN_READ, team_id)
    allowed_tags = await (tag_service or TagService()).list_authorized_tags_ids(
        user,
        OwnerFilter.PERSONAL if personal else OwnerFilter.TEAM,
        None if personal else team_id,
    )
    if not set(metadata.tags.tag_ids or ()).intersection(allowed_tags):
        raise PermissionError("Document is outside the conversation scope")
    await rebac.check_user_permission_or_raise(user, DocumentPermission.READ, document_uid)

    info = await asyncio.to_thread(context.get_content_store().get_file_metadata, document_uid)
    if info.size < 0 or info.size > MAX_MOUNTED_FILE_BYTES:
        raise ValueError("Document exceeds the sandbox file limit")
    name = metadata.document_name
    if not name or name in {".", ".."} or PurePosixPath(name).name != name or "\\" in name or "\x00" in name:
        raise ValueError("Document name is unsafe for a sandbox path")
    return AuthorizedCorpusSource(document_uid=document_uid, name=name, size=info.size)
