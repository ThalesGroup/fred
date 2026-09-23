# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");

from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from typing import Callable

import pytest
from openfga_sdk.api_client import ApiClient
from openfga_sdk.client.models.write_conflict_opts import (
    ClientWriteRequestOnDuplicateWrites,
)
from openfga_sdk.configuration import Configuration

from fred_core.security.models import Resource, StandingAuthorizationError
from fred_core.security.rebac.openfga_engine import OpenFgaRebacEngine
from fred_core.security.rebac.openfga_schema import DEFAULT_SCHEMA
from fred_core.security.rebac.rebac_engine import (
    RebacEngine,
    RebacReference,
    Relation,
    RelationType,
    TeamPermission,
)
from fred_core.security.structure import OpenFgaRebacConfig

_PERSON = RebacReference(Resource.USER, "person-synthetic")
_TEAM = RebacReference(Resource.TEAM, "team-synthetic")
_ORGANIZATION = RebacReference(Resource.ORGANIZATION, "fred")
_EVERYONE = RebacReference(Resource.USER, "*")


def _organization_of(model: dict) -> dict:
    return next(t for t in model["type_definitions"] if t["type"] == "organization")


def _allow_list_model(model: dict) -> None:
    """The old model's shape: a per-person `active: [user]` and no `suspended`."""
    organization = _organization_of(model)
    organization["relations"]["active"] = {"this": {}}
    organization["metadata"]["relations"]["active"] = {
        "directly_related_user_types": [{"type": "user"}]
    }
    del organization["relations"]["suspended"]
    del organization["metadata"]["relations"]["suspended"]


class _StandingClient:
    def __init__(self, *, standing: bool = True, target: bool = True) -> None:
        self.standing = standing
        self.target = target
        self.batch_calls = []
        self.list_calls = []
        self.read_calls = []
        self.write_calls = []
        # The model the repository ships, parsed below by the SDK itself.
        self.model: dict = json.loads(DEFAULT_SCHEMA)

    def _standing_of(self, user: str) -> bool:
        return self.standing

    def _answer(self, check) -> bool:
        if (check.relation, check.object) == ("active", "organization:fred"):
            return self._standing_of(check.user)
        return self.target

    async def batch_check(self, body, options):
        self.batch_calls.append((body, options))
        return SimpleNamespace(
            result=[
                SimpleNamespace(
                    allowed=self._answer(item),
                    correlation_id=item.correlation_id,
                    error=None,
                )
                for item in body.checks
            ]
        )

    async def list_objects(self, body, options):
        self.list_calls.append((body, options))
        return SimpleNamespace(objects=[])

    async def check(self, body, options):
        self.batch_calls.append((body, options))
        return SimpleNamespace(allowed=self._answer(body))

    async def read(self, body, options):
        self.read_calls.append((body, options))
        return SimpleNamespace(tuples=[], continuation_token="")  # nosec B106 - protocol metadata or synthetic fixture

    async def write(self, body, options):
        self.write_calls.append((body, options))
        return SimpleNamespace()

    async def read_authorization_model(self, options):
        self.selected_model = options["authorization_model_id"]
        payload = {"authorization_model": {"id": self.selected_model, **self.model}}
        async with ApiClient(Configuration(api_url="http://fake-openfga:8080")) as api:
            return api.deserialize(
                SimpleNamespace(data=json.dumps(payload)),
                "ReadAuthorizationModelResponse",
            )

    async def read_latest_authorization_model(self):
        return await self.read_authorization_model(
            {"authorization_model_id": "synthetic-latest"}
        )


def _engine(client: _StandingClient, *, gate: bool = True) -> OpenFgaRebacEngine:
    engine = OpenFgaRebacEngine(
        OpenFgaRebacConfig(
            api_url="http://fake-openfga:8080",  # pyright: ignore[reportArgumentType]
        ),
        token="synthetic-test-token",  # nosec B106
        enforces_standing=gate,
    )
    engine._cached_client = client  # pyright: ignore[reportAttributeAccessIssue]
    return engine


@pytest.mark.asyncio
async def test_person_check_combines_standing_and_permission_in_one_batch() -> None:
    client = _StandingClient()

    assert await _engine(client).has_permission(_PERSON, TeamPermission.CAN_READ, _TEAM)

    assert len(client.batch_calls) == 1
    body, options = client.batch_calls[0]
    assert [(item.relation, item.object) for item in body.checks] == [
        ("active", "organization:fred"),
        ("can_read", "team:team-synthetic"),
    ]
    assert options["consistency"] == "HIGHER_CONSISTENCY"


@pytest.mark.asyncio
async def test_missing_standing_is_a_bounded_permission_error() -> None:
    client = _StandingClient(standing=False)

    with pytest.raises(StandingAuthorizationError) as caught:
        await _engine(client).has_permissions(
            _PERSON,
            [TeamPermission.CAN_READ, TeamPermission.CAN_UPDATE_INFO],
            _TEAM,
        )

    assert isinstance(caught.value, PermissionError)
    assert str(caught.value) == "Current account standing could not be established."
    assert len(client.batch_calls) == 1
    assert len(client.batch_calls[0][0].checks) == 3


@pytest.mark.asyncio
async def test_standing_transport_failure_is_same_bounded_denial() -> None:
    class _Unavailable(_StandingClient):
        async def batch_check(self, body, options):
            raise RuntimeError("synthetic upstream canary")

    with pytest.raises(StandingAuthorizationError) as caught:
        await _engine(_Unavailable()).has_permission(
            _PERSON, TeamPermission.CAN_READ, _TEAM
        )

    assert caught.value.unavailable is True
    assert "canary" not in str(caught.value)


@pytest.mark.asyncio
async def test_list_checks_standing_before_list_objects() -> None:
    client = _StandingClient(standing=False)

    with pytest.raises(StandingAuthorizationError):
        await _engine(client).lookup_resources(
            _PERSON, TeamPermission.CAN_READ, Resource.TEAM
        )

    assert len(client.batch_calls) == 1
    assert client.list_calls == []


@pytest.mark.asyncio
async def test_active_person_may_receive_an_ordinary_empty_list() -> None:
    client = _StandingClient()

    result = await _engine(client).lookup_resources(
        _PERSON, TeamPermission.CAN_READ, Resource.TEAM
    )

    assert result == []
    assert len(client.list_calls) == 1


@pytest.mark.asyncio
async def test_explicit_standing_check_needs_no_object_permission() -> None:
    client = _StandingClient(standing=False)

    with pytest.raises(StandingAuthorizationError):
        await _engine(client).require_user_standing("person-synthetic")

    body, options = client.batch_calls[0]
    assert body.relation == "active"
    assert body.object == "organization:fred"
    assert options["consistency"] == "HIGHER_CONSISTENCY"


@pytest.mark.asyncio
async def test_team_subject_and_gate_off_do_not_add_standing_check() -> None:
    gate_off = _StandingClient()
    assert await _engine(gate_off, gate=False).has_permission(
        _PERSON, TeamPermission.CAN_READ, _TEAM
    )
    assert len(gate_off.batch_calls) == 1
    assert not hasattr(gate_off.batch_calls[0][0], "checks")

    team_client = _StandingClient()
    team_subject = RebacReference(Resource.TEAM, "team-subject")
    assert await _engine(team_client).has_permission(
        team_subject, TeamPermission.CAN_READ, _TEAM
    )
    assert not hasattr(team_client.batch_calls[0][0], "checks")


_STANDING_TUPLES = [
    Relation(subject=_EVERYONE, relation=RelationType.ACTIVE, resource=_ORGANIZATION),
    Relation(subject=_PERSON, relation=RelationType.ACTIVE, resource=_ORGANIZATION),
    Relation(
        subject=_ORGANIZATION,
        relation=RelationType.STANDING_READY,
        resource=_ORGANIZATION,
    ),
    Relation(subject=_PERSON, relation=RelationType.SUSPENDED, resource=_ORGANIZATION),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "relation", _STANDING_TUPLES, ids=lambda r: f"{r.subject.id}-{r.relation.value}"
)
async def test_generic_relation_writes_and_deletes_cannot_change_standing(
    relation: Relation,
) -> None:
    client = _StandingClient()
    engine = _engine(client)
    ordinary = Relation(
        subject=_PERSON, relation=RelationType.TEAM_MEMBER, resource=_TEAM
    )

    with pytest.raises(ValueError, match="account lifecycle"):
        await engine.add_relation(relation)
    with pytest.raises(ValueError, match="account lifecycle"):
        await engine.add_relations([ordinary, relation])
    with pytest.raises(ValueError, match="account lifecycle"):
        await engine.delete_relation(relation)
    with pytest.raises(ValueError, match="account lifecycle"):
        await engine.delete_relations([ordinary, relation])

    assert client.write_calls == []


@pytest.mark.asyncio
async def test_a_batch_delete_is_refused_before_any_relation_is_removed() -> None:
    """The batch is checked as a whole, so an engine that deletes one relation at
    a time never removes the ordinary ones of a batch it refuses."""
    engine = _RecordingDeletes()
    ordinary = Relation(
        subject=_PERSON, relation=RelationType.TEAM_MEMBER, resource=_TEAM
    )
    ban = Relation(
        subject=_PERSON, relation=RelationType.SUSPENDED, resource=_ORGANIZATION
    )

    with pytest.raises(ValueError, match="account lifecycle"):
        await engine.delete_relations(iter([ordinary, ban]))

    assert engine.deleted == []
    await engine.delete_relations(iter([ordinary]))
    assert engine.deleted == [ordinary]


@pytest.mark.asyncio
async def test_default_standing_writes_exactly_the_everyone_entry() -> None:
    client = _StandingClient()

    await _engine(client).grant_default_standing()

    assert len(client.write_calls) == 1
    body, _options = client.write_calls[0]
    assert not body.deletes
    assert [(t.user, t.relation, t.object) for t in body.writes] == [
        ("user:*", "active", "organization:fred")
    ]


@pytest.mark.asyncio
async def test_removing_standing_writes_the_ban_without_logging_the_person(
    caplog,
) -> None:
    client = _StandingClient()

    with caplog.at_level(
        logging.DEBUG, logger="fred_core.security.rebac.openfga_engine"
    ):
        await _engine(client).remove_user_standing(_PERSON.id)

    assert len(client.write_calls) == 1
    body, _options = client.write_calls[0]
    assert not body.deletes
    assert [(t.user, t.relation, t.object) for t in body.writes] == [
        ("user:person-synthetic", "suspended", "organization:fred")
    ]
    rendered = repr([record.__dict__ for record in caplog.records])
    assert caplog.records
    assert _PERSON.id not in rendered


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "write",
    [
        lambda engine: engine.grant_default_standing(),
        lambda engine: engine.mark_standing_seed_ready(),
        lambda engine: engine.remove_user_standing(_PERSON.id),
    ],
    ids=["everyone", "marker", "ban"],
)
async def test_lifecycle_writes_accept_a_tuple_already_stored(write) -> None:
    """Every start rewrites the everyone entry and the marker, and a retried delete
    rewrites the ban: the store must treat an existing tuple as written."""
    client = _StandingClient()

    await write(_engine(client))

    _body, options = client.write_calls[0]
    assert (
        options["conflict"].on_duplicate_writes
        == ClientWriteRequestOnDuplicateWrites.IGNORE
    )


@pytest.mark.asyncio
async def test_an_engine_without_the_standing_model_refuses_to_grant_it() -> None:
    engine = _NonBatchingEngine(RuntimeError("unused"))

    with pytest.raises(RuntimeError, match="Standing authorization model"):
        await engine.grant_default_standing()


@pytest.mark.asyncio
async def test_model_validation_is_independent_of_seed_marker() -> None:
    client = _StandingClient()
    engine = _engine(client)

    await engine.validate_standing_model()

    assert engine._authorization_model_id == "synthetic-latest"
    assert await engine.is_standing_seed_ready() is False
    assert client.read_calls[-1][1]["consistency"] == "HIGHER_CONSISTENCY"


def _server_defaults(model: dict) -> None:
    """Empty-string defaults a model read back from the store may carry."""
    organization = _organization_of(model)
    for metadata in organization["metadata"]["relations"].values():
        for reference in metadata.get("directly_related_user_types", []):
            reference.setdefault("condition", "")
    subtract = organization["relations"]["active"]["difference"]["subtract"]
    subtract["computedUserset"].setdefault("object", "")


@pytest.mark.asyncio
async def test_model_validation_accepts_empty_string_defaults() -> None:
    client = _StandingClient()
    _server_defaults(client.model)

    await _engine(client).validate_standing_model()


def _per_person_active(model: dict) -> None:
    organization = _organization_of(model)
    organization["relations"]["active"] = {"this": {}}
    organization["metadata"]["relations"]["active"] = {
        "directly_related_user_types": [{"type": "user"}]
    }


def _missing_suspended(model: dict) -> None:
    organization = _organization_of(model)
    del organization["relations"]["suspended"]
    del organization["metadata"]["relations"]["suspended"]


def _wildcard_suspended(model: dict) -> None:
    _organization_of(model)["metadata"]["relations"]["suspended"] = {
        "directly_related_user_types": [{"type": "user", "wildcard": {}}]
    }


def _active_without_ban(model: dict) -> None:
    _organization_of(model)["relations"]["active"] = {"this": {}}


def _active_without_wildcard(model: dict) -> None:
    """`active: [user] but not suspended`: the ban without the everyone entry."""
    _organization_of(model)["metadata"]["relations"]["active"] = {
        "directly_related_user_types": [{"type": "user"}]
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reshape",
    [
        _per_person_active,
        _missing_suspended,
        _wildcard_suspended,
        _active_without_ban,
        _active_without_wildcard,
    ],
)
async def test_model_validation_rejects_a_standing_shape_other_than_the_block_list(
    reshape: Callable[[dict], None],
) -> None:
    client = _StandingClient()
    reshape(client.model)

    with pytest.raises(
        RuntimeError, match="Standing authorization model is not available"
    ):
        await _engine(client).validate_standing_model()


@pytest.mark.asyncio
async def test_old_model_pin_fails_bounded_compatibility_validation() -> None:
    client = _StandingClient()
    _allow_list_model(client.model)

    engine = _engine(client)
    engine._authorization_model_id = "synthetic-old-pin"
    with pytest.raises(
        RuntimeError, match="Standing authorization model is not available"
    ):
        await engine.validate_standing_model()
    assert client.selected_model == "synthetic-old-pin"


@pytest.mark.asyncio
async def test_standing_checks_do_not_log_subject_or_resource_identifiers(
    caplog,
) -> None:
    client = _StandingClient()
    with caplog.at_level(
        logging.DEBUG, logger="fred_core.security.rebac.openfga_engine"
    ):
        await _engine(client).has_permission(_PERSON, TeamPermission.CAN_READ, _TEAM)
    rendered = repr([record.__dict__ for record in caplog.records])
    assert _PERSON.id not in rendered
    assert _TEAM.id not in rendered
    assert "authorization_batch_check" in rendered


@pytest.mark.asyncio
async def test_a_standing_error_is_an_unconsultable_dependency() -> None:
    """The store answered, but not about standing. Treating that as a decision
    would deny a person for a fault that is not theirs."""

    class _ErroringStanding(_StandingClient):
        async def batch_check(self, body, options):
            return SimpleNamespace(
                result=[
                    SimpleNamespace(
                        allowed=False,
                        correlation_id=item.correlation_id,
                        error=(
                            "synthetic upstream canary"
                            if item.correlation_id == "0"
                            else None
                        ),
                    )
                    for item in body.checks
                ]
            )

    with pytest.raises(StandingAuthorizationError) as caught:
        await _engine(_ErroringStanding()).has_permission(
            _PERSON, TeamPermission.CAN_READ, _TEAM
        )

    assert caught.value.unavailable is True
    assert "canary" not in str(caught.value)


@pytest.mark.asyncio
async def test_an_absent_standing_result_is_an_unconsultable_dependency() -> None:
    """A response that simply omits the standing answer must not be read as one."""

    class _DropsStanding(_StandingClient):
        async def batch_check(self, body, options):
            return SimpleNamespace(
                result=[
                    SimpleNamespace(
                        allowed=True, correlation_id=item.correlation_id, error=None
                    )
                    for item in body.checks
                    if item.correlation_id != "0"
                ]
            )

    with pytest.raises(StandingAuthorizationError) as caught:
        await _engine(_DropsStanding()).has_permission(
            _PERSON, TeamPermission.CAN_READ, _TEAM
        )

    assert caught.value.unavailable is True


class _NonBatchingEngine(RebacEngine):
    """Keeps the base class's standing template, which the store-backed engine
    replaces with a batched one, so the template's own failure path runs."""

    def __init__(self, failure: Exception) -> None:
        self._failure = failure

    @property
    def enforces_standing(self) -> bool:
        return True

    async def _has_permission_raw(self, *args, **kwargs) -> bool:
        raise self._failure

    async def _persist_relation(self, *args, **kwargs):
        raise NotImplementedError

    async def delete_relation(self, *args, **kwargs):
        raise NotImplementedError

    async def delete_all_relations_of_reference(self, *args, **kwargs):
        raise NotImplementedError

    async def delete_all_relations_of_type(self, *args, **kwargs):
        raise NotImplementedError

    async def list_relations(self, *args, **kwargs):
        raise NotImplementedError

    async def _lookup_resources_raw(self, *args, **kwargs):
        raise NotImplementedError

    async def lookup_subjects(self, *args, **kwargs):
        raise NotImplementedError


class _RecordingDeletes(_NonBatchingEngine):
    """Deletes one relation at a time and records each, like a plain store."""

    def __init__(self) -> None:
        super().__init__(RuntimeError("unused"))
        self.deleted: list[Relation] = []

    async def delete_relation(self, relation, *args, **kwargs):
        self.deleted.append(relation)
        return None


@pytest.mark.asyncio
async def test_a_standing_requirement_survives_an_unconsultable_dependency() -> None:
    engine = _NonBatchingEngine(RuntimeError("synthetic upstream canary"))

    with pytest.raises(StandingAuthorizationError) as caught:
        await engine.require_user_standing("person-synthetic")

    assert caught.value.unavailable is True
    assert "canary" not in str(caught.value)


@pytest.mark.asyncio
async def test_the_standing_template_reports_an_unconsultable_dependency() -> None:
    engine = _NonBatchingEngine(RuntimeError("synthetic upstream canary"))

    with pytest.raises(StandingAuthorizationError) as caught:
        await engine.has_permissions(
            _PERSON, [TeamPermission.CAN_READ, TeamPermission.CAN_UPDATE_INFO], _TEAM
        )

    assert caught.value.unavailable is True
    assert "canary" not in str(caught.value)


@pytest.mark.asyncio
async def test_a_store_unreachable_before_its_client_exists_is_unconsultable() -> None:
    """The store can already be gone when a call goes to establish its client.
    Left unclassified, that surfaces as an unhandled failure rather than as the
    dependency being unavailable."""
    engine = _engine(_StandingClient())

    async def unreachable():
        raise ConnectionError("synthetic upstream canary")

    engine.get_client = unreachable  # pyright: ignore[reportAttributeAccessIssue]

    with pytest.raises(StandingAuthorizationError) as caught:
        await engine.has_permission(_PERSON, TeamPermission.CAN_READ, _TEAM)

    assert caught.value.unavailable is True
    assert "canary" not in str(caught.value)


class _SeedingStore(_StandingClient):
    """A store whose reads return the tuples written to it that match the read,
    and whose standing check evaluates the shipped model over those tuples.

    The base fake always reads back nothing, which can only ever express the
    half of the rollout before startup has written anything.
    """

    def __init__(self, *, target: bool = True) -> None:
        super().__init__(target=target)
        self.tuples: set[tuple[str, str, str]] = set()

    def _standing_of(self, user: str) -> bool:
        # `active: [user:*] but not suspended`
        return ("user:*", "active", "organization:fred") in self.tuples and (
            user,
            "suspended",
            "organization:fred",
        ) not in self.tuples

    async def write(self, body, options):
        for tuple_ in body.writes or []:
            self.tuples.add((tuple_.user, tuple_.relation, tuple_.object))
        for tuple_ in body.deletes or []:
            self.tuples.discard((tuple_.user, tuple_.relation, tuple_.object))
        return await super().write(body, options)

    async def read(self, body, options):
        self.read_calls.append((body, options))
        tuples = [
            SimpleNamespace(
                key=SimpleNamespace(user=user, relation=relation, object=obj)
            )
            for user, relation, obj in sorted(self.tuples)
            if (not body.user or body.user == user)
            and (not body.relation or body.relation == relation)
            and (not body.object or body.object == obj)
        ]
        return SimpleNamespace(tuples=tuples, continuation_token="")  # nosec B106 - protocol metadata


@pytest.mark.asyncio
async def test_a_pinned_deployment_recovers_once_the_new_model_is_published() -> None:
    """The refusal is only half the contract. A deployment pinned to the old
    model ends with the gate active and every person still in good standing."""
    client = _SeedingStore()
    _allow_list_model(client.model)
    engine = _engine(client)
    engine._authorization_model_id = "synthetic-old-pin"

    with pytest.raises(
        RuntimeError, match="Standing authorization model is not available"
    ):
        await engine.validate_standing_model()

    # The new model is published and this participant selects it.
    client.model = json.loads(DEFAULT_SCHEMA)
    engine._authorization_model_id = None
    await engine.validate_standing_model()
    assert engine._authorization_model_id == "synthetic-latest"

    # Without the everyone entry nobody is in good standing.
    with pytest.raises(StandingAuthorizationError):
        await engine.has_permission(_PERSON, TeamPermission.CAN_READ, _TEAM)

    # Startup writes the everyone entry, then the marker.
    assert await engine.is_standing_seed_ready() is False
    await engine.grant_default_standing()
    assert await engine.is_standing_seed_ready() is False
    await engine.mark_standing_seed_ready()
    assert await engine.is_standing_seed_ready() is True
    assert ("user:*", "active", "organization:fred") in client.tuples

    # A person Fred has not removed keeps the access they had before.
    assert await engine.has_permission(_PERSON, TeamPermission.CAN_READ, _TEAM) is True


@pytest.mark.asyncio
async def test_a_person_fred_removed_is_refused_beside_the_everyone_entry() -> None:
    client = _SeedingStore()
    engine = _engine(client)
    bystander = RebacReference(Resource.USER, "bystander-synthetic")
    await engine.grant_default_standing()

    await engine.remove_user_standing(_PERSON.id)

    with pytest.raises(StandingAuthorizationError) as caught:
        await engine.has_permission(_PERSON, TeamPermission.CAN_READ, _TEAM)
    assert caught.value.unavailable is False
    with pytest.raises(StandingAuthorizationError):
        await engine.require_user_standing(_PERSON.id)
    assert await engine.has_permission(bystander, TeamPermission.CAN_READ, _TEAM)
