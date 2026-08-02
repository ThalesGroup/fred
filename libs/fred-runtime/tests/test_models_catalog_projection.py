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
`_project_model_catalog_entries` (OBSERV-02 v3, `AGENT-CAPABILITY-RFC.md`
§8.7) — the pure grouping logic behind `GET /agents/models-catalog`.

Pulled out of the route as a standalone function specifically so it's
unit-testable without a running FastAPI app (agent_app.py has no existing
TestClient harness).
"""

from __future__ import annotations

from fred_core.common import ModelConfiguration
from fred_runtime.app.agent_app import _project_model_catalog_entries
from fred_runtime.model_routing.catalog import ModelCatalog
from fred_runtime.model_routing.contracts import ModelCapability, ModelProfile


def _profile(
    profile_id: str,
    *,
    capability: ModelCapability = ModelCapability.CHAT,
    provider: str | None = "openai",
    name: str | None = "gpt-5.1",
    description: str | None = None,
    supports_thinking: bool = False,
) -> ModelProfile:
    return ModelProfile(
        profile_id=profile_id,
        capability=capability,
        model=ModelConfiguration(provider=provider, name=name),
        description=description,
        supports_thinking=supports_thinking,
    )


def _catalog(profiles: tuple[ModelProfile, ...]) -> ModelCatalog:
    return ModelCatalog(
        default_profile_by_capability={ModelCapability.CHAT: profiles[0].profile_id}
        if profiles
        else {},
        profiles=profiles,
    )


def test_one_entry_per_distinct_provider_and_name() -> None:
    # Same (provider, name) used by two different routing capabilities
    # (chat + language) — one admin enablement decision, not two.
    catalog = _catalog(
        (
            _profile("chat.openai.gpt51", capability=ModelCapability.CHAT),
            _profile("language.openai.gpt51", capability=ModelCapability.LANGUAGE),
        )
    )

    entries = _project_model_catalog_entries(catalog)

    assert len(entries) == 1
    assert entries[0].provider == "openai"
    assert entries[0].name == "gpt-5.1"


def test_sibling_profiles_sharing_provider_and_name_are_all_listed() -> None:
    # TEAM-ROUTING-POLICY-RFC.md §7.1: enablement is coarser (provider, name)
    # than routing (profile_id) — profile_ids must carry every sibling so
    # control-plane/frontend can still offer each one once the capability is
    # enabled, and translate any of them back to this entry's capability id.
    catalog = _catalog(
        (
            _profile("chat.openai.gpt51.default", provider="openai", name="gpt-5.1"),
            _profile("chat.openai.gpt51.creative", provider="openai", name="gpt-5.1"),
        )
    )

    entries = _project_model_catalog_entries(catalog)

    assert len(entries) == 1
    assert entries[0].profile_ids == [
        "chat.openai.gpt51.default",
        "chat.openai.gpt51.creative",
    ]


def test_distinct_provider_name_pairs_have_their_own_profile_ids() -> None:
    catalog = _catalog(
        (
            _profile("p1", provider="openai", name="gpt-5.1"),
            _profile("p2", provider="azure", name="gpt-5.1"),
        )
    )

    entries = _project_model_catalog_entries(catalog)

    by_provider = {e.provider: e.profile_ids for e in entries}
    assert by_provider == {"openai": ["p1"], "azure": ["p2"]}


def test_distinct_providers_or_names_produce_distinct_entries() -> None:
    catalog = _catalog(
        (
            _profile("p1", provider="openai", name="gpt-5.1"),
            _profile("p2", provider="azure", name="gpt-5.1"),
            _profile("p3", provider="openai", name="gpt-4o"),
        )
    )

    entries = _project_model_catalog_entries(catalog)

    assert {(e.provider, e.name) for e in entries} == {
        ("openai", "gpt-5.1"),
        ("azure", "gpt-5.1"),
        ("openai", "gpt-4o"),
    }
    assert len({e.id for e in entries}) == 3  # every id is unique too


def test_entry_id_uses_the_shared_fred_sdk_helper() -> None:
    from fred_sdk.contracts.capability.manifest import model_capability_id

    catalog = _catalog((_profile("p1", provider="openai", name="gpt-5.1"),))

    entries = _project_model_catalog_entries(catalog)

    assert entries[0].id == model_capability_id("openai", "gpt-5.1")


def test_empty_catalog_returns_no_entries() -> None:
    assert _project_model_catalog_entries(_catalog(())) == []


# ---------------------------------------------------------------------------
# thinking_profile_ids (REASON-01, MODEL-REASONING-ENABLEMENT-RFC.md §5.3)
# ---------------------------------------------------------------------------


def test_thinking_profile_ids_is_the_supports_thinking_subset() -> None:
    # The §5.3 case verbatim, and the reason aptitude is per profile: the same
    # (provider, name) is declared twice — reasoning-capable as a chat profile,
    # not as a language one. One model entry, one thinking profile.
    catalog = _catalog(
        (
            _profile(
                "chat.mistral.small",
                capability=ModelCapability.CHAT,
                name="mistral-small-latest",
                supports_thinking=True,
            ),
            _profile(
                "language.mistral.small",
                capability=ModelCapability.LANGUAGE,
                name="mistral-small-latest",
            ),
        )
    )

    entries = _project_model_catalog_entries(catalog)

    assert len(entries) == 1
    assert entries[0].profile_ids == ["chat.mistral.small", "language.mistral.small"]
    assert entries[0].thinking_profile_ids == ["chat.mistral.small"]


def test_thinking_profile_ids_is_empty_when_no_profile_declares_aptitude() -> None:
    # Empty is what makes the admin row show NO reasoning control at all
    # (§5.3): aptitude is not an administrator's choice.
    catalog = _catalog((_profile("p1"), _profile("p2", name="gpt-4o")))

    entries = _project_model_catalog_entries(catalog)

    assert all(entry.thinking_profile_ids == [] for entry in entries)


def test_thinking_profile_ids_never_leaks_across_models() -> None:
    catalog = _catalog(
        (
            _profile("thinker", name="gpt-5.1", supports_thinking=True),
            _profile("plain", name="gpt-4o"),
        )
    )

    entries = _project_model_catalog_entries(catalog)

    assert {e.name: e.thinking_profile_ids for e in entries} == {
        "gpt-5.1": ["thinker"],
        "gpt-4o": [],
    }
