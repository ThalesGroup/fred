"""The engine a service actually builds from its security configuration."""

from __future__ import annotations

import pytest
from pydantic import AnyHttpUrl, AnyUrl

from fred_core.security.delegation import CallerPolicy, DelegationConfig
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


def _security(
    *, delegation: bool, user: bool = True, m2m: bool = True
) -> SecurityConfiguration:
    policies = (
        [CallerPolicy(client_id="a-runtime", subject="a-subject")] if delegation else []
    )
    return SecurityConfiguration(
        m2m=M2MSecurity(enabled=m2m, realm_url=_REALM, client_id="a-workload"),
        user=UserSecurity(enabled=user, realm_url=_REALM, client_id="a-browser-client"),
        delegation=DelegationConfig(enabled=delegation, caller_policies=policies),
        rebac=OpenFgaRebacConfig(api_url=AnyHttpUrl("http://authz.invalid:9080")),
    )


@pytest.mark.parametrize(("user", "m2m"), [(True, False), (False, True)])
def test_delegation_refuses_an_engine_that_would_authorize_everyone(
    user: bool, m2m: bool
) -> None:
    """Without both OIDC halves the factory falls back to an engine that says yes
    to everyone, which under delegation would serve a person nobody re-checks."""
    with pytest.raises(ValueError, match="enforced relationship engine"):
        rebac_factory(_security(delegation=True, user=user, m2m=m2m))


def test_without_delegation_a_missing_oidc_half_still_yields_the_permissive_engine() -> (
    None
):
    assert isinstance(
        rebac_factory(_security(delegation=False, m2m=False)), NoopRebacEngine
    )


def test_delegation_with_both_halves_builds_the_enforcing_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "OPENFGA_API_TOKEN", "not-a-real-token"
    )  # pragma: allowlist secret
    assert isinstance(rebac_factory(_security(delegation=True)), OpenFgaRebacEngine)
