import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fred_core import RebacReference, Relation, RelationType, Resource
from fred_core.documents.tag_models import TagRow
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_PATH = Path(__file__).parents[2] / "alembic/backfill/convert_corpus_owners.py"
_SPEC = importlib.util.spec_from_file_location("convert_corpus_owners", _PATH)
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def _owner(folder, owner="alice", kind=Resource.USER):
    return Relation(RebacReference(kind, owner), RelationType.OWNER, RebacReference(Resource.TAGS, folder))


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["dry_run", "apply", "missing", "multiple", "conflict", "json_conflict", "unsupported", "network", "collision", "path_conflict"])
async def test_owner_conversion_is_verified_and_atomic(case):
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(TagRow.__table__.create)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    original = {"a": "alice", "b": "team-1"}
    if case == "collision":
        original["b"] = "personal-alice"
    async with sessions.begin() as session:
        for uid, owner in original.items():
            session.add(
                TagRow(
                    tag_id=uid,
                    type="document",
                    owner_id=owner,
                    name="Root",
                    doc={
                        "owner_id": "wrong" if uid == "b" and case == "json_conflict" else owner,
                        "description": "preserved",
                        "name": "Root",
                        "path": "different" if uid == "b" and case == "path_conflict" else None,
                        "type": "document",
                    },
                )
            )
    rebac = AsyncMock()

    async def relations(resource, **kwargs):
        if resource.id == "a":
            return [_owner("a")]
        if case == "network":
            raise ConnectionError("FGA unavailable")
        if case == "missing":
            return []
        if case == "multiple":
            return [_owner("b", "team-1", Resource.TEAM), _owner("b", "bob")]
        if case == "conflict":
            return [_owner("b", "different", Resource.TEAM)]
        if case == "unsupported":
            return [_owner("b", "team-1", Resource.TAGS)]
        return [_owner("b", original["b"], Resource.TEAM)]

    rebac.list_direct_relations.side_effect = relations
    try:
        if case in {"dry_run", "apply"}:
            async with sessions.begin() as session:
                mapping = await _MODULE.convert_owners(session, rebac, apply=case == "apply")
                assert mapping == {"a": "personal-alice", "b": "team-1"}
        else:
            with pytest.raises((RuntimeError, ConnectionError)):
                async with sessions.begin() as session:
                    await _MODULE.convert_owners(session, rebac, apply=True)
        async with sessions() as session:
            rows = (await session.scalars(select(TagRow))).all()
            assert {row.tag_id: row.owner_id for row in rows} == (mapping if case == "apply" else original)
            for row in rows:
                assert row.doc["description"] == "preserved"
                if case == "apply":
                    assert row.doc["owner_id"] == row.owner_id
        rebac.add_relation.assert_not_called()
        rebac.delete_relation.assert_not_called()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cli_disables_fga_initialization_writes(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from fred_core import OpenFgaRebacConfig

    from knowledge_flow_backend import application_context
    from knowledge_flow_backend.common import config_loader

    config = SimpleNamespace(security=SimpleNamespace(rebac=OpenFgaRebacConfig(api_url="http://localhost:8080", create_store_if_needed=True, sync_schema_on_init=True)))
    monkeypatch.setattr(config_loader, "load_configuration", lambda: config)
    context = MagicMock()
    context.shutdown = AsyncMock()
    construct = MagicMock(return_value=context)
    monkeypatch.setattr(application_context, "ApplicationContext", construct)
    sessions = MagicMock()
    sessions.begin.return_value = AsyncMock()
    monkeypatch.setattr(_MODULE, "make_session_factory", lambda engine: sessions)
    monkeypatch.setattr(_MODULE, "convert_owners", AsyncMock(return_value={}))
    await _MODULE.main(False)
    used_config = construct.call_args.args[0]
    assert used_config.security.rebac.create_store_if_needed is False
    assert used_config.security.rebac.sync_schema_on_init is False
    context.shutdown.assert_awaited_once()
