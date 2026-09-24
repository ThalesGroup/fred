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

"""Per-call credentials derived from the authenticated run and current token provider."""

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any
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
from fred_runtime.runtime_support.run_scope import RunScope

logger = logging.getLogger(__name__)

TokenGetter = Callable[[], Awaitable[str | None]]

# Client shims carry the live provider rather than a captured token.
PROVIDER_ATTRIBUTE = "credential_provider"


class DelegationConfigurationError(RuntimeError):
    """The pod cannot honour its delegation configuration, so it must not start."""


@dataclass(frozen=True)
class OutboundCredentials:
    """Authorization and grant parameters for one outbound request."""

    authorization: str | None = None
    parameters: Mapping[str, str] = field(default_factory=dict)
    delegated: bool = False


@dataclass(frozen=True)
class RunRecord:
    """Verified admission data used to construct outbound grants."""

    run_id: str
    person_id: str
    agent_id: str
    terminal: bool = False


class RunRecordStore:
    """Thread-safe run records retained until their owner releases them."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, RunRecord] = {}

    def admit(self, record: RunRecord) -> RunRecord:
        with self._lock:
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

    def mark_terminal(self, run_id: str) -> None:
        with self._lock:
            record = self._records.get(run_id)
            if record is not None:
                self._records[run_id] = replace(record, terminal=True)

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
    """Read the person token per call so children observe refreshes."""

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
    """Wrap a captured bearer for admission or an own-identity call."""

    async def _token() -> str | None:
        return token

    return PersonCredentialProvider(_token, agent_id=agent_id)


class DelegatedCredentialProvider(OutboundCredentialProvider):
    """Resolve the workload token and live run authority before each call."""

    delegated = True

    def __init__(
        self,
        *,
        runtime: "DelegationRuntime",
        run_id: str,
        agent_id: str,
    ) -> None:
        self._runtime = runtime
        self._run_id = run_id
        self._agent_id = agent_id

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

    async def credentials(
        self, *, override_token: str | None = None
    ) -> OutboundCredentials:
        # Delegated calls cannot fall back to a caller-supplied person token.
        record = self.record
        if record.terminal:
            raise DelegationUnavailableError()
        scope = RunScope.current()
        if scope is not None:
            if scope.closed:
                raise DelegationUnavailableError()
            scope.raise_if_stopped()
        token = await self._runtime.workload_token()
        live_record = self.record
        if live_record is not record or live_record.terminal:
            raise DelegationUnavailableError()
        if scope is not None:
            if scope.closed:
                raise DelegationUnavailableError()
            scope.raise_if_stopped()
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
            runtime=self._runtime, run_id=self._run_id, agent_id=agent_id
        )


class DelegationRuntime:
    """Pod-wide workload credentials and admitted run records."""

    def __init__(
        self,
        *,
        config: DelegationConfig | None = None,
        token_provider: M2MTokenProvider | None = None,
        records: RunRecordStore | None = None,
    ) -> None:
        self._enabled = (config or DelegationConfig()).act_for_people
        self._token_provider = token_provider
        self._records = records if records is not None else RunRecordStore()

    @property
    def enabled(self) -> bool:
        """True when this pod's outgoing calls act for people."""
        return self._enabled

    @property
    def records(self) -> RunRecordStore:
        return self._records

    def ensure_usable(self) -> None:
        """Refuse enabled delegation without a workload token provider."""
        if not self._enabled:
            return
        if self._token_provider is None:
            raise DelegationUnavailableError(
                "act_for_people is on but this deployment has no workload client."
            )

    async def workload_token(self) -> str:
        self.ensure_usable()
        assert self._token_provider is not None  # ensure_usable proved it
        try:
            token = await self._token_provider.get_token()
        except Exception as exc:
            # Upstream errors can expose credentials; report only the type.
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
    """Build outgoing credentials and reject incompatible authentication settings."""
    config = getattr(security, "delegation", None) or DelegationConfig()
    if config.act_for_people and not user_authentication_enabled:
        raise DelegationConfigurationError(
            "act_for_people is on while user authentication is disabled. A run "
            "cannot act for a person the platform never authenticated; enable "
            "user authentication or turn act_for_people off."
        )
    if config.accept_delegated_calls and not config.act_for_people:
        # A person named by a workload has no token of their own to forward.
        raise DelegationConfigurationError(
            "accept_delegated_calls is on without act_for_people. An agent run "
            "for a person a workload names must call onward for that person; "
            "turn act_for_people on as well."
        )

    token_provider: M2MTokenProvider | None = None
    m2m = getattr(security, "m2m", None)
    if config.act_for_people and m2m is not None and m2m.enabled and m2m.client_id:
        token_provider = M2MTokenProvider(
            M2MAuthConfig(
                keycloak_realm_url=str(m2m.realm_url).rstrip("/"),
                client_id=m2m.client_id,
                secret_env=m2m.secret_env_var,
            )
        )
    return DelegationRuntime(config=config, token_provider=token_provider)


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
    """Prefer the explicit provider, then the holder, then the person token getter."""
    if explicit is not None:
        return explicit
    from_holder = getattr(holder, PROVIDER_ATTRIBUTE, None) if holder else None
    if isinstance(from_holder, OutboundCredentialProvider):
        return from_holder
    return PersonCredentialProvider(person_token_getter)


def attach_grant(
    request_kwargs: dict[str, Any], parameters: Mapping[str, str]
) -> dict[str, Any]:
    """Merge grant fields into a JSON object body, or query parameters otherwise."""
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
    """Place verified grant fields in the endpoint query, outside model arguments."""
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
