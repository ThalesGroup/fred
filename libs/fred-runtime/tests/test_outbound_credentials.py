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
with the flag off, and with it on a grant composed solely from the run record,
beside a workload token the provider releases only to a live run.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator
from contextlib import contextmanager

import httpx
import pytest
from conftest import (
    IAM_MARKER,
    WORKLOAD_SECRET_ENV,
    MockIdentityProvider,
    StaticWorkloadTokens,
    admitted_provider,
)
from fred_core.security.backend_to_backend_auth import TokenLease
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
from fred_runtime.common import kf_vectorsearch_client
from fred_runtime.common.outbound_credentials import (
    DelegatedCredentialProvider,
    DelegationConfigurationError,
    DelegationRuntime,
    PersonCredentialProvider,
    RunRecord,
    attach_grant,
    build_delegation_runtime,
    delegation_enabled,
    grant_query_url,
    resolve_credential_provider,
    set_delegation_runtime,
    static_person_provider,
)
from fred_runtime.runtime_support.authority import DelegationUnavailableError
from fred_runtime.runtime_support.run_scope import RunScope
from pydantic import AnyUrl


class FakeWorkloadTokens(StaticWorkloadTokens):
    """Provide deterministic token/lease reads and explicit rotation without IAM.

    Call `rotate()` to advance the token returned to a delegated request.
    """

    def __init__(self, *tokens: str) -> None:
        super().__init__()
        self._tokens = list(tokens) or ["workload-token-1"]
        self._index = 0
        self.calls = 0

    def rotate(self) -> None:
        self._index = min(self._index + 1, len(self._tokens) - 1)

    async def get_token(self) -> str:
        self.calls += 1
        return self._tokens[self._index]

    async def get_token_lease(self) -> TokenLease:
        return TokenLease(await self.get_token(), self._generation)

    async def refresh_rejected(self, lease: TokenLease) -> TokenLease:
        if lease.generation == self._generation:
            self.rotate()
            self._generation += 1
        return await self.get_token_lease()


def enabled_runtime(
    tokens: FakeWorkloadTokens | None = None,
) -> DelegationRuntime:
    return DelegationRuntime(
        config=DelegationConfig(act_for_people=True),
        token_provider=tokens or FakeWorkloadTokens(),
    )


def admitted(runtime: DelegationRuntime, **overrides) -> RunRecord:
    record = RunRecord(
        run_id=overrides.pop("run_id", "run-1"),
        person_id=overrides.pop("person_id", "person-1"),
        agent_id=overrides.pop("agent_id", "agent-1"),
        **overrides,
    )
    return runtime.records.admit(record)


def delegated(runtime: DelegationRuntime, **names: str) -> DelegatedCredentialProvider:
    provider = runtime.provider_for(
        run_id=names.get("run_id", "run-1"), agent_id=names.get("agent_id", "agent-1")
    )
    assert isinstance(provider, DelegatedCredentialProvider)
    return provider


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
async def test_resolving_a_delegated_grant_acquires_no_token(monkeypatch):
    """The grant comes from the record alone; the workload bearer is the HTTP
    authentication adapter's to obtain, once per request."""
    identity = MockIdentityProvider(monkeypatch, "workload-1")
    provider = admitted_provider(identity.provider)

    credentials = await provider.credentials()

    assert credentials.parameters == {
        GRANT_PARAM_PERSON: "alice",
        GRANT_PARAM_RUN: "run-7",
        GRANT_PARAM_AGENT: "agent-a",
    }
    assert credentials.delegated is True
    assert credentials.authorization is None
    assert identity.events == []
    assert identity.issued == []
    assert (await provider.get_token_lease()).token == "workload-1"
    assert identity.acquisitions == 1


@pytest.mark.asyncio
async def test_a_caller_supplied_token_never_becomes_the_delegated_bearer():
    """The override exists for the person path. Honouring it here would be the
    fallback the once-only rule forbids."""
    runtime = enabled_runtime(FakeWorkloadTokens("workload-1"))
    admitted(runtime)
    provider = delegated(runtime)

    credentials = await provider.credentials(override_token="someone-elses-bearer")

    assert "someone-elses-bearer" not in repr(credentials)
    assert (await provider.get_token_lease()).token == "workload-1"


@pytest.mark.asyncio
async def test_a_run_without_a_record_makes_no_delegated_call():
    runtime = enabled_runtime()
    provider = runtime.provider_for(run_id="unknown-run", agent_id="agent-1")

    with pytest.raises(DelegationUnavailableError):
        await provider.credentials()


@pytest.mark.parametrize("acquisition", ["lease", "renewal"])
@pytest.mark.asyncio
async def test_a_record_removed_during_token_acquisition_releases_no_token(
    acquisition: str,
):
    started = asyncio.Event()
    release = asyncio.Event()

    class _DelayedTokens(FakeWorkloadTokens):
        async def get_token(self) -> str:
            started.set()
            await release.wait()
            return "workload-after-renewal"

    runtime = enabled_runtime(_DelayedTokens())
    admitted(runtime)
    provider = delegated(runtime)
    call = asyncio.create_task(
        provider.get_token_lease()
        if acquisition == "lease"
        else provider.refresh_rejected(TokenLease("rejected", 0))
    )
    await started.wait()
    runtime.records.discard("run-1")
    release.set()
    with pytest.raises(DelegationUnavailableError):
        await call


@pytest.mark.asyncio
async def test_a_closed_scope_cannot_use_a_renewed_token():
    runtime = enabled_runtime()
    admitted(runtime)
    provider = runtime.provider_for(run_id="run-1", agent_id="agent-1")
    with RunScope.open() as scope:
        scope.close()
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

    runtime.records.discard("run-1")
    runtime.records.admit(
        RunRecord(run_id="run-1", person_id="bob", agent_id="agent-1")
    )
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
    child = delegated(runtime, run_id="run-7", agent_id="parent").for_agent("child")

    assert (await child.get_token_lease()).token == "workload-1"
    tokens.rotate()
    assert (await child.get_token_lease()).token == "workload-2"
    assert (await child.credentials()).parameters[GRANT_PARAM_AGENT] == "child"


@pytest.mark.asyncio
async def test_a_retried_call_asks_again_and_keeps_the_same_grant(monkeypatch):
    async def _instant(_delay: float) -> None:
        return None

    monkeypatch.setattr(kf_vectorsearch_client.asyncio, "sleep", _instant)
    tokens = FakeWorkloadTokens("workload-1", "workload-2")
    runtime = enabled_runtime(tokens)
    admitted(runtime)
    provider = delegated(runtime)
    attempts: list[tuple[str, dict[str, str]]] = []

    async def request() -> str:
        # One attempt as a client makes it: the grant, then the adapter's lease.
        credentials = await provider.credentials()
        lease = await provider.get_token_lease()
        attempts.append((lease.token, dict(credentials.parameters)))
        if len(attempts) == 1:
            tokens.rotate()
            raise httpx.ConnectError("synthetic disconnect")
        return "ok"

    assert await kf_vectorsearch_client._with_transient_retry(request) == "ok"
    assert [token for token, _ in attempts] == ["workload-1", "workload-2"]
    assert attempts[0][1] == attempts[1][1]


# ---------------------------------------------------------------------------
# Fail closed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_missing_workload_client_refuses_instead_of_falling_back():
    runtime = DelegationRuntime(
        config=DelegationConfig(act_for_people=True),
        token_provider=None,
    )
    admitted(runtime)
    provider = delegated(runtime)

    with pytest.raises(DelegationUnavailableError):
        await provider.get_token_lease()
    with pytest.raises(DelegationUnavailableError):
        await provider.refresh_rejected(TokenLease("rejected", 0))


@pytest.mark.asyncio
async def test_an_inert_runtime_is_usable_and_silent_when_the_flag_is_off():
    runtime = DelegationRuntime(config=DelegationConfig())

    assert runtime.enabled is False
    runtime.ensure_usable()  # must not raise


@pytest.mark.parametrize(
    ("act_for_people", "accept_delegated_calls"),
    [(True, False), (False, True), (True, True)],
)
def test_outgoing_delegation_follows_act_for_people_alone(
    act_for_people: bool, accept_delegated_calls: bool
):
    # Believing grants from other workloads says nothing about what this pod's
    # own calls present.
    runtime = DelegationRuntime(
        config=DelegationConfig(
            act_for_people=act_for_people,
            accept_delegated_calls=accept_delegated_calls,
        ),
        token_provider=FakeWorkloadTokens(),
    )
    set_delegation_runtime(runtime)
    try:
        assert runtime.enabled is act_for_people
        assert delegation_enabled() is act_for_people
    finally:
        set_delegation_runtime(None)


# ---------------------------------------------------------------------------
# Workload credential failure handling
# ---------------------------------------------------------------------------


class _RecordingHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@contextmanager
def recorded_logs() -> Iterator[_RecordingHandler]:
    """Read every line from the root, which `caplog` stops seeing once a pod
    has installed its logging setup."""
    handler = _RecordingHandler()
    root = logging.getLogger()
    level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        yield handler
    finally:
        root.setLevel(level)
        root.removeHandler(handler)


@pytest.mark.parametrize(
    ("cause", "error_type"),
    [
        ("missing_secret", "RuntimeError"),
        ("refused", "RuntimeError"),
        ("unreachable", "ConnectError"),
    ],
)
@pytest.mark.parametrize("acquisition", ["lease", "renewal"])
@pytest.mark.asyncio
async def test_a_failed_workload_acquisition_logs_its_error_type_only(
    monkeypatch, acquisition: str, cause: str, error_type: str
):
    """One line names the failure's type: never the secret's setting, never
    what the identity provider answered."""
    identity = MockIdentityProvider(monkeypatch, secret=cause != "missing_secret")
    identity.failure = cause if cause != "missing_secret" else None
    provider = admitted_provider(identity.provider)

    with recorded_logs() as logs:
        with pytest.raises(DelegationUnavailableError) as raised:
            if acquisition == "lease":
                await provider.get_token_lease()
            else:
                await provider.refresh_rejected(TokenLease("rejected", 0))

    lines = [
        (record.name, record.levelno, record.getMessage()) for record in logs.records
    ]
    assert lines == [
        (
            "fred_runtime.common.outbound_credentials",
            logging.ERROR,
            f"The workload credential could not be obtained ({error_type}).",
        )
    ]
    for secret_or_upstream in (WORKLOAD_SECRET_ENV, IAM_MARKER):
        assert secret_or_upstream not in str(raised.value)
    assert raised.value.__cause__ is None
    assert raised.value.reason == "delegation_unavailable"


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------


def security_configuration(
    *,
    act_for_people: bool,
    user_enabled: bool,
    accept_delegated_calls: bool = False,
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
            act_for_people=act_for_people,
            accept_delegated_calls=accept_delegated_calls,
        ),
    )


def test_the_flag_on_without_user_authentication_refuses_to_start():
    with pytest.raises(DelegationConfigurationError) as raised:
        build_delegation_runtime(
            security_configuration(act_for_people=True, user_enabled=False),
            user_authentication_enabled=False,
        )

    assert "user authentication" in str(raised.value)


def test_the_flag_off_leaves_disabled_authentication_exactly_as_it_was():
    runtime = build_delegation_runtime(
        security_configuration(act_for_people=False, user_enabled=False),
        user_authentication_enabled=False,
    )

    assert runtime.enabled is False


def test_the_flag_on_with_user_authentication_builds_a_workload_token_provider():
    runtime = build_delegation_runtime(
        security_configuration(act_for_people=True, user_enabled=True),
        user_authentication_enabled=True,
    )

    assert runtime.enabled is True
    runtime.ensure_usable()


def test_accepting_delegated_calls_without_acting_for_people_refuses_to_start():
    with pytest.raises(DelegationConfigurationError) as raised:
        build_delegation_runtime(
            security_configuration(
                act_for_people=False, accept_delegated_calls=True, user_enabled=True
            ),
            user_authentication_enabled=True,
        )

    assert "accept_delegated_calls is on without act_for_people" in str(raised.value)


def test_both_switches_on_with_user_authentication_build_a_usable_runtime():
    runtime = build_delegation_runtime(
        security_configuration(
            act_for_people=True, accept_delegated_calls=True, user_enabled=True
        ),
        user_authentication_enabled=True,
    )

    assert runtime.enabled is True
    runtime.ensure_usable()


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


@pytest.mark.asyncio
async def test_a_terminal_record_stops_the_provider_before_workload_token():
    tokens = FakeWorkloadTokens()
    runtime = enabled_runtime(tokens)
    local = admitted(runtime)
    provider = delegated(runtime)
    runtime.records.mark_terminal(local.run_id)

    with pytest.raises(DelegationUnavailableError):
        await provider.credentials()
    with pytest.raises(DelegationUnavailableError):
        await provider.get_token_lease()
    assert tokens.calls == 0
