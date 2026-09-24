"""The engine a service actually builds from its security configuration."""

from __future__ import annotations

import pytest
from pydantic import AnyHttpUrl, AnyUrl

from fred_core.security.delegation import DelegationConfig
from fred_core.security.rebac.noop_engine import NoopRebacEngine
from fred_core.security.rebac.openfga_engine import OpenFgaRebacEngine
from fred_core.security.rebac.rebac_factory import rebac_factory
from fred_core.security.structure import (
    M2MSecurity,
    OpenFgaRebacConfig,
    SecurityConfiguration,
    UserSecurity,
)

_REALM = AnyUrl("http://identity.invalid/realms/app")


_IN_USE = pytest.mark.parametrize(
    "delegation",
    [
        DelegationConfig(act_for_people=True),
        DelegationConfig(accept_delegated_calls=True),
    ],
    ids=["act_for_people", "accept_delegated_calls"],
)


def _security(
    *, delegation: DelegationConfig, user: bool = True, m2m: bool = True
) -> SecurityConfiguration:
    return SecurityConfiguration(
        m2m=M2MSecurity(enabled=m2m, realm_url=_REALM, client_id="a-workload"),
        user=UserSecurity(enabled=user, realm_url=_REALM, client_id="a-browser-client"),
        delegation=delegation,
        rebac=OpenFgaRebacConfig(api_url=AnyHttpUrl("http://authz.invalid:9080")),
    )


@_IN_USE
@pytest.mark.parametrize(("user", "m2m"), [(True, False), (False, True)])
def test_delegation_refuses_an_engine_that_would_authorize_everyone(
    delegation: DelegationConfig, user: bool, m2m: bool
) -> None:
    """Without both OIDC halves the factory falls back to an engine that says yes
    to everyone, which under delegation would serve a person nobody re-checks."""
    with pytest.raises(ValueError, match="enforced relationship engine"):
        rebac_factory(_security(delegation=delegation, user=user, m2m=m2m))


def test_without_delegation_a_missing_oidc_half_still_yields_the_permissive_engine() -> (
    None
):
    assert isinstance(
        rebac_factory(_security(delegation=DelegationConfig(), m2m=False)),
        NoopRebacEngine,
    )


@_IN_USE
def test_delegation_with_both_halves_builds_the_enforcing_engine(
    monkeypatch: pytest.MonkeyPatch, delegation: DelegationConfig
) -> None:
    monkeypatch.setenv(
        "OPENFGA_API_TOKEN", "not-a-real-token"
    )  # pragma: allowlist secret
    engine = rebac_factory(_security(delegation=delegation))
    assert isinstance(engine, OpenFgaRebacEngine)
    assert engine.enforces_standing is True


def test_without_delegation_the_engine_does_not_enforce_standing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "OPENFGA_API_TOKEN", "not-a-real-token"
    )  # pragma: allowlist secret
    engine = rebac_factory(_security(delegation=DelegationConfig()))
    assert isinstance(engine, OpenFgaRebacEngine)
    assert engine.enforces_standing is False
