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

"""The single place every outbound call asks for its credentials.

Flag off, a provider hands back the person's bearer exactly as before. Flag on,
it hands back the runtime's own workload bearer plus the grant parameters, read
only from the pod-local run record — the one object that names the person, so no
tool argument or model output can influence who a call acts for.
"""

from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Final, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fred_core.security.backend_to_backend_auth import M2MAuthConfig, M2MTokenProvider
from fred_core.security.delegation import (
    GRANT_PARAM_AGENT,
    GRANT_PARAM_PERSON,
    GRANT_PARAM_RUN,
    DelegationConfig,
)
from fred_core.security.structure import SecurityConfiguration

from fred_runtime.runtime_support.authority import DelegationUnavailableError
from fred_runtime.runtime_support.run_budget import (
    DEFAULT_RUN_CEILING_SECONDS,
    RunScope,
)

logger = logging.getLogger(__name__)

TokenGetter = Callable[[], Awaitable[str | None]]

# Attribute an outbound client looks for on the agent-like object it was handed,
# so a shim carries the live provider instead of a copied credential string.
PROVIDER_ATTRIBUTE = "credential_provider"

#: How far past its run ceiling a record may live before a later admission drops
#: it. A run that reaches its ceiling releases its own record, so anything older
#: than this was left behind by a failure and belongs to nobody.
RUN_RECORD_AGE_MARGIN_SECONDS: Final[float] = 60.0


class DelegationConfigurationError(RuntimeError):
    """The pod cannot honour its delegation configuration, so it must not start."""


@dataclass(frozen=True)
class OutboundCredentials:
    """What one outbound call sends: an authorization header value and, under
    delegation, the grant parameters that name the person, run and agent."""

    authorization: str | None = None
    parameters: Mapping[str, str] = field(default_factory=dict)
    delegated: bool = False


@dataclass(frozen=True)
class RunRecord:
    """The pod-local record admission writes from the verified token.

    It is the only source of the grant: nothing reaching the runtime later —
    a tool argument, a model output, a request body — can change it.
    """

    run_id: str
    person_id: str
    agent_id: str
    agent_instance_id: str | None = None
    roles: tuple[str, ...] = ()
    team_id: str | None = None
    parent_run_id: str | None = None
    mode: str = "attended"
    started_at: float = field(default_factory=time.time)
    started_monotonic: float = field(default_factory=time.monotonic)
    run_ceiling_seconds: float | None = None
    origin_caller: str | None = None
    registered: bool = False
    terminal: bool = False
    terminal_reason: str | None = None


class RunRecordSource(Protocol):
    """Durable source consulted for every delegated background call."""

    async def get(self, run_id: str) -> RunRecord | None: ...


@dataclass(frozen=True)
class ImmutableRunRecordSource:
    """One workflow admission record, immutable for the workflow lifetime."""

    record: RunRecord

    async def get(self, run_id: str) -> RunRecord | None:
        return self.record if self.record.run_id == run_id else None


class RunRecordStore:
    """Pod-local run records, keyed by run id.

    Locked rather than plain-dict: admission writes from a request handler while
    a turn's outbound calls read from other tasks on the same loop, and a pod
    serves many turns at once.
    """

    def __init__(
        self,
        *,
        max_age_seconds: float = DEFAULT_RUN_CEILING_SECONDS
        + RUN_RECORD_AGE_MARGIN_SECONDS,
    ) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, RunRecord] = {}
        self._max_age_seconds = max_age_seconds

    def set_max_age(self, seconds: float) -> None:
        """Set how long a record may live before an admission drops it. Called
        once at startup from the deployment's run ceiling."""
        with self._lock:
            self._max_age_seconds = seconds

    def put(self, record: RunRecord) -> RunRecord:
        with self._lock:
            # A record normally goes when its run ends; a run that never started
            # — a binding refused, a client gone before the first event — leaves
            # one behind, and admission is where they are swept.
            self._drop_abandoned()
            self._records[record.run_id] = record
        return record

    def admit(self, record: RunRecord) -> RunRecord:
        with self._lock:
            self._drop_abandoned()
            if record.run_id in self._records:
                raise ValueError("The run is already admitted.")
            self._records[record.run_id] = record
        return record

    def get(self, run_id: str) -> RunRecord | None:
        with self._lock:
            return self._records.get(run_id)

    def discard(self, run_id: str) -> None:
        with self._lock:
            self._records.pop(run_id, None)

    def finalize(self, run_id: str, *, run_ceiling_seconds: float) -> RunRecord:
        with self._lock:
            record = replace(
                self._records[run_id],
                run_ceiling_seconds=run_ceiling_seconds,
                registered=True,
            )
            self._records[run_id] = record
            return record

    def mark_terminal(self, run_id: str, *, reason: str | None = None) -> None:
        with self._lock:
            record = self._records.get(run_id)
            if record is not None:
                self._records[run_id] = replace(
                    record,
                    terminal=True,
                    terminal_reason=record.terminal_reason or reason,
                )

    def _drop_abandoned(self) -> None:
        """Drop every record too old to belong to a live run. Held under the
        lock: one pass over the records a pod actually has in flight."""
        now = time.time()
        abandoned = [
            run_id
            for run_id, record in self._records.items()
            if record.started_at
            + (
                record.run_ceiling_seconds + RUN_RECORD_AGE_MARGIN_SECONDS
                if record.run_ceiling_seconds is not None
                else self._max_age_seconds
            )
            < now
        ]
        for run_id in abandoned:
            self._records.pop(run_id, None)

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)


class OutboundCredentialProvider(ABC):
    """Asked at call time by every outbound client, never copied into one."""

    delegated: bool = False

    @property
    def agent_id(self) -> str | None:
        return None

    @abstractmethod
    async def credentials(
        self, *, override_token: str | None = None
    ) -> OutboundCredentials:
        """Return the credentials for one call."""

    @abstractmethod
    def for_agent(self, agent_id: str) -> "OutboundCredentialProvider":
        """Return a provider naming another agent on the same run."""


class PersonCredentialProvider(OutboundCredentialProvider):
    """Flag off: the person's own bearer, read live at call time.

    The getter is asked per call rather than captured as a string so an in-place
    token refresh is seen by calls already under way, including a child's.
    """

    delegated = False

    def __init__(
        self, token_getter: TokenGetter | None = None, *, agent_id: str | None = None
    ) -> None:
        self._token_getter = token_getter
        self._agent_id = agent_id

    @property
    def agent_id(self) -> str | None:
        return self._agent_id

    async def credentials(
        self, *, override_token: str | None = None
    ) -> OutboundCredentials:
        token = override_token
        if not token and self._token_getter is not None:
            token = await self._token_getter()
        return OutboundCredentials(
            authorization=f"Bearer {token}" if token else None,
            parameters={},
            delegated=False,
        )

    def for_agent(self, agent_id: str) -> "PersonCredentialProvider":
        return PersonCredentialProvider(self._token_getter, agent_id=agent_id)


def static_person_provider(
    token: str | None, *, agent_id: str | None = None
) -> PersonCredentialProvider:
    """A provider over one bearer already in hand — admission, where the
    person's own credential is presented for the only time."""

    async def _token() -> str | None:
        return token

    return PersonCredentialProvider(_token, agent_id=agent_id)


class DelegatedCredentialProvider(OutboundCredentialProvider):
    """Flag on: the runtime's workload bearer plus the grant from the run record.

    Both halves are resolved per call — the bearer from the shared token
    provider, the person and run from the record — so a running child observes
    every change instead of holding a snapshot.
    """

    delegated = True

    def __init__(
        self,
        *,
        runtime: "DelegationRuntime",
        run_id: str,
        agent_id: str,
        record_source: RunRecordSource | None = None,
        admitted_person_id: str | None = None,
        admitted_root_agent_id: str | None = None,
    ) -> None:
        self._runtime = runtime
        self._run_id = run_id
        self._agent_id = agent_id
        self._record_source = record_source
        self._admitted_person_id = admitted_person_id
        self._admitted_root_agent_id = admitted_root_agent_id or agent_id

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def record(self) -> RunRecord:
        record = self._runtime.records.get(self._run_id)
        if record is None:
            raise DelegationUnavailableError()
        return record

    def finalize_registration(self, *, run_ceiling_seconds: float) -> RunRecord:
        return self._runtime.records.finalize(
            self._run_id, run_ceiling_seconds=run_ceiling_seconds
        )

    async def terminal_authorization(self) -> str:
        self._runtime.records.mark_terminal(self._run_id)
        return f"Bearer {await self._runtime.workload_token()}"

    async def credentials(
        self, *, override_token: str | None = None
    ) -> OutboundCredentials:
        # A caller-supplied person token is deliberately ignored: a delegated
        # call never falls back to the person's bearer.
        local_record = self.record
        record = local_record
        if self._record_source is not None:
            durable = await self._record_source.get(self._run_id)
            if (
                durable is None
                or durable.run_id != local_record.run_id
                or durable.person_id != local_record.person_id
                or durable.person_id != self._admitted_person_id
                or durable.agent_id != self._admitted_root_agent_id
                or durable.agent_instance_id != local_record.agent_instance_id
            ):
                raise DelegationUnavailableError()
            record = durable
        if local_record.terminal or record.terminal:
            raise DelegationUnavailableError()
        scope = RunScope.current()
        if scope is not None:
            scope.raise_if_stopped()
            scope.raise_if_exhausted()
        token = await self._runtime.workload_token()
        return OutboundCredentials(
            authorization=f"Bearer {token}",
            parameters={
                GRANT_PARAM_PERSON: record.person_id,
                GRANT_PARAM_RUN: record.run_id,
                GRANT_PARAM_AGENT: self._agent_id,
            },
            delegated=True,
        )

    def for_agent(self, agent_id: str) -> "DelegatedCredentialProvider":
        return DelegatedCredentialProvider(
            runtime=self._runtime,
            run_id=self._run_id,
            agent_id=agent_id,
            record_source=self._record_source,
            admitted_person_id=self._admitted_person_id,
            admitted_root_agent_id=self._admitted_root_agent_id,
        )

    def with_record_source(
        self, source: RunRecordSource, *, root_agent_id: str | None = None
    ) -> "DelegatedCredentialProvider":
        """Attach durable workflow admission without changing local lifecycle state."""
        record = self.record
        return DelegatedCredentialProvider(
            runtime=self._runtime,
            run_id=self._run_id,
            agent_id=self._agent_id,
            record_source=source,
            admitted_person_id=record.person_id,
            admitted_root_agent_id=root_agent_id or record.agent_id,
        )


class DelegationRuntime:
    """Pod-wide delegation state: the configuration, the workload token provider
    and the run records. Built once at startup; `enabled` is the deployment flag."""

    def __init__(
        self,
        *,
        config: DelegationConfig | None = None,
        token_provider: M2MTokenProvider | None = None,
        records: RunRecordStore | None = None,
        workload_client_id: str | None = None,
    ) -> None:
        self._config = config or DelegationConfig()
        self._token_provider = token_provider
        self._records = records if records is not None else RunRecordStore()
        self._workload_client_id = workload_client_id

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    @property
    def workload_client_id(self) -> str | None:
        """The client the workload token is minted for — the `azp` a receiver
        reads to decide whether this caller may speak for a person. It names a
        program, so it belongs in an audit line; the secret behind it never does."""
        return self._workload_client_id

    @property
    def config(self) -> DelegationConfig:
        return self._config

    @property
    def records(self) -> RunRecordStore:
        return self._records

    def ensure_usable(self) -> None:
        """Fail closed: enabled without an allow-list or a workload client is a
        misconfiguration, never a reason to fall back to the person's bearer."""
        if not self._config.enabled:
            return
        if not self._config.allowed_callers and not self._config.caller_policies:
            raise DelegationUnavailableError(
                "Delegation is enabled but no caller allow-list is configured."
            )
        if self._token_provider is None:
            raise DelegationUnavailableError(
                "Delegation is enabled but this deployment has no workload client."
            )

    async def workload_token(self) -> str:
        self.ensure_usable()
        assert self._token_provider is not None  # ensure_usable proved it
        try:
            token = await self._token_provider.get_token()
        except Exception as exc:
            # The upstream message can name the secret's environment variable or
            # echo the authorization server's body; only the type is reportable.
            logger.error(
                "The workload credential could not be obtained (%s).",
                type(exc).__name__,
            )
            raise DelegationUnavailableError(
                "The platform could not obtain its workload credential."
            ) from None
        if not token:
            raise DelegationUnavailableError(
                "The platform could not obtain its workload credential."
            )
        return token

    def provider_for(self, *, run_id: str, agent_id: str) -> OutboundCredentialProvider:
        return DelegatedCredentialProvider(
            runtime=self, run_id=run_id, agent_id=agent_id
        )


def build_delegation_runtime(
    security: SecurityConfiguration | None, *, user_authentication_enabled: bool
) -> DelegationRuntime:
    """Read `security.delegation` once, at startup.

    A delegated call has no meaning without a verified person, so the flag on
    while user authentication is off is a refusal to start, not a warning. With
    the flag off the result is an inert runtime and nothing else changes.
    """
    config = getattr(security, "delegation", None) or DelegationConfig()
    if config.enabled and not user_authentication_enabled:
        raise DelegationConfigurationError(
            "Delegation is enabled while user authentication is disabled. A run "
            "cannot act for a person the platform never authenticated; enable "
            "user authentication or turn delegation off."
        )

    token_provider: M2MTokenProvider | None = None
    workload_client_id: str | None = None
    m2m = getattr(security, "m2m", None)
    if config.enabled and m2m is not None and m2m.enabled and m2m.client_id:
        workload_client_id = m2m.client_id
        token_provider = M2MTokenProvider(
            M2MAuthConfig(
                keycloak_realm_url=str(m2m.realm_url).rstrip("/"),
                client_id=m2m.client_id,
                secret_env=m2m.secret_env_var,
                refresh_failure_cooldown_seconds=(m2m.refresh_failure_cooldown_seconds),
            )
        )
    return DelegationRuntime(
        config=config,
        token_provider=token_provider,
        workload_client_id=workload_client_id,
    )


_DELEGATION_RUNTIME: DelegationRuntime | None = None


def set_delegation_runtime(runtime: DelegationRuntime | None) -> None:
    """Install the pod's delegation state at startup (`None` restores unset)."""
    global _DELEGATION_RUNTIME
    _DELEGATION_RUNTIME = runtime


def get_delegation_runtime() -> DelegationRuntime | None:
    return _DELEGATION_RUNTIME


def delegation_enabled() -> bool:
    runtime = _DELEGATION_RUNTIME
    return runtime is not None and runtime.enabled


def resolve_credential_provider(
    *,
    explicit: OutboundCredentialProvider | None = None,
    holder: Any | None = None,
    person_token_getter: TokenGetter | None = None,
) -> OutboundCredentialProvider:
    """Find the provider one client must use.

    One explicit chain, no ambient state: the client's own provider, else the
    one carried by the agent-like object it was handed, else the person's token
    path it has always used. A path that reaches none of the first two behaves
    exactly as it did before delegation existed — and the enumeration test is
    what proves no run path relies on that.
    """
    if explicit is not None:
        return explicit
    from_holder = getattr(holder, PROVIDER_ATTRIBUTE, None) if holder else None
    if isinstance(from_holder, OutboundCredentialProvider):
        return from_holder
    return PersonCredentialProvider(person_token_getter)


def attach_grant(
    request_kwargs: dict[str, Any], parameters: Mapping[str, str]
) -> dict[str, Any]:
    """Put the grant on one request: body fields for a JSON body, query
    parameters otherwise, so every receiver declares them like any other field."""
    if not parameters:
        return request_kwargs
    body = request_kwargs.get("json")
    if isinstance(body, dict):
        request_kwargs["json"] = {**body, **parameters}
        return request_kwargs
    query = dict(request_kwargs.get("params") or {})
    query.update(parameters)
    request_kwargs["params"] = query
    return request_kwargs


def grant_query_url(url: str, parameters: Mapping[str, str]) -> str:
    """Append the grant to a server endpoint's query string.

    Used where a request has no body the runtime controls — a tool-protocol
    endpoint — so the grant still travels outside the tool's own arguments.
    """
    if not parameters:
        return url
    parts = urlsplit(url)
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key not in parameters
    ]
    query.extend(parameters.items())
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )
