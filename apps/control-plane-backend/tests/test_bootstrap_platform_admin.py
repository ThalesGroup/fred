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

"""RFC Part 8 (§42): root platform-admin bootstrap.

Two independent proofs — a valid Keycloak JWT and a deploy-time secret — and
the grant always targets the caller's own `sub`, never a third party. The
completed-once guard is a durably persisted marker, not a live count of
`platform_admin` tuples: these tests lock in that removing every
`platform_admin` afterwards must not reopen the endpoint.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, cast

import pytest
from control_plane_backend.bootstrap.dependencies import BootstrapServiceDependencies
from control_plane_backend.bootstrap.schemas import (
    BootstrapAlreadyCompletedError,
    BootstrapAuthDisabledError,
    BootstrapPlatformAdminRequest,
    BootstrapPlatformAdminResponse,
    BootstrapRebacDisabledError,
    BootstrapTokenInvalidError,
)
from control_plane_backend.bootstrap.service import bootstrap_platform_admin
from fred_core import (
    ORGANIZATION_ID,
    KeycloakUser,
    RebacReference,
    Relation,
    RelationType,
    Resource,
)
from pydantic import ValidationError


class _FakeRebac:
    def __init__(
        self, *, enabled: bool = True, call_order: list[str] | None = None
    ) -> None:
        self.enabled = enabled
        self.added_relations: list[Relation] = []
        self._call_order = call_order

    async def add_relation(self, relation: Relation):
        self.added_relations.append(relation)
        if self._call_order is not None:
            self._call_order.append("add_relation")
        return None


class _FakeBootstrapStore:
    def __init__(self, *, already_completed: bool = False) -> None:
        self._completed = already_completed
        self.completed_by: str | None = None
        self.advisory_lock_calls = 0
        self.call_order: list[str] = []
        # Real (not no-op) lock: makes concurrent callers genuinely
        # serialize, so a test can prove the lock does something instead of
        # trivially passing because asyncio never interleaved them.
        self._lock = asyncio.Lock()

    async def is_completed(self) -> bool:
        self.call_order.append("is_completed")
        await asyncio.sleep(0)  # yield once so concurrent callers can interleave here
        return self._completed

    async def mark_completed(self, completed_by: str) -> None:
        self.call_order.append("mark_completed")
        # Also yield here, *before* flipping the flag: without this, the
        # check-then-write inside the lock is one uninterrupted synchronous
        # stretch (no real await in between), so even a no-op lock would
        # "accidentally" pass — the two callers' checks never actually race
        # against each other's write. This is the second half of giving the
        # test real teeth.
        await asyncio.sleep(0)
        self._completed = True
        self.completed_by = completed_by

    @asynccontextmanager
    async def advisory_lock(self):
        self.advisory_lock_calls += 1
        async with self._lock:
            yield None


def _user(uid: str = "benjamin-sub", username: str = "benjamin") -> KeycloakUser:
    return KeycloakUser(
        uid=uid, username=username, roles=[], email=f"{username}@example.com"
    )


def _deps(
    *,
    env_var_name: str | None = None,
    env_var_value: str | None = None,
    file_path=None,
    file_value: str | None = None,
    rebac: _FakeRebac | None = None,
    store: _FakeBootstrapStore | None = None,
    auth_enabled: bool = True,
    monkeypatch: pytest.MonkeyPatch,
) -> BootstrapServiceDependencies:
    class _App:
        bootstrap_token_env_var = env_var_name
        bootstrap_token_file = str(file_path) if file_path is not None else None

    class _UserSecurity:
        enabled = auth_enabled

    class _Security:
        user = _UserSecurity()

    class _Configuration:
        app = _App()
        security = _Security()

    if env_var_name and env_var_value is not None:
        monkeypatch.setenv(env_var_name, env_var_value)
    if file_path is not None and file_value is not None:
        file_path.write_text(file_value)

    bootstrap_store = store or _FakeBootstrapStore()
    return BootstrapServiceDependencies(
        configuration=cast(Any, _Configuration()),
        rebac=cast(Any, rebac or _FakeRebac()),
        get_platform_bootstrap_store=cast(Any, lambda: bootstrap_store),
    )


@pytest.mark.asyncio
async def test_bootstrap_grants_platform_admin_to_the_caller(tmp_path, monkeypatch):
    rebac = _FakeRebac()
    deps = _deps(
        file_path=tmp_path / "token",
        file_value="secret-token-9f3a2b1c",
        rebac=rebac,
        monkeypatch=monkeypatch,
    )
    user = _user(uid="benjamin-sub", username="benjamin")

    response = await bootstrap_platform_admin(
        user, BootstrapPlatformAdminRequest(token="secret-token-9f3a2b1c"), deps
    )

    assert response.user_id == "benjamin-sub"
    assert response.username == "benjamin"
    assert len(rebac.added_relations) == 1
    written = rebac.added_relations[0]
    assert written.subject == RebacReference(Resource.USER, "benjamin-sub")
    assert written.relation == RelationType.PLATFORM_ADMIN
    assert written.resource == RebacReference(Resource.ORGANIZATION, ORGANIZATION_ID)


@pytest.mark.asyncio
async def test_bootstrap_prefers_env_var_over_file(tmp_path, monkeypatch):
    deps = _deps(
        env_var_name="FRED_BOOTSTRAP_TOKEN",
        env_var_value="env-token-7c21d4e9",
        file_path=tmp_path / "token",
        file_value="file-token-4b18f0a2",
        monkeypatch=monkeypatch,
    )

    response = await bootstrap_platform_admin(
        _user(), BootstrapPlatformAdminRequest(token="env-token-7c21d4e9"), deps
    )
    assert response.user_id == "benjamin-sub"

    # The file's value must not also work once the env var is configured.
    with pytest.raises(BootstrapTokenInvalidError):
        await bootstrap_platform_admin(
            _user(), BootstrapPlatformAdminRequest(token="file-token-4b18f0a2"), deps
        )


@pytest.mark.asyncio
async def test_bootstrap_env_var_configured_but_absent_does_not_fall_back_to_file(
    tmp_path, monkeypatch
):
    """`bootstrap_token_file`'s docstring says "Ignored if
    bootstrap_token_env_var is set" — this must hold even when the named env
    var itself is absent. Once the operator has named an env var, that is the
    only source consulted, ever: if it's missing, the secret is "not
    configured", full stop, never a fallback to the file — even though the
    file alone holds a perfectly valid secret here.
    """
    deps = _deps(
        env_var_name="FRED_BOOTSTRAP_TOKEN",
        file_path=tmp_path / "token",
        file_value="file-token-4b18f0a2",
        monkeypatch=monkeypatch,
    )

    with pytest.raises(BootstrapTokenInvalidError):
        await bootstrap_platform_admin(
            _user(), BootstrapPlatformAdminRequest(token="file-token-4b18f0a2"), deps
        )


@pytest.mark.asyncio
async def test_bootstrap_rejects_wrong_token(tmp_path, monkeypatch):
    deps = _deps(
        file_path=tmp_path / "token",
        file_value="secret-token-9f3a2b1c",
        monkeypatch=monkeypatch,
    )

    with pytest.raises(BootstrapTokenInvalidError):
        await bootstrap_platform_admin(
            _user(), BootstrapPlatformAdminRequest(token="wrong-token-x19283"), deps
        )


@pytest.mark.asyncio
async def test_bootstrap_disabled_when_nothing_configured(tmp_path, monkeypatch):
    deps = _deps(monkeypatch=monkeypatch)

    with pytest.raises(BootstrapTokenInvalidError):
        await bootstrap_platform_admin(
            _user(), BootstrapPlatformAdminRequest(token="anything-at-all-1234"), deps
        )


@pytest.mark.asyncio
async def test_bootstrap_refuses_when_already_completed(tmp_path, monkeypatch):
    rebac = _FakeRebac()
    store = _FakeBootstrapStore(already_completed=True)
    deps = _deps(
        file_path=tmp_path / "token",
        file_value="secret-token-9f3a2b1c",
        rebac=rebac,
        store=store,
        monkeypatch=monkeypatch,
    )

    with pytest.raises(BootstrapAlreadyCompletedError):
        await bootstrap_platform_admin(
            _user(), BootstrapPlatformAdminRequest(token="secret-token-9f3a2b1c"), deps
        )
    assert rebac.added_relations == []


@pytest.mark.asyncio
async def test_bootstrap_fails_closed_when_auth_disabled(tmp_path, monkeypatch):
    """RFC Part 8 (§42.1) requires two independent proofs — a valid Keycloak
    JWT and the deploy secret — neither alone sufficient. With authentication
    disabled, `get_current_user` returns a hardcoded mock identity with no
    real validation, so the JWT "proof" degrades to a rubber stamp and the
    deploy secret alone would become sufficient. Refused before the ReBAC
    guard and before the store is even touched.
    """
    rebac = _FakeRebac()
    store = _FakeBootstrapStore()
    deps = _deps(
        file_path=tmp_path / "token",
        file_value="secret-token-9f3a2b1c",
        rebac=rebac,
        store=store,
        auth_enabled=False,
        monkeypatch=monkeypatch,
    )

    with pytest.raises(BootstrapAuthDisabledError):
        await bootstrap_platform_admin(
            _user(), BootstrapPlatformAdminRequest(token="secret-token-9f3a2b1c"), deps
        )
    assert rebac.added_relations == []
    assert store.call_order == []


@pytest.mark.asyncio
async def test_bootstrap_fails_closed_when_rebac_disabled(tmp_path, monkeypatch):
    """With ReBAC disabled, `add_relation` would be a silent no-op
    (`NoopRebacEngine`) — refused before the store is even touched, so
    bootstrap cannot burn its one-time completion marker while granting no
    one `platform_admin`."""
    rebac = _FakeRebac(enabled=False)
    store = _FakeBootstrapStore()
    deps = _deps(
        file_path=tmp_path / "token",
        file_value="secret-token-9f3a2b1c",
        rebac=rebac,
        store=store,
        monkeypatch=monkeypatch,
    )

    with pytest.raises(BootstrapRebacDisabledError):
        await bootstrap_platform_admin(
            _user(), BootstrapPlatformAdminRequest(token="secret-token-9f3a2b1c"), deps
        )
    assert rebac.added_relations == []
    assert store.call_order == []


@pytest.mark.asyncio
async def test_bootstrap_durable_marker_blocks_reuse_even_after_admin_removed(
    tmp_path, monkeypatch
):
    """The load-bearing regression test (RFC §42.3).

    A live `lookup_subjects` count of `platform_admin` would read as "zero
    admins" the instant the last one is removed, silently reopening this
    endpoint for anyone who still holds the secret. The durable marker must
    not care: once set, it stays set regardless of what happens to the
    OpenFGA relation afterwards.
    """
    rebac = _FakeRebac()
    store = _FakeBootstrapStore()
    deps = _deps(
        file_path=tmp_path / "token",
        file_value="secret-token-9f3a2b1c",
        rebac=rebac,
        store=store,
        monkeypatch=monkeypatch,
    )

    await bootstrap_platform_admin(
        _user(), BootstrapPlatformAdminRequest(token="secret-token-9f3a2b1c"), deps
    )
    assert len(rebac.added_relations) == 1

    # Simulate total platform_admin loss: the relation the endpoint wrote is
    # gone, but the durable marker (a separate system) is untouched.
    rebac.added_relations.clear()

    with pytest.raises(BootstrapAlreadyCompletedError):
        await bootstrap_platform_admin(
            _user(), BootstrapPlatformAdminRequest(token="secret-token-9f3a2b1c"), deps
        )
    assert rebac.added_relations == []


@pytest.mark.asyncio
async def test_bootstrap_writes_openfga_tuple_before_marker(tmp_path, monkeypatch):
    store = _FakeBootstrapStore()
    rebac = _FakeRebac(call_order=store.call_order)
    deps = _deps(
        file_path=tmp_path / "token",
        file_value="secret-token-9f3a2b1c",
        store=store,
        rebac=rebac,
        monkeypatch=monkeypatch,
    )

    await bootstrap_platform_admin(
        _user(), BootstrapPlatformAdminRequest(token="secret-token-9f3a2b1c"), deps
    )

    assert store.call_order == [
        "is_completed",
        "is_completed",
        "add_relation",
        "mark_completed",
    ]
    assert store.completed_by == "benjamin-sub"


class _FailingRebac:
    """A rebac fake whose `add_relation` always fails, simulating a transient
    OpenFGA outage — the exact scenario this task fixes."""

    enabled = True

    async def add_relation(self, relation: Relation):
        raise RuntimeError("openfga unavailable")


@pytest.mark.asyncio
async def test_bootstrap_marker_not_written_when_openfga_write_fails(
    tmp_path, monkeypatch
):
    """The actual regression this task fixes: with the OpenFGA tuple written
    before the durable marker, a transient `add_relation` failure must leave
    the marker unwritten so a retry can safely start from scratch. Under the
    old order (marker written first), this same failure would have left
    bootstrap permanently marked complete with no admin ever granted."""
    store = _FakeBootstrapStore()
    deps = _deps(
        file_path=tmp_path / "token",
        file_value="secret-token-9f3a2b1c",
        store=store,
        rebac=cast(Any, _FailingRebac()),
        monkeypatch=monkeypatch,
    )

    with pytest.raises(RuntimeError, match="openfga unavailable"):
        await bootstrap_platform_admin(
            _user(), BootstrapPlatformAdminRequest(token="secret-token-9f3a2b1c"), deps
        )

    assert store.completed_by is None
    assert await store.is_completed() is False


@pytest.mark.asyncio
async def test_bootstrap_check_then_write_under_advisory_lock(tmp_path, monkeypatch):
    store = _FakeBootstrapStore()
    deps = _deps(
        file_path=tmp_path / "token",
        file_value="secret-token-9f3a2b1c",
        store=store,
        monkeypatch=monkeypatch,
    )

    await bootstrap_platform_admin(
        _user(), BootstrapPlatformAdminRequest(token="secret-token-9f3a2b1c"), deps
    )

    assert store.advisory_lock_calls == 1


@pytest.mark.asyncio
async def test_bootstrap_never_promotes_a_third_party(tmp_path, monkeypatch):
    """There is no `identifier` field — only the caller's own JWT can ever be
    granted. This test exists to make that structural guarantee explicit: the
    request schema has no way to name anyone else."""
    assert "identifier" not in BootstrapPlatformAdminRequest.model_fields

    rebac = _FakeRebac()
    deps = _deps(
        file_path=tmp_path / "token",
        file_value="secret-token-9f3a2b1c",
        rebac=rebac,
        monkeypatch=monkeypatch,
    )
    caller = _user(uid="attacker-sub", username="attacker")

    await bootstrap_platform_admin(
        caller, BootstrapPlatformAdminRequest(token="secret-token-9f3a2b1c"), deps
    )

    assert rebac.added_relations[0].subject == RebacReference(
        Resource.USER, "attacker-sub"
    )


def test_bootstrap_request_rejects_empty_token():
    """`secrets.compare_digest("", "") is True` in Python, so an empty
    `request.token` must never even reach the comparison — it has to be
    rejected at the schema layer, before `bootstrap_platform_admin` runs."""
    with pytest.raises(ValidationError):
        BootstrapPlatformAdminRequest(token="")


@pytest.mark.asyncio
async def test_bootstrap_treats_empty_configured_secret_as_unconfigured(
    tmp_path, monkeypatch
):
    """A configured secret file that is empty (or whitespace-only) — e.g. a
    broken `make bootstrap-token` run — must not be treated as "configured
    with an empty secret". Otherwise, combined with
    `secrets.compare_digest("", "") is True`, any caller who passes a
    16-char (schema-valid) but wrong token would still fail here, which is
    the point: an empty configured secret must never compare equal to
    anything, so this always raises `BootstrapTokenInvalidError` rather than
    granting `platform_admin`.
    """
    deps = _deps(file_path=tmp_path / "token", file_value="", monkeypatch=monkeypatch)

    with pytest.raises(BootstrapTokenInvalidError):
        await bootstrap_platform_admin(
            _user(),
            BootstrapPlatformAdminRequest(token="0123456789abcdef"),
            deps,
        )


@pytest.mark.asyncio
async def test_bootstrap_treats_too_short_configured_secret_as_unconfigured(
    tmp_path, monkeypatch
):
    """A configured secret shorter than the schema's `min_length` floor
    (e.g. a truncated or misconfigured secret file) is also treated as
    unconfigured, not compared against the request token."""
    deps = _deps(
        file_path=tmp_path / "token", file_value="short", monkeypatch=monkeypatch
    )

    with pytest.raises(BootstrapTokenInvalidError):
        await bootstrap_platform_admin(
            _user(),
            BootstrapPlatformAdminRequest(token="0123456789abcdef"),
            deps,
        )


@pytest.mark.asyncio
async def test_bootstrap_concurrent_calls_grant_exactly_once(tmp_path, monkeypatch):
    """The advisory lock's whole job is preventing exactly this race: two
    legitimate secret-holders calling bootstrap concurrently, both racing the
    check-then-write window, must not both succeed. Exactly one call must be
    granted `platform_admin`; the other must observe the durable marker and
    fail with `BootstrapAlreadyCompletedError` — never a double grant, and
    never a lost update.
    """
    rebac = _FakeRebac()
    store = _FakeBootstrapStore()
    deps = _deps(
        file_path=tmp_path / "token",
        file_value="secret-token-9f3a2b1c",
        rebac=rebac,
        store=store,
        monkeypatch=monkeypatch,
    )

    results = await asyncio.gather(
        bootstrap_platform_admin(
            _user(uid="user-a", username="user-a"),
            BootstrapPlatformAdminRequest(token="secret-token-9f3a2b1c"),
            deps,
        ),
        bootstrap_platform_admin(
            _user(uid="user-b", username="user-b"),
            BootstrapPlatformAdminRequest(token="secret-token-9f3a2b1c"),
            deps,
        ),
        return_exceptions=True,
    )

    successes = [r for r in results if isinstance(r, BootstrapPlatformAdminResponse)]
    failures = [r for r in results if isinstance(r, BootstrapAlreadyCompletedError)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert len(rebac.added_relations) == 1
