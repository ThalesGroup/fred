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

"""Verify bounded exact-reference cleanup without external services."""

from __future__ import annotations

import asyncio
import json
import re
from types import SimpleNamespace
from typing import Any

import pytest
from openfga_sdk.exceptions import ValidationException
from openfga_sdk.models.consistency_preference import ConsistencyPreference
from openfga_sdk.models.read_request_tuple_key import ReadRequestTupleKey

import fred_core
from fred_core.security.models import Resource
from fred_core.security.rebac.openfga_engine import (
    _MAX_REFERENCE_CLEANUP_PASSES,
    _MAX_TUPLES_PER_WRITE,
    OpenFgaRebacEngine,
    RebacCleanupIncomplete,
    _derive_person_object_types,
)
from fred_core.security.rebac.openfga_schema import DEFAULT_SCHEMA
from fred_core.security.rebac.rebac_engine import RebacReference
from fred_core.security.structure import OpenFgaRebacConfig

_APP = RebacReference(Resource.APP, "acme-forecast")
_APP_ID = "app:acme-forecast"
_PERSON = RebacReference(Resource.USER, "person-deleted")
_PERSON_ID = "user:person-deleted"
_PERSON_TYPES = ("organization", "team", "agent", "tag")
_PERSON_READ_TYPES = (*_PERSON_TYPES, "group")
_BAN = (_PERSON_ID, "suspended", "organization:fred")
_EVERYONE = ("user:*", "active", "organization:fred")
_MARKER = ("organization:fred", "standing_ready", "organization:fred")
_PUBLIC_TEAM = ("user:*", "public", "team:alpha")

_Key = tuple[str | None, str | None, str | None]
_Tuple = tuple[str, str, str]


def _validate_read_key(key: _Key) -> None:
    """Reject what the OpenFGA server's Read rejects before touching storage."""
    user, _, obj = key
    if user and not re.fullmatch(r"[^\s]{1,511}:[^\s]{1,511}", user):
        raise ValidationException(status=400, reason="invalid ReadRequestTupleKey.User")
    object_type, separator, object_id = (obj or "").partition(":")
    if not separator or not object_type or (not object_id and not user):
        raise ValidationException(
            status=400,
            reason="the object type field is required and both the object id "
            "and user cannot be empty",
        )


def _read_key_matches(key: _Key, stored: _Tuple) -> bool:
    """OpenFGA storage filter: type-only object, optional relation, exact user."""
    user, relation, obj = key
    stored_user, stored_relation, stored_object = stored
    object_type, _, object_id = (obj or "").partition(":")
    stored_type, _, stored_id = stored_object.partition(":")
    if stored_type != object_type or (object_id and stored_id != object_id):
        return False
    if relation and stored_relation != relation:
        return False
    if user:
        user_type, _, user_id = user.rsplit("#", 1)[0].partition(":")
        if user_id:
            return stored_user == user
        return stored_user.startswith(f"{user_type}:")
    return True


class _FakeOpenFgaClient:
    """Mutable tuple store filtered like OpenFGA Read; deletes take effect.

    ``page_size`` forces the Read pagination path, and ``regrow`` is a tuple a
    concurrent writer adds back after every delete while cleanup runs. Each read
    yields to the event loop like a network call; ``max_in_flight`` counts the
    reads that overlapped.
    """

    def __init__(
        self,
        tuples: list[_Tuple],
        *,
        page_size: int = 1000,
        regrow: _Tuple | None = None,
    ) -> None:
        self.store: list[_Tuple] = list(tuples)
        self._page_size = page_size
        self._regrow = regrow
        self.write_batch_sizes: list[int] = []
        self.read_calls: list[tuple[_Key | None, str | None]] = []
        self.read_consistency_options: list[object] = []
        self._in_flight = 0
        self.max_in_flight = 0

    async def read(self, body: ReadRequestTupleKey, options) -> SimpleNamespace:
        self._in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self._in_flight)
        try:
            await asyncio.sleep(0)
        finally:
            self._in_flight -= 1
        # The SDK sends no tuple_key at all when every field is unset.
        key: _Key | None = (
            None
            if body.user is None and body.relation is None and body.object is None
            else (body.user, body.relation, body.object)
        )
        token = options.get("continuation_token")
        self.read_calls.append((key, token))
        self.read_consistency_options.append(options.get("consistency"))
        if key is not None:
            _validate_read_key(key)
        matches = [t for t in self.store if key is None or _read_key_matches(key, t)]
        index = int(token or 0)
        page = matches[index : index + self._page_size]
        next_index = index + self._page_size
        next_token = str(next_index) if next_index < len(matches) else ""
        keys = [
            SimpleNamespace(key=SimpleNamespace(user=u, relation=r, object=o))
            for u, r, o in page
        ]
        return SimpleNamespace(tuples=keys, continuation_token=next_token)

    async def write(self, body, options) -> Any:
        deletes = list(body.deletes or [])
        self.write_batch_sizes.append(len(deletes))
        removed = {(t.user, t.relation, t.object) for t in deletes}
        if len(removed) != len(deletes):
            raise ValidationException(status=400, reason="duplicate tuple in write")
        self.store = [t for t in self.store if t not in removed]
        if self._regrow:
            self.store.append(self._regrow)
        return SimpleNamespace()

    def read_sequences(self) -> list[_Key | None]:
        """The key of every read that starts a fresh pagination sequence."""
        return [key for key, token in self.read_calls if not token]


def _make_engine(
    client: _FakeOpenFgaClient, *, schema: str = DEFAULT_SCHEMA
) -> OpenFgaRebacEngine:
    config = OpenFgaRebacConfig(
        api_url="http://fake-openfga:8080"  # pyright: ignore[reportArgumentType]
    )
    engine = OpenFgaRebacEngine(config, token="test-token", schema=schema)  # nosec B106 — synthetic offline fixture
    engine._cached_client = client  # pyright: ignore[reportAttributeAccessIssue]
    return engine


def _targeted(object_type: str) -> _Key:
    return (_PERSON_ID, None, f"{object_type}:")


@pytest.mark.asyncio
async def test_the_fake_client_filters_reads_like_openfga() -> None:
    kept = ("user:person-kept", "team_member", "team:alpha")
    admin = (_PERSON_ID, "team_admin", "team:alpha")
    member = (_PERSON_ID, "team_member", "team:beta")
    client = _FakeOpenFgaClient(
        [kept, admin, member, _PUBLIC_TEAM, (_PERSON_ID, "owner", "tag:notes")]
    )

    async def read(**key: str) -> list[_Tuple]:
        res = await client.read(ReadRequestTupleKey(**key), {})
        return [(t.key.user, t.key.relation, t.key.object) for t in res.tuples]

    assert len(await read()) == 5
    assert await read(user=_PERSON_ID, object="team:") == [admin, member]
    assert await read(user=_PERSON_ID, relation="team_member", object="team:") == [
        member
    ]
    assert await read(object="team:alpha") == [kept, admin, _PUBLIC_TEAM]
    with pytest.raises(ValidationException):
        await read(object="team:")
    with pytest.raises(ValidationException):
        await read(user=_PERSON_ID)
    with pytest.raises(ValidationException):
        await read(user="user:", object="team:")
    # The server reads "user:#x" as the user type alone.
    assert await read(user="user:#x", object="team:") == [
        kept,
        admin,
        member,
        _PUBLIC_TEAM,
    ]


@pytest.mark.asyncio
async def test_removes_every_tuple_naming_the_reference_on_either_side() -> None:
    client = _FakeOpenFgaClient(
        [
            ("team:alpha", "enabled", _APP_ID),
            ("organization:main", "default_on", _APP_ID),
            (_APP_ID, "parent", "organization:main"),
        ]
    )

    await _make_engine(client).delete_all_relations_of_reference(_APP)

    assert client.store == []


@pytest.mark.asyncio
async def test_unrelated_references_survive_the_cleanup() -> None:
    survivor = ("team:alpha", "enabled", "app:other-app")
    client = _FakeOpenFgaClient([("team:alpha", "enabled", _APP_ID), survivor])

    await _make_engine(client).delete_all_relations_of_reference(_APP)

    assert client.store == [survivor]


@pytest.mark.asyncio
async def test_a_large_reference_is_deleted_within_the_per_write_limit() -> None:
    """One oversized write is rejected by the server, so batches must be bound."""
    count = _MAX_TUPLES_PER_WRITE * 2 + 5
    client = _FakeOpenFgaClient(
        [(f"team:t{i}", "enabled", _APP_ID) for i in range(count)]
    )

    await _make_engine(client).delete_all_relations_of_reference(_APP)

    assert client.store == []
    assert max(client.write_batch_sizes) <= _MAX_TUPLES_PER_WRITE
    assert sum(client.write_batch_sizes) == count


@pytest.mark.asyncio
async def test_tuples_beyond_the_first_read_page_are_deleted_too() -> None:
    client = _FakeOpenFgaClient(
        [(f"team:t{i}", "enabled", _APP_ID) for i in range(7)], page_size=2
    )

    await _make_engine(client).delete_all_relations_of_reference(_APP)

    assert client.store == []


@pytest.mark.asyncio
async def test_cleanup_ends_only_after_a_pass_that_finds_nothing() -> None:
    """A cursor reaching its end is not the same as an empty re-read."""
    client = _FakeOpenFgaClient([("team:alpha", "enabled", _APP_ID)], page_size=1)

    await _make_engine(client).delete_all_relations_of_reference(_APP)

    # One enumerating pass, then a second that finds nothing and stops.
    assert len(client.read_calls) >= 2
    assert client.store == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reference", "stored"),
    [
        (_APP, ("team:alpha", "enabled", _APP_ID)),
        (_PERSON, (_PERSON_ID, "team_member", "team:alpha")),
    ],
    ids=["full-scan", "person"],
)
async def test_every_enumeration_asks_for_higher_consistency(
    reference: RebacReference, stored: _Tuple
) -> None:
    """Reject stale empty reads as evidence of completion."""
    client = _FakeOpenFgaClient([stored])

    await _make_engine(client).delete_all_relations_of_reference(reference)

    assert client.read_consistency_options
    assert set(client.read_consistency_options) == {
        ConsistencyPreference.HIGHER_CONSISTENCY
    }


@pytest.mark.asyncio
async def test_a_reference_that_keeps_regaining_tuples_fails_loudly() -> None:
    """Cleanup must not return success while tuples it read still exist."""
    client = _FakeOpenFgaClient(
        [("team:alpha", "enabled", _APP_ID)], regrow=("team:late", "enabled", _APP_ID)
    )

    with pytest.raises(RebacCleanupIncomplete):
        await _make_engine(client).delete_all_relations_of_reference(_APP)

    assert client.store != []
    assert len(client.write_batch_sizes) == _MAX_REFERENCE_CLEANUP_PASSES


@pytest.mark.asyncio
async def test_a_reference_with_no_tuples_writes_nothing() -> None:
    client = _FakeOpenFgaClient([("team:alpha", "enabled", "app:other-app")])

    result = await _make_engine(client).delete_all_relations_of_reference(_APP)

    assert result is None
    assert client.write_batch_sizes == []


def test_person_types_derive_from_the_published_schema() -> None:
    assert _derive_person_object_types(DEFAULT_SCHEMA) == _PERSON_TYPES


@pytest.mark.asyncio
async def test_person_cleanup_reads_each_person_type_never_the_store() -> None:
    client = _FakeOpenFgaClient(
        [
            (_PERSON_ID, "team_member", "team:alpha"),
            (_PERSON_ID, "viewer", "tag:notes"),
            ("user:person-kept", "team_member", "team:alpha"),
            ("team:alpha", "owner", "tag:notes"),
        ],
        page_size=1,
    )

    await _make_engine(client).delete_all_relations_of_reference(_PERSON)

    assert all(key is not None for key, _ in client.read_calls)
    # One deleting pass, then one confirming pass: each reads every type once.
    assert sorted(client.read_sequences(), key=str) == sorted(
        [_targeted(object_type) for object_type in _PERSON_READ_TYPES] * 2, key=str
    )


@pytest.mark.asyncio
async def test_person_cleanup_clears_every_type_and_keeps_the_ban() -> None:
    """The ban is what refuses the person afterwards; the cleanup still ends."""
    kept = [
        _BAN,
        _EVERYONE,
        _MARKER,
        _PUBLIC_TEAM,
        ("user:person-kept", "platform_admin", "organization:fred"),
        ("user:person-kept", "team_member", "team:alpha"),
        ("user:person-kept", "owner", "agent:helper"),
        ("user:person-deleted-too", "viewer", "tag:notes"),
        ("team:alpha", "owner", "tag:notes"),
    ]
    person = [
        (_PERSON_ID, "platform_admin", "organization:fred"),
        (_PERSON_ID, "team_member", "team:alpha"),
        (_PERSON_ID, "owner", "agent:helper"),
        (_PERSON_ID, "viewer", "tag:notes"),
    ]
    client = _FakeOpenFgaClient(kept + person, page_size=2)

    result = await _make_engine(client).delete_all_relations_of_reference(_PERSON)

    assert result == ConsistencyPreference.HIGHER_CONSISTENCY
    assert client.store == kept
    assert client.write_batch_sizes == [len(person)]


@pytest.mark.asyncio
async def test_person_reads_page_through_every_continuation_token() -> None:
    person = [(_PERSON_ID, "team_member", f"team:t{i}") for i in range(5)] + [
        (_PERSON_ID, "viewer", f"tag:g{i}") for i in range(3)
    ]
    client = _FakeOpenFgaClient(person, page_size=2)

    await _make_engine(client).delete_all_relations_of_reference(_PERSON)

    assert client.store == []
    assert client.write_batch_sizes == [len(person)]
    assert (_targeted("team"), "4") in client.read_calls


@pytest.mark.asyncio
async def test_a_person_left_with_only_their_ban_needs_no_write() -> None:
    client = _FakeOpenFgaClient([_BAN])

    result = await _make_engine(client).delete_all_relations_of_reference(_PERSON)

    assert result is None
    assert client.write_batch_sizes == []
    assert client.store == [_BAN]


@pytest.mark.asyncio
async def test_person_cleanup_ends_on_a_targeted_pass_that_finds_nothing() -> None:
    client = _FakeOpenFgaClient([(_PERSON_ID, "team_member", "team:alpha")])

    await _make_engine(client).delete_all_relations_of_reference(_PERSON)

    assert client.store == []
    assert len(client.read_sequences()) == 2 * len(_PERSON_READ_TYPES)


@pytest.mark.asyncio
async def test_a_person_who_keeps_regaining_tuples_fails_loudly() -> None:
    client = _FakeOpenFgaClient(
        [(_PERSON_ID, "team_member", "team:alpha")],
        regrow=(_PERSON_ID, "owner", "agent:late"),
    )

    with pytest.raises(RebacCleanupIncomplete):
        await _make_engine(client).delete_all_relations_of_reference(_PERSON)

    assert len(client.write_batch_sizes) == _MAX_REFERENCE_CLEANUP_PASSES


@pytest.mark.asyncio
async def test_person_type_reads_run_together() -> None:
    """The per-type reads overlap, so a slow OpenFGA costs one read per pass."""
    client = _FakeOpenFgaClient([(_PERSON_ID, "team_member", "team:alpha")])

    await _make_engine(client).delete_all_relations_of_reference(_PERSON)

    assert client.store == []
    assert client.max_in_flight == len(_PERSON_READ_TYPES)


@pytest.mark.asyncio
async def test_person_cleanup_removes_a_retired_group_membership() -> None:
    """Earlier models let a person join a `group`; those tuples go too."""
    membership = (_PERSON_ID, "member", "group:g1")
    other = ("user:person-kept", "member", "group:g1")
    client = _FakeOpenFgaClient(
        [membership, other, (_PERSON_ID, "team_member", "team:a"), _BAN]
    )

    await _make_engine(client).delete_all_relations_of_reference(_PERSON)

    assert client.store == [other, _BAN]


@pytest.mark.asyncio
async def test_a_schema_opening_group_to_a_person_reads_it_once() -> None:
    model = json.loads(DEFAULT_SCHEMA)
    model["type_definitions"].append(
        {
            "type": "group",
            "relations": {"member": {"this": {}}},
            "metadata": {
                "relations": {
                    "member": {"directly_related_user_types": [{"type": "user"}]}
                }
            },
        }
    )
    client = _FakeOpenFgaClient([(_PERSON_ID, "member", "group:g1")])

    await _make_engine(
        client, schema=json.dumps(model)
    ).delete_all_relations_of_reference(_PERSON)

    assert client.store == []
    assert client.read_sequences().count(_targeted("group")) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("person_id", ["*", "#x", "#", "team#member", ""])
async def test_a_reference_naming_no_single_person_is_refused_before_any_call(
    person_id: str,
) -> None:
    client = _FakeOpenFgaClient([_EVERYONE, _PUBLIC_TEAM])

    with pytest.raises(ValueError):
        await _make_engine(client).delete_all_relations_of_reference(
            RebacReference(Resource.USER, person_id)
        )

    assert client.read_calls == []
    assert client.write_batch_sizes == []
    assert client.store == [_EVERYONE, _PUBLIC_TEAM]


def _schema_with_extra_types() -> str:
    """Add one type taking a person directly and one taking only `user:*` or a userset."""
    model = json.loads(DEFAULT_SCHEMA)
    model["type_definitions"] += [
        {
            "type": "notebook",
            "relations": {"reader": {"this": {}}},
            "metadata": {
                "relations": {
                    "reader": {"directly_related_user_types": [{"type": "user"}]}
                }
            },
        },
        {
            "type": "board",
            "relations": {"guest": {"this": {}}, "member": {"this": {}}},
            "metadata": {
                "relations": {
                    "guest": {
                        "directly_related_user_types": [
                            {"type": "user", "wildcard": {}}
                        ]
                    },
                    "member": {
                        "directly_related_user_types": [
                            {"type": "team", "relation": "team_member"}
                        ]
                    },
                }
            },
        },
    ]
    return json.dumps(model)


@pytest.mark.asyncio
async def test_person_cleanup_reads_every_type_its_schema_opens_to_a_person() -> None:
    schema = _schema_with_extra_types()
    client = _FakeOpenFgaClient(
        [(_PERSON_ID, "reader", "notebook:n1"), ("user:*", "guest", "board:b1")]
    )

    await _make_engine(client, schema=schema).delete_all_relations_of_reference(_PERSON)

    assert _derive_person_object_types(schema) == (*_PERSON_TYPES, "notebook")
    assert client.store == [("user:*", "guest", "board:b1")]
    assert _targeted("notebook") in client.read_sequences()
    assert _targeted("board") not in client.read_sequences()


@pytest.mark.asyncio
async def test_team_cleanup_still_scans_the_whole_store() -> None:
    survivor = ("user:person-kept", "team_member", "team:beta")
    client = _FakeOpenFgaClient(
        [
            ("user:person-kept", "team_member", "team:alpha"),
            ("team:alpha", "owner", "tag:notes"),
            ("team:alpha", "enabled", _APP_ID),
            survivor,
        ]
    )

    await _make_engine(client).delete_all_relations_of_reference(
        RebacReference(Resource.TEAM, "alpha")
    )

    assert client.store == [survivor]
    assert {key for key, _ in client.read_calls} == {None}


@pytest.mark.asyncio
async def test_organization_cleanup_keeps_every_standing_tuple() -> None:
    platform_admin = ("user:person-kept", "platform_admin", "organization:fred")
    client = _FakeOpenFgaClient([_BAN, _EVERYONE, _MARKER, platform_admin])

    await _make_engine(client).delete_all_relations_of_reference(
        RebacReference(Resource.ORGANIZATION, "fred")
    )

    assert client.store == [_BAN, _EVERYONE, _MARKER]


def test_cleanup_incomplete_is_exported_from_the_package_root() -> None:
    assert fred_core.RebacCleanupIncomplete is RebacCleanupIncomplete
    assert "RebacCleanupIncomplete" in fred_core.__all__
