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

"""What one outbound call is given, and what can influence it.

The provider is the only thing that answers "which credential, and on whose
behalf", so these tests pin both halves: the person's bearer and nothing else
with the flag off, and the workload bearer plus a grant composed solely from the
run record with it on.
"""

from __future__ import annotations

import logging
import time

import pytest
from fred_core.security.backend_to_backend_auth import M2MAuthConfig, M2MTokenProvider
from fred_core.security.delegation import (
    GRANT_PARAM_AGENT,
    GRANT_PARAM_PERSON,
    GRANT_PARAM_RUN,
    DelegationConfig,
)
from fred_core.security.structure import (
    M2MSecurity,
    SecurityConfiguration,
    UserSecurity,
)
from fred_runtime.common.outbound_credentials import (
    DelegatedCredentialProvider,
    DelegationConfigurationError,
    DelegationRuntime,
    ImmutableRunRecordSource,
    PersonCredentialProvider,
    RunRecord,
    RunRecordStore,
    attach_grant,
    build_delegation_runtime,
    grant_query_url,
    resolve_credential_provider,
    static_person_provider,
)
from fred_runtime.runtime_support.authority import DelegationUnavailableError
from pydantic import AnyUrl

# Env var name used only to point the real token provider at a secret that does
# not exist, so its failure path runs without any network.
ABSENT_SECRET_ENV = "FRED_TEST_ABSENT_WORKLOAD_SECRET"  # pragma: allowlist secret


class FakeWorkloadTokens(M2MTokenProvider):
    """Stands in for `M2MTokenProvider`.

    Models the one method callers use: an async `get_token()` returning the
    current token string. `rotate()` is how a test expires one token and issues
    the next, which is what the real provider does on its own when its cached
    token nears expiry.
    """

    def __init__(self, *tokens: str) -> None:
        self._tokens = list(tokens) or ["workload-token-1"]
        self._index = 0
        self.calls = 0

    def rotate(self) -> None:
        self._index = min(self._index + 1, len(self._tokens) - 1)

    async def get_token(self) -> str:
        self.calls += 1
        return self._tokens[self._index]


def enabled_runtime(
    tokens: FakeWorkloadTokens | None = None,
) -> DelegationRuntime:
    return DelegationRuntime(
        config=DelegationConfig(enabled=True, allowed_callers=["agent-backend"]),
        token_provider=tokens or FakeWorkloadTokens(),
    )


def admitted(runtime: DelegationRuntime, **overrides) -> RunRecord:
    record = RunRecord(
        run_id=overrides.pop("run_id", "run-1"),
        person_id=overrides.pop("person_id", "person-1"),
        agent_id=overrides.pop("agent_id", "agent-1"),
        roles=overrides.pop("roles", ("reader",)),
        team_id=overrides.pop("team_id", "team-1"),
        **overrides,
    )
    return runtime.records.put(record)


# ---------------------------------------------------------------------------
# Flag off — today's behaviour, unchanged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_with_the_flag_off_the_header_is_the_persons_bearer_and_nothing_else():
    provider = static_person_provider("person-bearer")

    credentials = await provider.credentials()

    assert credentials.authorization == "Bearer person-bearer"
    assert credentials.parameters == {}
    assert credentials.delegated is False


@pytest.mark.asyncio
async def test_the_person_provider_reads_its_token_at_call_time():
    """A refresh in place must be seen by a call made after it, so the provider
    holds a getter, not a string."""
    token = "first"

    async def _current() -> str:
        return token

    provider = PersonCredentialProvider(_current)
    assert (await provider.credentials()).authorization == "Bearer first"

    token = "refreshed"
    assert (await provider.credentials()).authorization == "Bearer refreshed"


@pytest.mark.asyncio
async def test_no_credential_at_all_yields_no_authorization_header():
    assert (await static_person_provider(None).credentials()).authorization is None


# ---------------------------------------------------------------------------
# Flag on — the grant comes from the record, and only from the record
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_delegated_call_carries_the_workload_bearer_and_the_grant():
    runtime = enabled_runtime(FakeWorkloadTokens("workload-1"))
    admitted(runtime, person_id="alice", run_id="run-7", agent_id="agent-a")
    provider = runtime.provider_for(run_id="run-7", agent_id="agent-a")

    credentials = await provider.credentials()

    assert credentials.authorization == "Bearer workload-1"
    assert credentials.parameters == {
        GRANT_PARAM_PERSON: "alice",
        GRANT_PARAM_RUN: "run-7",
        GRANT_PARAM_AGENT: "agent-a",
    }
    assert credentials.delegated is True


@pytest.mark.asyncio
async def test_a_caller_supplied_token_never_becomes_the_delegated_bearer():
    """The override exists for the person path. Honouring it here would be the
    fallback the once-only rule forbids."""
    runtime = enabled_runtime(FakeWorkloadTokens("workload-1"))
    admitted(runtime)
    provider = runtime.provider_for(run_id="run-1", agent_id="agent-1")

    credentials = await provider.credentials(override_token="someone-elses-bearer")

    assert credentials.authorization == "Bearer workload-1"


@pytest.mark.asyncio
async def test_a_run_without_a_record_makes_no_delegated_call():
    runtime = enabled_runtime()
    provider = runtime.provider_for(run_id="unknown-run", agent_id="agent-1")

    with pytest.raises(DelegationUnavailableError):
        await provider.credentials()


@pytest.mark.asyncio
async def test_the_record_is_the_only_source_of_the_person():
    """Nothing carried on the provider names the person: replacing the record's
    person changes the grant, and nothing else can."""
    runtime = enabled_runtime()
    admitted(runtime, person_id="alice")
    provider = runtime.provider_for(run_id="run-1", agent_id="agent-1")
    assert (await provider.credentials()).parameters[GRANT_PARAM_PERSON] == "alice"

    runtime.records.put(RunRecord(run_id="run-1", person_id="bob", agent_id="agent-1"))
    assert (await provider.credentials()).parameters[GRANT_PARAM_PERSON] == "bob"


@pytest.mark.asyncio
async def test_a_child_names_its_own_agent_on_the_shared_run():
    runtime = enabled_runtime()
    admitted(runtime, person_id="alice", run_id="run-7", agent_id="parent")
    parent = runtime.provider_for(run_id="run-7", agent_id="parent")

    child = parent.for_agent("member-2")
    credentials = await child.credentials()

    assert credentials.parameters[GRANT_PARAM_AGENT] == "member-2"
    assert credentials.parameters[GRANT_PARAM_RUN] == "run-7"
    assert credentials.parameters[GRANT_PARAM_PERSON] == "alice"
    assert (await parent.credentials()).parameters[GRANT_PARAM_AGENT] == "parent"


@pytest.mark.asyncio
async def test_a_child_observes_a_provider_change_made_after_it_was_spawned():
    """The child is handed the provider, not a credential read off it: a
    workload token rotated mid-run is on the child's next call."""
    tokens = FakeWorkloadTokens("workload-1", "workload-2")
    runtime = enabled_runtime(tokens)
    admitted(runtime, run_id="run-7", agent_id="parent")
    child = runtime.provider_for(run_id="run-7", agent_id="parent").for_agent("child")

    assert (await child.credentials()).authorization == "Bearer workload-1"
    tokens.rotate()
    assert (await child.credentials()).authorization == "Bearer workload-2"


# ---------------------------------------------------------------------------
# Fail closed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_empty_allow_list_refuses_instead_of_falling_back():
    runtime = DelegationRuntime(
        config=DelegationConfig.model_construct(enabled=True, allowed_callers=[]),
        token_provider=FakeWorkloadTokens(),
    )
    admitted(runtime)
    provider = runtime.provider_for(run_id="run-1", agent_id="agent-1")

    with pytest.raises(DelegationUnavailableError):
        await provider.credentials()


@pytest.mark.asyncio
async def test_a_missing_workload_client_refuses_instead_of_falling_back():
    runtime = DelegationRuntime(
        config=DelegationConfig(enabled=True, allowed_callers=["agent-backend"]),
        token_provider=None,
    )
    admitted(runtime)

    with pytest.raises(DelegationUnavailableError):
        await runtime.provider_for(run_id="run-1", agent_id="agent-1").credentials()


@pytest.mark.asyncio
async def test_an_inert_runtime_is_usable_and_silent_when_the_flag_is_off():
    runtime = DelegationRuntime(config=DelegationConfig())

    assert runtime.enabled is False
    runtime.ensure_usable()  # must not raise


# ---------------------------------------------------------------------------
# The real token provider: contract of the double, and of the failure path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_real_token_provider_serves_a_live_token_without_any_call():
    """Pins the semantics `FakeWorkloadTokens` models: `get_token()` returns the
    cached token while it is still valid, so nothing here reaches the network."""
    provider = M2MTokenProvider(
        M2MAuthConfig(
            keycloak_realm_url="https://realm.invalid/realms/fred",
            client_id="agent-backend",
            secret_env=ABSENT_SECRET_ENV,
        )
    )
    provider._token = "cached-workload-token"  # noqa: SLF001 — pinning the cache itself
    provider._exp = int(time.time()) + 300  # noqa: SLF001

    assert await provider.get_token() == "cached-workload-token"


@pytest.mark.asyncio
async def test_a_failing_workload_fetch_never_reports_what_it_was_looking_for(
    caplog, monkeypatch
):
    """A missing workload secret must name neither its setting nor upstream
    detail in the provider, run failure, or log line."""
    monkeypatch.delenv(ABSENT_SECRET_ENV, raising=False)
    real = M2MTokenProvider(
        M2MAuthConfig(
            keycloak_realm_url="https://realm.invalid/realms/fred",
            client_id="agent-backend",
            secret_env=ABSENT_SECRET_ENV,
        )
    )
    runtime = DelegationRuntime(
        config=DelegationConfig(enabled=True, allowed_callers=["agent-backend"]),
        token_provider=real,
    )

    caplog.clear()
    with caplog.at_level(logging.ERROR):
        with pytest.raises(DelegationUnavailableError) as raised:
            await runtime.workload_token()

    assert ABSENT_SECRET_ENV not in str(raised.value)
    assert ABSENT_SECRET_ENV not in caplog.text
    assert raised.value.__cause__ is None
    assert raised.value.reason == "delegation_unavailable"


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------


def security_configuration(
    *, delegation_enabled: bool, user_enabled: bool
) -> SecurityConfiguration:
    return SecurityConfiguration(
        m2m=M2MSecurity(
            enabled=True,
            realm_url=AnyUrl("http://identity.invalid/realms/fred"),
            client_id="agent-backend",
        ),
        user=UserSecurity(
            enabled=user_enabled,
            realm_url=AnyUrl("http://identity.invalid/realms/fred"),
            client_id="app",
        ),
        delegation=DelegationConfig(
            enabled=delegation_enabled, allowed_callers=["agent-backend"]
        ),
    )


def test_the_flag_on_without_user_authentication_refuses_to_start():
    with pytest.raises(DelegationConfigurationError) as raised:
        build_delegation_runtime(
            security_configuration(delegation_enabled=True, user_enabled=False),
            user_authentication_enabled=False,
        )

    assert "user authentication" in str(raised.value)


def test_the_flag_off_leaves_disabled_authentication_exactly_as_it_was():
    runtime = build_delegation_runtime(
        security_configuration(delegation_enabled=False, user_enabled=False),
        user_authentication_enabled=False,
    )

    assert runtime.enabled is False


def test_the_flag_on_with_user_authentication_builds_a_workload_token_provider():
    runtime = build_delegation_runtime(
        security_configuration(delegation_enabled=True, user_enabled=True),
        user_authentication_enabled=True,
    )

    assert runtime.enabled is True
    runtime.ensure_usable()
    # The client the workload token is minted for: what a receiver reads off the
    # token to decide whether this caller may speak for a person, and what the
    # admission audit names as the caller.
    assert runtime.workload_client_id == "agent-backend"


def test_workload_refresh_cooldown_is_forwarded_to_the_token_provider():
    security = security_configuration(delegation_enabled=True, user_enabled=True)
    security = security.model_copy(
        update={
            "m2m": security.m2m.model_copy(
                update={"refresh_failure_cooldown_seconds": 17.0}
            )
        }
    )

    runtime = build_delegation_runtime(security, user_authentication_enabled=True)

    assert runtime._token_provider is not None  # noqa: SLF001
    assert (  # noqa: SLF001
        runtime._token_provider.cfg.refresh_failure_cooldown_seconds == 17.0
    )


def test_the_flag_off_carries_no_workload_client_to_name():
    runtime = build_delegation_runtime(
        security_configuration(delegation_enabled=False, user_enabled=True),
        user_authentication_enabled=True,
    )

    assert runtime.workload_client_id is None


def test_no_security_configuration_at_all_is_an_inert_runtime():
    assert (
        build_delegation_runtime(None, user_authentication_enabled=False).enabled
        is False
    )


# ---------------------------------------------------------------------------
# Where the grant travels
# ---------------------------------------------------------------------------


def test_the_grant_is_a_body_field_when_the_request_has_a_json_body():
    kwargs = attach_grant({"json": {"query": "q"}}, {"person": "alice"})

    assert kwargs["json"] == {"query": "q", "person": "alice"}
    assert "params" not in kwargs


def test_the_grant_is_a_query_parameter_when_there_is_no_json_body():
    kwargs = attach_grant({"params": {"limit": 10}}, {"person": "alice"})

    assert kwargs["params"] == {"limit": 10, "person": "alice"}


def test_a_non_object_json_body_falls_back_to_query_parameters():
    kwargs = attach_grant({"json": ["a", "b"]}, {"person": "alice"})

    assert kwargs["json"] == ["a", "b"]
    assert kwargs["params"] == {"person": "alice"}


def test_an_endpoint_url_carries_the_grant_without_losing_its_own_query():
    url = grant_query_url(
        "https://kf.invalid/mcp?tenant=acme", {"person": "alice", "run": "run-1"}
    )

    assert url.startswith("https://kf.invalid/mcp?")
    assert "tenant=acme" in url
    assert "person=alice" in url
    assert "run=run-1" in url


def test_a_grant_on_the_endpoint_replaces_a_same_named_query_parameter():
    url = grant_query_url("https://kf.invalid/mcp?person=mallory", {"person": "alice"})

    assert "person=mallory" not in url
    assert "person=alice" in url


# ---------------------------------------------------------------------------
# Resolution order
# ---------------------------------------------------------------------------


def test_an_explicit_provider_wins_over_the_one_carried_by_the_holder():
    explicit = static_person_provider("explicit")
    holder = type(
        "Holder", (), {"credential_provider": static_person_provider("held")}
    )()

    assert resolve_credential_provider(explicit=explicit, holder=holder) is explicit


def test_the_holders_provider_is_used_when_the_client_has_none_of_its_own():
    held = static_person_provider("held")
    holder = type("Holder", (), {"credential_provider": held})()

    assert resolve_credential_provider(holder=holder) is held


@pytest.mark.asyncio
async def test_a_client_with_no_provider_anywhere_keeps_its_own_token_path():
    async def _person_token() -> str:
        return "person-bearer"

    provider = resolve_credential_provider(person_token_getter=_person_token)

    assert provider.delegated is False
    assert (await provider.credentials()).authorization == "Bearer person-bearer"


def test_a_holder_carrying_no_provider_is_not_mistaken_for_one():
    holder = type("Holder", (), {"credential_provider": None})()

    assert isinstance(
        resolve_credential_provider(holder=holder), PersonCredentialProvider
    )


# ---------------------------------------------------------------------------
# The record store
# ---------------------------------------------------------------------------


def test_a_released_record_leaves_the_run_unable_to_call():
    store = RunRecordStore()
    store.put(RunRecord(run_id="run-1", person_id="alice", agent_id="agent-1"))
    assert store.get("run-1") is not None

    store.discard("run-1")

    assert store.get("run-1") is None
    assert len(store) == 0


def test_a_record_left_behind_by_a_run_that_never_ended_is_dropped():
    """A run refused after admission, or a client gone before the first event,
    releases nothing itself — the next admission is what clears it."""
    store = RunRecordStore(max_age_seconds=60.0)
    store.put(
        RunRecord(
            run_id="abandoned",
            person_id="alice",
            agent_id="agent-1",
            started_at=time.time() - 3600.0,
        )
    )

    store.put(RunRecord(run_id="admitted", person_id="bob", agent_id="agent-1"))

    assert store.get("abandoned") is None
    assert store.get("admitted") is not None


def test_a_record_of_a_run_still_inside_its_budget_is_kept():
    store = RunRecordStore(max_age_seconds=3600.0)
    store.put(
        RunRecord(
            run_id="running",
            person_id="alice",
            agent_id="agent-1",
            started_at=time.time() - 60.0,
        )
    )

    store.put(RunRecord(run_id="admitted", person_id="bob", agent_id="agent-1"))

    assert store.get("running") is not None
    assert len(store) == 2


def test_the_record_keeps_what_admission_verified():
    record = RunRecord(
        run_id="run-1",
        person_id="alice",
        agent_id="agent-1",
        roles=("reader", "writer"),
        team_id="team-1",
    )

    assert record.mode == "attended"
    assert record.parent_run_id is None
    assert record.roles == ("reader", "writer")
    assert record.started_at > 0


def test_a_delegated_provider_reports_the_run_it_belongs_to():
    runtime = enabled_runtime()
    provider = runtime.provider_for(run_id="run-7", agent_id="agent-1")

    assert isinstance(provider, DelegatedCredentialProvider)
    assert provider.run_id == "run-7"
    assert provider.agent_id == "agent-1"


@pytest.mark.asyncio
async def test_durable_source_is_checked_on_every_delegated_call():
    runtime = enabled_runtime()
    local = admitted(runtime, agent_id="instance-1", agent_instance_id="instance-1")
    durable = RunRecord(
        run_id=local.run_id,
        person_id=local.person_id,
        agent_id="template-1",
        agent_instance_id="instance-1",
        team_id=local.team_id,
        mode="background",
    )
    provider = runtime.provider_for(run_id=local.run_id, agent_id="instance-1")
    assert isinstance(provider, DelegatedCredentialProvider)
    provider = provider.for_agent("template-1").with_record_source(
        ImmutableRunRecordSource(durable), root_agent_id="template-1"
    )

    credentials = await provider.credentials()
    assert credentials.parameters[GRANT_PARAM_PERSON] == "person-1"
    assert credentials.parameters[GRANT_PARAM_AGENT] == "template-1"


@pytest.mark.asyncio
async def test_durable_source_tampering_fails_before_workload_token():
    tokens = FakeWorkloadTokens()
    runtime = enabled_runtime(tokens)
    local = admitted(runtime, agent_id="instance-1", agent_instance_id="instance-1")
    tampered = RunRecord(
        run_id=local.run_id,
        person_id="different-person",
        agent_id="template-1",
        agent_instance_id="instance-1",
    )
    provider = runtime.provider_for(run_id=local.run_id, agent_id="template-1")
    assert isinstance(provider, DelegatedCredentialProvider)
    provider = provider.with_record_source(
        ImmutableRunRecordSource(tampered), root_agent_id="template-1"
    )

    with pytest.raises(DelegationUnavailableError):
        await provider.credentials()
    assert tokens.calls == 0


@pytest.mark.asyncio
async def test_local_revocation_stops_durable_provider_before_workload_token():
    tokens = FakeWorkloadTokens()
    runtime = enabled_runtime(tokens)
    local = admitted(runtime, agent_id="instance-1", agent_instance_id="instance-1")
    durable = RunRecord(
        run_id=local.run_id,
        person_id=local.person_id,
        agent_id="template-1",
        agent_instance_id="instance-1",
    )
    provider = runtime.provider_for(run_id=local.run_id, agent_id="template-1")
    assert isinstance(provider, DelegatedCredentialProvider)
    provider = provider.with_record_source(
        ImmutableRunRecordSource(durable), root_agent_id="template-1"
    )
    runtime.records.mark_terminal(local.run_id, reason="authority_lost")

    with pytest.raises(DelegationUnavailableError):
        await provider.credentials()
    assert tokens.calls == 0
