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
from openfga_sdk.exceptions import ValidationException

from fred_core.security.models import AccountStatusError, Resource
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
_BYSTANDER = RebacReference(Resource.USER, "bystander-synthetic")
_TEAM = RebacReference(Resource.TEAM, "team-synthetic")
_ORGANIZATION = RebacReference(Resource.ORGANIZATION, "fred")
_PERSON_SUSPENDED = ("user:person-synthetic", "suspended", "organization:fred")


def _organization_of(model: dict) -> dict:
    return next(t for t in model["type_definitions"] if t["type"] == "organization")


def _model_without_suspension(model: dict) -> None:
    """A model that stores account status as a per-person `active: [user]` and defines
    no `suspended`."""
    organization = _organization_of(model)
    organization["relations"]["active"] = {"this": {}}
    organization["metadata"]["relations"]["active"] = {
        "directly_related_user_types": [{"type": "user"}]
    }
    del organization["relations"]["suspended"]
    del organization["metadata"]["relations"]["suspended"]


class _AccountStatusStore:
    """A tuple store that evaluates `suspended: [user]` as OpenFGA does.

    A check on `suspended` is true only when the direct tuple is stored. A write
    of `suspended` naming `user:*` or a userset is rejected with a 400, as is a
    duplicate write unless the request ignores duplicates, and as is a check on
    a relation the current model does not define. Every other check answers
    `target`.
    """

    def __init__(self, *, target: bool = True) -> None:
        self.target = target
        self.tuples: set[tuple[str, str, str]] = set()
        self.batch_calls = []
        self.check_calls = []
        self.list_calls = []
        self.read_calls = []
        self.write_calls = []
        # The model the repository ships, parsed below by the SDK itself.
        self.model: dict = json.loads(DEFAULT_SCHEMA)

    def _answer(self, user: str, relation: str, obj: str) -> bool:
        if obj.startswith("organization:"):
            if relation not in _organization_of(self.model)["relations"]:
                raise ValidationException(status=400, reason="relation not found")
            if relation == RelationType.SUSPENDED.value:
                return (user, relation, obj) in self.tuples
        return self.target

    async def batch_check(self, body, options):
        self.batch_calls.append((body, options))
        result = []
        for item in body.checks:
            try:
                allowed = self._answer(item.user, item.relation, item.object)
                error = None
            except ValidationException:
                allowed = False
                error = SimpleNamespace(input_error="validation_error")
            result.append(
                SimpleNamespace(
                    allowed=allowed, correlation_id=item.correlation_id, error=error
                )
            )
        return SimpleNamespace(result=result)

    async def check(self, body, options):
        self.check_calls.append((body, options))
        return SimpleNamespace(
            allowed=self._answer(body.user, body.relation, body.object)
        )

    async def list_objects(self, body, options):
        self.list_calls.append((body, options))
        return SimpleNamespace(objects=[])

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

    async def write(self, body, options):
        self.write_calls.append((body, options))
        conflict = options.get("conflict")
        ignore_duplicates = (
            conflict is not None
            and conflict.on_duplicate_writes
            == ClientWriteRequestOnDuplicateWrites.IGNORE
        )
        writes = [(t.user, t.relation, t.object) for t in body.writes or []]
        for user, relation, obj in writes:
            if relation == RelationType.SUSPENDED.value and (
                not user.startswith("user:") or user == "user:*" or "#" in user
            ):
                raise ValidationException(status=400, reason="type not allowed")
            if (user, relation, obj) in self.tuples and not ignore_duplicates:
                raise ValidationException(status=400, reason="tuple already exists")
        self.tuples.update(writes)
        for tuple_ in body.deletes or []:
            self.tuples.discard((tuple_.user, tuple_.relation, tuple_.object))
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


def _engine(client: _AccountStatusStore, *, gate: bool = True) -> OpenFgaRebacEngine:
    engine = OpenFgaRebacEngine(
        OpenFgaRebacConfig(
            api_url="http://fake-openfga:8080",  # pyright: ignore[reportArgumentType]
        ),
        token="synthetic-test-token",  # nosec B106
        requires_active_accounts=gate,
    )
    engine._cached_client = client  # pyright: ignore[reportAttributeAccessIssue]
    return engine


@pytest.mark.asyncio
@pytest.mark.parametrize("consistency", [None, "HIGHER_CONSISTENCY"])
async def test_person_decisions_carry_no_account_status_item(
    consistency: str | None,
) -> None:
    """Account status is the request's check; a decision about a person, even a
    suspended one, asks only its own question at its caller's consistency."""
    client = _AccountStatusStore()
    client.tuples.add(_PERSON_SUSPENDED)
    engine = _engine(client)

    assert await engine.has_permission(
        _PERSON, TeamPermission.CAN_READ, _TEAM, consistency_token=consistency
    )
    assert await engine.has_permissions(
        _PERSON,
        [TeamPermission.CAN_READ, TeamPermission.CAN_UPDATE_INFO],
        _TEAM,
        consistency_token=consistency,
    ) == [True, True]
    assert (
        await engine.lookup_resources(
            _PERSON,
            TeamPermission.CAN_READ,
            Resource.TEAM,
            consistency_token=consistency,
        )
        == []
    )

    asked = [(body.user, body.relation, body.object) for body, _ in client.check_calls]
    asked += [
        (item.user, item.relation, item.object)
        for body, _ in client.batch_calls
        for item in body.checks
    ]
    assert asked == [
        ("user:person-synthetic", "can_read", "team:team-synthetic"),
        ("user:person-synthetic", "can_read", "team:team-synthetic"),
        ("user:person-synthetic", "can_update_info", "team:team-synthetic"),
    ]
    assert len(client.list_calls) == 1
    calls = client.check_calls + client.batch_calls + client.list_calls
    assert [options.get("consistency") for _, options in calls] == [consistency] * 3


@pytest.mark.asyncio
async def test_a_store_without_tuples_leaves_every_person_active() -> None:
    client = _AccountStatusStore()
    engine = _engine(client)

    assert await engine.has_permission(_PERSON, TeamPermission.CAN_READ, _TEAM)
    assert await engine.has_permissions(
        _PERSON, [TeamPermission.CAN_READ, TeamPermission.CAN_UPDATE_INFO], _TEAM
    ) == [True, True]
    await engine.require_active_account(_PERSON.id)
    assert (
        await engine.lookup_resources(_PERSON, TeamPermission.CAN_READ, Resource.TEAM)
        == []
    )

    assert len(client.list_calls) == 1
    assert client.write_calls == []
    assert client.tuples == set()


@pytest.mark.asyncio
async def test_an_active_person_without_the_permission_is_denied_not_refused() -> None:
    engine = _engine(_AccountStatusStore(target=False))

    assert await engine.has_permission(_PERSON, TeamPermission.CAN_READ, _TEAM) is False
    assert await engine.has_permissions(
        _PERSON, [TeamPermission.CAN_READ, TeamPermission.CAN_UPDATE_INFO], _TEAM
    ) == [False, False]


@pytest.mark.asyncio
async def test_a_suspended_person_is_refused_while_others_keep_access() -> None:
    client = _AccountStatusStore()
    engine = _engine(client)
    await engine.suspend_account(_PERSON.id)

    with pytest.raises(AccountStatusError) as caught:
        await engine.require_active_account(_PERSON.id)
    assert caught.value.unavailable is False

    await engine.require_active_account(_BYSTANDER.id)


@pytest.mark.asyncio
async def test_a_suspension_is_a_bounded_refusal_from_one_check() -> None:
    client = _AccountStatusStore()
    client.tuples.add(_PERSON_SUSPENDED)

    with pytest.raises(AccountStatusError) as caught:
        await _engine(client).require_active_account(_PERSON.id)

    assert isinstance(caught.value, PermissionError)
    assert str(caught.value) == "Current account status could not be established."
    assert len(client.check_calls) == 1
    assert client.batch_calls == []


@pytest.mark.asyncio
async def test_account_status_transport_failure_is_same_bounded_denial() -> None:
    class _Unavailable(_AccountStatusStore):
        async def check(self, body, options):
            raise RuntimeError("synthetic upstream canary")

    with pytest.raises(AccountStatusError) as caught:
        await _engine(_Unavailable()).require_active_account(_PERSON.id)

    assert caught.value.unavailable is True
    assert "canary" not in str(caught.value)


@pytest.mark.asyncio
async def test_explicit_account_status_check_needs_no_object_permission() -> None:
    client = _AccountStatusStore()
    client.tuples.add(_PERSON_SUSPENDED)

    with pytest.raises(AccountStatusError):
        await _engine(client).require_active_account("person-synthetic")

    body, options = client.check_calls[0]
    assert (body.user, body.relation, body.object) == _PERSON_SUSPENDED
    assert options["consistency"] == "HIGHER_CONSISTENCY"
    assert client.batch_calls == []


@pytest.mark.asyncio
async def test_with_the_gate_off_no_account_status_is_read() -> None:
    client = _AccountStatusStore()
    client.tuples.add(_PERSON_SUSPENDED)

    await _engine(client, gate=False).require_active_account(_PERSON.id)

    assert client.check_calls == client.batch_calls == []


@pytest.mark.asyncio
async def test_generic_relation_writes_and_deletes_cannot_change_account_status() -> (
    None
):
    client = _AccountStatusStore()
    engine = _engine(client)
    suspension = Relation(
        subject=_PERSON, relation=RelationType.SUSPENDED, resource=_ORGANIZATION
    )
    ordinary = Relation(
        subject=_PERSON, relation=RelationType.TEAM_MEMBER, resource=_TEAM
    )

    with pytest.raises(ValueError, match="account lifecycle"):
        await engine.add_relation(suspension)
    with pytest.raises(ValueError, match="account lifecycle"):
        await engine.add_relations([ordinary, suspension])
    with pytest.raises(ValueError, match="account lifecycle"):
        await engine.delete_relation(suspension)
    with pytest.raises(ValueError, match="account lifecycle"):
        await engine.delete_relations([ordinary, suspension])

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
async def test_suspending_an_account_writes_one_direct_tuple_without_logging_the_person(
    caplog,
) -> None:
    client = _AccountStatusStore()

    with caplog.at_level(
        logging.DEBUG, logger="fred_core.security.rebac.openfga_engine"
    ):
        await _engine(client).suspend_account(_PERSON.id)

    assert len(client.write_calls) == 1
    body, _options = client.write_calls[0]
    assert not body.deletes
    assert [(t.user, t.relation, t.object) for t in body.writes] == [_PERSON_SUSPENDED]
    assert client.tuples == {_PERSON_SUSPENDED}
    rendered = repr([record.__dict__ for record in caplog.records])
    assert _PERSON.id not in rendered


@pytest.mark.asyncio
async def test_a_retried_suspension_accepts_the_tuple_already_stored() -> None:
    """A retried account deletion rewrites the suspension, so the store must
    treat an existing tuple as written."""
    client = _AccountStatusStore()
    engine = _engine(client)

    await engine.suspend_account(_PERSON.id)
    await engine.suspend_account(_PERSON.id)

    assert len(client.write_calls) == 2
    assert client.tuples == {_PERSON_SUSPENDED}


@pytest.mark.asyncio
async def test_an_engine_without_the_account_status_model_cannot_suspend_or_validate() -> (
    None
):
    engine = _NonBatchingEngine(RuntimeError("unused"))

    with pytest.raises(RuntimeError, match="Account status authorization model"):
        await engine.suspend_account(_PERSON.id)
    with pytest.raises(RuntimeError, match="Account status authorization model"):
        await engine.validate_account_status_model()


@pytest.mark.asyncio
async def test_model_validation_selects_the_shipped_model_and_writes_nothing() -> None:
    client = _AccountStatusStore()
    engine = _engine(client)

    await engine.validate_account_status_model()

    assert engine._authorization_model_id == "synthetic-latest"
    assert client.write_calls == []
    assert client.read_calls == []


def _server_defaults(model: dict) -> None:
    """Empty-string defaults a model read back from the store may carry."""
    organization = _organization_of(model)
    for metadata in organization["metadata"]["relations"].values():
        for reference in metadata.get("directly_related_user_types", []):
            reference.setdefault("relation", "")
            reference.setdefault("condition", "")


@pytest.mark.asyncio
async def test_model_validation_accepts_empty_string_defaults() -> None:
    client = _AccountStatusStore()
    _server_defaults(client.model)

    await _engine(client).validate_account_status_model()


def _missing_suspended(model: dict) -> None:
    organization = _organization_of(model)
    del organization["relations"]["suspended"]
    del organization["metadata"]["relations"]["suspended"]


def _wildcard_suspended(model: dict) -> None:
    _organization_of(model)["metadata"]["relations"]["suspended"] = {
        "directly_related_user_types": [{"type": "user", "wildcard": {}}]
    }


def _person_or_everyone_suspended(model: dict) -> None:
    _organization_of(model)["metadata"]["relations"]["suspended"] = {
        "directly_related_user_types": [
            {"type": "user"},
            {"type": "user", "wildcard": {}},
        ]
    }


def _userset_suspended(model: dict) -> None:
    _organization_of(model)["metadata"]["relations"]["suspended"] = {
        "directly_related_user_types": [{"type": "team", "relation": "team_member"}]
    }


def _conditional_suspended(model: dict) -> None:
    _organization_of(model)["metadata"]["relations"]["suspended"] = {
        "directly_related_user_types": [
            {"type": "user", "condition": "synthetic_condition"}
        ]
    }


def _derived_suspended(model: dict) -> None:
    _organization_of(model)["relations"]["suspended"] = {
        "union": {
            "child": [
                {"this": {}},
                {"computedUserset": {"relation": "platform_admin"}},
            ]
        }
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reshape",
    [
        _missing_suspended,
        _wildcard_suspended,
        _person_or_everyone_suspended,
        _userset_suspended,
        _conditional_suspended,
        _derived_suspended,
    ],
)
async def test_model_validation_rejects_a_suspension_other_than_a_direct_person_tuple(
    reshape: Callable[[dict], None],
) -> None:
    client = _AccountStatusStore()
    reshape(client.model)

    with pytest.raises(
        RuntimeError, match="Account status authorization model is not available"
    ):
        await _engine(client).validate_account_status_model()


@pytest.mark.asyncio
async def test_a_pinned_model_without_suspension_fails_bounded_validation() -> None:
    client = _AccountStatusStore()
    _model_without_suspension(client.model)

    engine = _engine(client)
    engine._authorization_model_id = "synthetic-old-pin"
    with pytest.raises(
        RuntimeError, match="Account status authorization model is not available"
    ):
        await engine.validate_account_status_model()
    assert client.selected_model == "synthetic-old-pin"


@pytest.mark.asyncio
async def test_a_pinned_deployment_recovers_once_the_new_model_is_published() -> None:
    """The refusal is only half the contract. Once the model defining
    `suspended` is selected, every person Fred has not suspended has an active
    account without anything being written first."""
    client = _AccountStatusStore()
    _model_without_suspension(client.model)
    engine = _engine(client)
    engine._authorization_model_id = "synthetic-old-pin"

    with pytest.raises(
        RuntimeError, match="Account status authorization model is not available"
    ):
        await engine.validate_account_status_model()
    with pytest.raises(AccountStatusError) as caught:
        await engine.require_active_account(_PERSON.id)
    assert caught.value.unavailable is True

    # The new model is published and this participant selects it.
    client.model = json.loads(DEFAULT_SCHEMA)
    engine._authorization_model_id = None
    await engine.validate_account_status_model()
    assert engine._authorization_model_id == "synthetic-latest"

    await engine.require_active_account(_PERSON.id)
    assert await engine.has_permission(_PERSON, TeamPermission.CAN_READ, _TEAM) is True
    assert client.write_calls == []


@pytest.mark.asyncio
async def test_account_status_checks_do_not_log_subject_or_resource_identifiers(
    caplog,
) -> None:
    client = _AccountStatusStore()
    engine = _engine(client)
    with caplog.at_level(
        logging.DEBUG, logger="fred_core.security.rebac.openfga_engine"
    ):
        await engine.require_active_account(_PERSON.id)
        await engine.has_permission(_PERSON, TeamPermission.CAN_READ, _TEAM)
        await engine.has_permissions(_PERSON, [TeamPermission.CAN_READ], _TEAM)
    rendered = repr([record.__dict__ for record in caplog.records])
    assert _PERSON.id not in rendered
    assert _TEAM.id not in rendered
    assert "authorization_check" in rendered
    assert "authorization_batch_check" in rendered


@pytest.mark.asyncio
async def test_an_absent_account_status_answer_is_an_unconsultable_dependency() -> None:
    """A response that carries no answer must not be read as "not suspended"."""

    class _DropsAccountStatus(_AccountStatusStore):
        async def check(self, body, options):
            self.check_calls.append((body, options))
            # What the SDK makes of a reply body without `allowed`.
            return SimpleNamespace(allowed=None)

    with pytest.raises(AccountStatusError) as caught:
        await _engine(_DropsAccountStatus()).require_active_account(_PERSON.id)

    assert caught.value.unavailable is True


class _NonBatchingEngine(RebacEngine):
    """A plain engine with only the base class's own paths, answering every
    Check with `failure`."""

    def __init__(self, failure: Exception) -> None:
        self._failure = failure

    @property
    def requires_active_accounts(self) -> bool:
        return True

    async def _has_permission_raw(self, *args, **kwargs) -> bool:
        raise self._failure

    async def _persist_relation(self, *args, **kwargs):
        raise NotImplementedError

    async def delete_relation(self, *args, **kwargs):
        raise NotImplementedError

    async def delete_all_relations_of_reference(self, *args, **kwargs):
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


class _NonBatchingSuspensions(_NonBatchingEngine):
    """Answers `suspended` from stored person ids and grants every permission."""

    def __init__(self, suspended: set[str]) -> None:
        super().__init__(RuntimeError("unused"))
        self.suspended = suspended
        self.checks: list[tuple[RebacReference, object, RebacReference, object]] = []

    async def _has_permission_raw(
        self, subject, permission, resource, *, consistency_token=None, **kwargs
    ) -> bool:
        self.checks.append((subject, permission, resource, consistency_token))
        if permission == RelationType.SUSPENDED:
            return resource == _ORGANIZATION and subject.id in self.suspended
        return True


@pytest.mark.asyncio
async def test_the_base_engine_refuses_only_a_suspended_person() -> None:
    engine = _NonBatchingSuspensions({_PERSON.id})

    await engine.require_active_account(_BYSTANDER.id)
    with pytest.raises(AccountStatusError) as caught:
        await engine.require_active_account(_PERSON.id)
    assert caught.value.unavailable is False
    assert engine.checks == [
        (person, RelationType.SUSPENDED, _ORGANIZATION, RebacEngine.HIGHER_CONSISTENCY)
        for person in (_BYSTANDER, _PERSON)
    ]

    # Its decisions about the suspended person ask their own question only.
    assert await engine.has_permission(_PERSON, TeamPermission.CAN_READ, _TEAM)
    assert await engine.has_permissions(_PERSON, [TeamPermission.CAN_READ], _TEAM) == [
        True
    ]
    assert engine.checks[2:] == [
        (_PERSON, TeamPermission.CAN_READ, _TEAM, None),
        (_PERSON, TeamPermission.CAN_READ, _TEAM, None),
    ]


@pytest.mark.asyncio
async def test_an_account_status_requirement_survives_an_unconsultable_dependency() -> (
    None
):
    engine = _NonBatchingEngine(RuntimeError("synthetic upstream canary"))

    with pytest.raises(AccountStatusError) as caught:
        await engine.require_active_account("person-synthetic")

    assert caught.value.unavailable is True
    assert "canary" not in str(caught.value)


@pytest.mark.asyncio
async def test_a_store_unreachable_before_its_client_exists_is_unconsultable() -> None:
    """The store can already be gone when a call goes to establish its client.
    Left unclassified, that surfaces as an unhandled failure rather than as the
    dependency being unavailable."""
    engine = _engine(_AccountStatusStore())

    async def unreachable():
        raise ConnectionError("synthetic upstream canary")

    engine.get_client = unreachable  # pyright: ignore[reportAttributeAccessIssue]

    with pytest.raises(AccountStatusError) as caught:
        await engine.require_active_account(_PERSON.id)

    assert caught.value.unavailable is True
    assert "canary" not in str(caught.value)
