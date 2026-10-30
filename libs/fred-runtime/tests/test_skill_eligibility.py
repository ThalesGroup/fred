# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Public catalog and loading rules across independent execution scopes."""

from pathlib import Path

import pytest
from fred_runtime.skills.catalog import PlatformSkills


def publish(root: Path, name: str, flags: str = "") -> None:
    folder = root / name
    folder.mkdir()
    (folder / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Useful procedure\n{flags}---\nPROCEDURE\n"
    )


def test_common_loader_enforces_invocation_controls_without_an_http_route(
    tmp_path: Path,
) -> None:
    from fred_runtime.skills.tools import load_skill
    from test_platform_skills import binding

    publish(tmp_path, "internal", "user-invocable: false\n")
    publish(tmp_path, "interview", "disable-model-invocation: true\n")
    publish(tmp_path, "other")
    source = PlatformSkills.from_directory(str(tmp_path))
    with pytest.raises(ValueError, match="user"):
        load_skill(source, "internal", origin="user", load_id="user", agent_id="test")
    for bound in (binding(), binding("other")):
        with pytest.raises(ValueError, match="user"):
            load_skill(
                source,
                "internal",
                origin="user",
                load_id="bound-user",
                agent_id="test",
                binding=bound,
            )
    with pytest.raises(ValueError, match="unavailable"):
        load_skill(
            source, "interview", origin="agent", load_id="agent", agent_id="test"
        )
    content, attribution = load_skill(
        source, "interview", origin="user", load_id="selected", agent_id="test"
    )
    assert "PROCEDURE" in content and attribution.origin == "user"


def test_agent_only_skill_cannot_be_selected_by_a_user(tmp_path: Path) -> None:
    publish(tmp_path, "internal", "user-invocable: false\n")
    skills = PlatformSkills.from_directory(str(tmp_path))
    assert skills.catalog.skills[0].user_invocable is False
    assert "PROCEDURE" in skills.for_execution().read("internal")
    with pytest.raises(ValueError, match="user"):
        skills.for_execution(selected_names=("internal",))


def test_explicit_only_skill_requires_a_current_selection(tmp_path: Path) -> None:
    publish(tmp_path, "interview", "disable-model-invocation: true\n")
    skills = PlatformSkills.from_directory(str(tmp_path))
    with pytest.raises(ValueError, match="unavailable"):
        skills.for_execution().read("interview")
    assert "PROCEDURE" in skills.for_execution(selected_names=("interview",)).read(
        "interview"
    )
    assert "interview" not in skills.for_execution().prompt
    assert skills.for_catalog().catalog.skills[0].name == "interview"


def test_invalid_invocation_flags_exclude_only_the_bad_skill(tmp_path: Path) -> None:
    publish(tmp_path, "bad", 'user-invocable: "false"\n')
    publish(tmp_path, "good")
    skills = PlatformSkills.from_directory(str(tmp_path))
    assert [s.name for s in skills.catalog.skills] == ["good"]


def test_packaged_policy_is_scoped_without_mutating_the_shared_catalog() -> None:
    skills = PlatformSkills.from_directory("package")
    assert all(s.builtin for s in skills.catalog.skills)
    denied = skills.for_execution(disabled_names=("graph",))
    with pytest.raises(ValueError, match="unavailable"):
        denied.read("graph")
    assert "graph" not in {s.name for s in denied.catalog.skills}
    assert "graph" in {s.name for s in skills.catalog.skills}
    assert skills.for_execution().read("graph")


def test_packaged_policy_does_not_disable_a_custom_homonym(tmp_path: Path) -> None:
    publish(tmp_path, "graph")
    skills = PlatformSkills.from_directory(str(tmp_path))
    assert not skills.catalog.skills[0].builtin
    assert skills.for_execution(disabled_names=("graph",)).read("graph")


def test_runtime_rebinding_uses_original_catalog_after_selection_and_policy_changes() -> (
    None
):
    from fred_runtime.react.react_runtime import ReActRuntime
    from fred_sdk.contracts.runtime import RuntimeServices
    from test_history import _PingAgent
    from test_platform_skills import binding

    runtime = ReActRuntime(
        definition=_PingAgent(),
        services=RuntimeServices(skills=PlatformSkills.from_directory("package")),
    )
    runtime.bind(binding())
    assert runtime.services.skills is not None
    assert "grill-me" not in {s.name for s in runtime.services.skills.catalog.skills}
    runtime.bind(binding("grill-me"))
    assert runtime.services.skills.read("grill-me")
    runtime.bind(binding().model_copy(update={"disabled_platform_skills": ("graph",)}))
    assert "graph" not in {s.name for s in runtime.services.skills.catalog.skills}
    runtime.bind(binding())
    assert runtime.services.skills.read("graph")
