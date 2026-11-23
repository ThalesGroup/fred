# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Shared per-skill opt-outs preserve independent concurrent administrator writes."""

import asyncio

import pytest
from control_plane_backend.platform_skills.store import PlatformSkillPolicyStore
from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.mark.asyncio
async def test_independent_stores_see_atomic_concurrent_updates(
    control_plane_sql_engine: AsyncEngine,
) -> None:
    first = PlatformSkillPolicyStore(control_plane_sql_engine)
    second = PlatformSkillPolicyStore(control_plane_sql_engine)
    assert await first.list_disabled_skill_names() == set()
    assert await second.get_enabled("unknown") is None

    await asyncio.gather(
        first.set_enabled(name="mermaid", enabled=False, updated_by="alice"),
        second.set_enabled(name="grill-me", enabled=False, updated_by="bob"),
    )
    assert await first.list_disabled_skill_names() == {"mermaid", "grill-me"}
    assert await second.list_disabled_skill_names() == {"mermaid", "grill-me"}
    assert await first.get_enabled("mermaid") is False

    await asyncio.gather(
        first.set_enabled(name="mermaid", enabled=False, updated_by="alice"),
        second.set_enabled(name="mermaid", enabled=False, updated_by="bob"),
    )
    await second.set_enabled(name="mermaid", enabled=True, updated_by="bob")
    assert await first.list_disabled_skill_names() == {"grill-me"}
    assert await first.get_enabled("mermaid") is True
