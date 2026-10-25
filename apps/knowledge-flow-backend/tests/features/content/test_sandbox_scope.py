from types import SimpleNamespace

import pytest
from fred_core.common import OwnerFilter
from fred_core.security.rebac.noop_engine import NoopRebacEngine
from fred_pod.security.structure import KeycloakUser

from knowledge_flow_backend.features.content.sandbox_scope import authorize_corpus_source


class _Context:
    def __init__(self, *, tags=("team-tag",), source_tag="fred", size=120):
        self.metadata = SimpleNamespace(
            source=SimpleNamespace(source_tag=source_tag),
            tags=SimpleNamespace(tag_ids=list(tags)),
            document_name="report.xlsx",
        )
        self.size = size
        self.checked = []

    def get_metadata_store(self):
        return SimpleNamespace(get_metadata_by_uid=self._get_metadata)

    async def _get_metadata(self, uid):
        return self.metadata

    def get_rebac_engine(self):
        return SimpleNamespace(
            require_active_account=self._active,
            check_user_team_permission_or_raise=self._team,
            check_user_permission_or_raise=self._check,
        )

    async def _active(self, user_id):
        self.checked.append((user_id, "active"))

    async def _team(self, user, permission, team_id):
        self.checked.append((user.uid, permission.value, team_id))

    async def _check(self, user, permission, uid):
        self.checked.append((user.uid, permission.value, uid))

    def get_content_store(self):
        return SimpleNamespace(get_file_metadata=lambda uid: SimpleNamespace(size=self.size))

    def get_tag_store(self):
        async def filter_owned_tag_ids(owner_id, tag_ids):
            owner_tags = {"personal-tag"} if owner_id == "u1" else {"team-tag"}
            return tag_ids & owner_tags

        return SimpleNamespace(filter_owned_tag_ids=filter_owned_tag_ids)


class _Tags:
    def __init__(self, allowed):
        self.allowed = allowed
        self.calls = []

    async def list_authorized_tags_ids(self, user, owner_filter, team_id):
        self.calls.append((owner_filter, team_id))
        return self.allowed


@pytest.mark.asyncio
async def test_team_source_requires_membership_in_that_team() -> None:
    user = KeycloakUser(uid="u1", username="u1", roles=[])
    context = _Context()
    tags = _Tags({"other-team-tag"})
    with pytest.raises(PermissionError):
        await authorize_corpus_source(user, "team-1", "doc-1", context=context, tag_service=tags)
    assert tags.calls == [(OwnerFilter.TEAM, "team-1")]
    assert context.checked == [("u1", "active"), ("u1", "can_read", "team-1")]


@pytest.mark.asyncio
async def test_personal_source_uses_personal_scope_and_document_permission() -> None:
    user = KeycloakUser(uid="u1", username="u1", roles=[])
    context = _Context(tags=("personal-tag",))
    tags = _Tags({"personal-tag"})
    source = await authorize_corpus_source(user, "personal-1234", "doc-1", context=context, tag_service=tags)
    assert source.name == "report.xlsx"
    assert tags.calls == [(OwnerFilter.PERSONAL, None)]
    assert context.checked == [("u1", "active"), ("u1", "read", "doc-1")]


@pytest.mark.asyncio
async def test_personal_source_excludes_shared_team_owned_tag() -> None:
    user = KeycloakUser(uid="u1", username="u1", roles=[])
    context = _Context(tags=("team-tag",))
    with pytest.raises(PermissionError, match="outside the conversation scope"):
        await authorize_corpus_source(user, "personal-1234", "doc-1", context=context, tag_service=_Tags({"team-tag"}))


@pytest.mark.asyncio
async def test_sandbox_files_fail_closed_without_rebac() -> None:
    user = KeycloakUser(uid="u1", username="u1", roles=[])
    context = _Context()
    context.get_rebac_engine = lambda: NoopRebacEngine()
    with pytest.raises(PermissionError, match="require access control"):
        await authorize_corpus_source(user, "personal-1234", "doc-1", context=context, tag_service=_Tags({"team-tag"}))


@pytest.mark.asyncio
async def test_fast_ingest_is_not_exposed_as_corpus_document() -> None:
    user = KeycloakUser(uid="u1", username="u1", roles=[])
    with pytest.raises(FileNotFoundError):
        await authorize_corpus_source(
            user,
            "team-1",
            "attachment-doc",
            context=_Context(source_tag="fast_ingest"),
            tag_service=_Tags({"team-tag"}),
        )
