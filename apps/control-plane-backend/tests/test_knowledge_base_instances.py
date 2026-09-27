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


"""A folder that fills itself: creating one, and what that creates.

The four effects of one gesture — the library, the instance, the pod's grant
over that library, and the schedule — all happen or none does. Nothing here
reaches a live OpenFGA, a live Temporal or a live knowledge-flow: each is faked
at its own boundary, and what is asserted is the order, the undo and the scope.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Iterable
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, cast

import pytest
from control_plane_backend.knowledge_bases import api as knowledge_base_api
from control_plane_backend.knowledge_bases import instances as instances_module
from control_plane_backend.knowledge_bases.instances import (
    KnowledgeBaseInstanceNotFound,
    KnowledgeBaseNotEnabled,
    create_instance,
    delete_instance,
    displayable_configuration,
    list_instances,
)
from control_plane_backend.knowledge_bases.runs import (
    RunAccessDenied,
    RunNotFound,
    build_run_context,
)
from control_plane_backend.knowledge_bases.validation import (
    InstanceConfigurationInvalid,
)
from fastapi import HTTPException
from fred_core import AssertedUser, Resource
from fred_core.scheduler import IntervalSchedule
from fred_core.security.delegation import DelegationConfig, initialize_delegation
from fred_core.security.models import AuthorizationError
from fred_core.security.structure import SERVICE_AGENT_ROLE, KeycloakUser
from fred_sdk.contracts.models import FieldSpec
from temporalio.client import ScheduleAlreadyRunningError
from temporalio.service import RPCError, RPCStatusCode

DEFINITION = "acme.kb.http-markdown"
OTHER_DEFINITION = "acme.kb.other"
TEAM = "team-1"
OTHER_TEAM = "team-2"
POD_SUBJECT = "service-account-kb-acme"
POD_CLIENT = "kb-acme"
ISSUER = "https://id.invalid/realms/fred"


# --------------------------------------------------------------------------
# Fakes, one per boundary the transaction crosses
# --------------------------------------------------------------------------


class _FakeRebac:
    """Records relations and answers the two questions instances ask."""

    def __init__(
        self,
        *,
        usable: Iterable[tuple[str, str]] = (),
        members: Iterable[str] = (),
        public: Iterable[str] = (),
    ) -> None:
        self.relations: set[tuple[str, str, str]] = set()
        self._usable = set(usable)
        self._members = set(members)
        self._public = set(public)
        self.add_failures = 0

    @staticmethod
    def _key(relation: Any) -> tuple[str, str, str]:
        name = lambda v: str(getattr(v, "value", v))  # noqa: E731
        return (
            f"{name(relation.subject.type)}:{relation.subject.id}",
            name(relation.relation),
            f"{name(relation.resource.type)}:{relation.resource.id}",
        )

    async def has_permission(self, subject, permission, resource, **kwargs) -> bool:
        del permission, kwargs
        return (str(subject.id), str(resource.id)) in self._usable

    async def add_relation(self, relation: Any, actor_uid: str | None = None) -> None:
        del actor_uid
        if self.add_failures:
            self.add_failures -= 1
            raise RuntimeError("the authorization engine refused the write")
        self.relations.add(self._key(relation))

    async def delete_relation(self, relation: Any) -> None:
        self.relations.discard(self._key(relation))

    async def check_user_team_permission_or_raise(self, *, user, permission, team_id):
        asked = str(getattr(permission, "value", permission))
        # `can_read` is the one permission a PUBLIC team hands to every signed-in
        # user, through the `public: [user:*]` wildcard. Modelling membership as
        # a plain set would hide that, and hide any guard that reached for the
        # wrong permission with it.
        if asked == "can_read" and team_id in self._public:
            return
        if team_id not in self._members:
            raise AuthorizationError(user.uid, asked, Resource.TEAM)

    def may_write_in(self, library_id: str) -> bool:
        """What `tag#update` resolves to for the pod: a direct editor statement."""
        return (
            f"user:{POD_SUBJECT}",
            "editor",
            f"tag:{library_id}",
        ) in self.relations


class _FakeDefinition:
    def __init__(
        self, definition_id: str, *, subject: str, fields: list[FieldSpec]
    ) -> None:
        self.id = definition_id
        self.name = "HTTP Markdown"
        self.prefix = "acme.kb"
        self.version = "1.0.0"
        self.description = "Synchronize Markdown"
        self.client_id = POD_CLIENT
        self.subject = subject
        self.configuration_fields = fields


class _FakeDefinitionStore:
    def __init__(self, definitions: list[_FakeDefinition]) -> None:
        self.rows = {definition.id: definition for definition in definitions}

    async def get(self, definition_id: str) -> Any:
        return self.rows.get(definition_id)


class _StoredInstance:
    id: str
    team_id: str
    granted_subject: str

    def __init__(self, **kwargs: Any) -> None:
        self.__dict__.update(kwargs)
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = self.created_at


class _FakeInstanceStore:
    def __init__(self, *, fail_create: bool = False) -> None:
        self.rows: dict[str, Any] = {}
        self.fail_create = fail_create

    async def create(self, **kwargs: Any) -> Any:
        if self.fail_create:
            raise RuntimeError("the database refused the insert")
        row = _StoredInstance(
            id=kwargs["instance_id"],
            definition_id=kwargs["definition_id"],
            team_id=kwargs["team_id"],
            library_id=kwargs["library_id"],
            library_name=kwargs["library_name"],
            schedule_json=kwargs["schedule_json"],
            suspended=kwargs["suspended"],
            configuration=kwargs["configuration"],
            granted_subject=kwargs["granted_subject"],
            created_by=kwargs["created_by"],
        )
        self.rows[row.id] = row
        return row

    async def get(self, instance_id: str) -> Any:
        return self.rows.get(instance_id)

    async def list_for_team(self, team_id: str) -> list[Any]:
        return [row for row in self.rows.values() if row.team_id == team_id]

    async def delete(self, instance_id: str) -> bool:
        return self.rows.pop(instance_id, None) is not None


class _FakeLibraryClient:
    """Stands in for knowledge-flow's folder endpoints."""

    created: dict[str, str] = {}
    fail_create = False
    next_id = 0

    def __init__(self, base_url: str, authorization: str) -> None:
        self.authorization = authorization

    async def create(self, *, name: str, team_id: str, description: str) -> str:
        if type(self).fail_create:
            raise RuntimeError("knowledge-flow refused the folder")
        type(self).next_id += 1
        library_id = f"lib-{type(self).next_id}"
        type(self).created[library_id] = name
        return library_id

    async def delete(self, library_id: str) -> None:
        type(self).created.pop(library_id, None)

    @classmethod
    def reset(cls) -> None:
        cls.created = {}
        cls.fail_create = False
        cls.next_id = 0


class _FakeScheduleHandle:
    def __init__(self, client: "_FakeTemporal", schedule_id: str) -> None:
        self._client = client
        self._id = schedule_id

    async def delete(self) -> None:
        if self._id not in self._client.schedules:
            raise RPCError("no such schedule", RPCStatusCode.NOT_FOUND, b"")
        del self._client.schedules[self._id]

    async def update(self, updater) -> None:
        # The real client accepts a plain or an async callback, so the fake has
        # to as well, or it only ever exercises one of the two.
        update = updater(SimpleNamespace(description=None))
        if inspect.isawaitable(update):
            update = await update
        self._client.schedules[self._id] = update.schedule


class _FakeWorkflowHandle:
    def __init__(
        self, status: Any, result: Any = None, *, missing: bool = False
    ) -> None:
        self._status = status
        self._result = result
        self._missing = missing

    async def describe(self) -> Any:
        if self._missing:
            raise RPCError("gone", RPCStatusCode.NOT_FOUND, b"")
        return SimpleNamespace(status=self._status)

    async def result(self) -> Any:
        return self._result


class _FakeTemporal:
    def __init__(self, *, fail_create: bool = False) -> None:
        self.schedules: dict[str, Any] = {}
        self.fail_create = fail_create
        self.workflows: dict[str, _FakeWorkflowHandle] = {}

    async def create_schedule(self, schedule_id: str, schedule: Any) -> None:
        if self.fail_create:
            raise RuntimeError("the workflow engine is unreachable")
        if schedule_id in self.schedules:
            raise ScheduleAlreadyRunningError()
        self.schedules[schedule_id] = schedule

    def get_schedule_handle(self, schedule_id: str) -> _FakeScheduleHandle:
        return _FakeScheduleHandle(self, schedule_id)

    def get_workflow_handle(self, execution_id: str, run_id: str | None = None):
        return self.workflows.get(
            run_id or execution_id, _FakeWorkflowHandle(None, missing=True)
        )


class _Deps:
    def __init__(
        self,
        *,
        rebac: _FakeRebac,
        definitions: list[_FakeDefinition],
        temporal: _FakeTemporal | None = None,
        instance_store: _FakeInstanceStore | None = None,
    ) -> None:
        self.team_dependencies = SimpleNamespace(rebac=rebac)
        self.definitions = _FakeDefinitionStore(definitions)
        self.instances = instance_store or _FakeInstanceStore()
        self.temporal = temporal or _FakeTemporal()
        self.configuration = SimpleNamespace(
            platform=SimpleNamespace(
                knowledge_flow_base_url="http://kf/knowledge-flow/v1"
            ),
            scheduler=SimpleNamespace(
                temporal=SimpleNamespace(workflow_id_prefix="cp", task_queue="q")
            ),
            knowledge_bases=SimpleNamespace(run_max_attempts=2),
        )

    def get_knowledge_base_definition_store(self):
        return self.definitions

    def get_knowledge_base_instance_store(self):
        return self.instances

    async def get_temporal_client(self):
        return self.temporal


def _user(uid: str = "alice") -> KeycloakUser:
    return KeycloakUser(uid=uid, username=uid, roles=["admin"], email=None)


def _pod(client_id: str = POD_CLIENT) -> KeycloakUser:
    return KeycloakUser(
        uid=POD_SUBJECT,
        username="pod",
        roles=[SERVICE_AGENT_ROLE],
        email=None,
        client_id=client_id,
    )


def _workload(
    client_id: str = POD_CLIENT,
    caller_roles: frozenset[str] = frozenset({"delegation_caller"}),
) -> KeycloakUser:
    """A pod's bearer that holds no service role, only the delegation caller role."""
    return KeycloakUser(
        uid=POD_SUBJECT,
        username="pod",
        roles=[],
        email=None,
        client_id=client_id,
        token_issuer=ISSUER,
        token_audiences=frozenset({"fred-delegation"}),
        token_type="Bearer",
        caller_roles=caller_roles,
    )


def _person(run_id: str = "run-1") -> AssertedUser:
    return AssertedUser(uid="alice", client_id=POD_CLIENT, run_id=run_id, agent_id="a")


def _accept_delegated_calls() -> None:
    initialize_delegation(
        DelegationConfig(accept_delegated_calls=True),
        issuers=[ISSUER],
        user_clients=["app"],
    )


def _fields() -> list[FieldSpec]:
    return [
        FieldSpec(key="base_url", type="url", title="URL", required=True),
        FieldSpec(key="token", type="secret", title="Token"),
        FieldSpec(key="depth", type="integer", title="Depth", min=1, max=10),
    ]


def _deps(**kwargs: Any) -> _Deps:
    _FakeLibraryClient.reset()
    rebac = kwargs.pop(
        "rebac",
        _FakeRebac(usable={(TEAM, DEFINITION)}, members={TEAM}),
    )
    definitions = kwargs.pop(
        "definitions",
        [_FakeDefinition(DEFINITION, subject=POD_SUBJECT, fields=_fields())],
    )
    return _Deps(rebac=rebac, definitions=definitions, **kwargs)


@pytest.fixture(autouse=True)
def _fake_library(monkeypatch):
    _FakeLibraryClient.reset()
    monkeypatch.setattr(instances_module, "LibraryClient", _FakeLibraryClient)
    yield
    _FakeLibraryClient.reset()


async def _create(deps: _Deps, **overrides: Any):
    payload: dict[str, Any] = {
        "user": _user(),
        "authorization": "Bearer alice",
        "definition_id": DEFINITION,
        "team_id": TEAM,
        "folder_name": "Handbook",
        "schedule": IntervalSchedule(every_seconds=86_400),
        "suspended": False,
        "configuration": {"base_url": "https://example.test/docs"},
        "deps": deps,
    }
    payload.update(overrides)
    return await create_instance(**payload)


# --------------------------------------------------------------------------
# 3.0 — four effects, or none
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_creating_a_synchronized_folder_does_all_four_things():
    deps = _deps()

    instance = await _create(deps)

    assert _FakeLibraryClient.created == {instance.library_id: "Handbook"}
    assert deps.instances.rows[instance.id].library_id == instance.library_id
    assert deps.team_dependencies.rebac.may_write_in(instance.library_id)
    assert f"cp-kb-{instance.id}" in deps.temporal.schedules


@pytest.mark.parametrize(
    "break_step",
    ["library", "grant", "schedule", "instance"],
)
@pytest.mark.asyncio
async def test_a_partial_creation_leaves_nothing_behind(break_step: str):
    """Whichever step fails, the ones already applied are undone."""
    rebac = _FakeRebac(usable={(TEAM, DEFINITION)}, members={TEAM})
    temporal = _FakeTemporal(fail_create=break_step == "schedule")
    store = _FakeInstanceStore(fail_create=break_step == "instance")
    deps = _deps(rebac=rebac, temporal=temporal, instance_store=store)
    if break_step == "library":
        _FakeLibraryClient.fail_create = True
    if break_step == "grant":
        rebac.add_failures = 1

    with pytest.raises(RuntimeError):
        await _create(deps)

    assert _FakeLibraryClient.created == {}
    assert store.rows == {}
    assert rebac.relations == set()
    assert temporal.schedules == {}


@pytest.mark.asyncio
async def test_a_pod_is_editor_on_its_own_library_and_on_no_other():
    """Two instances of one definition, in one team, and no shared reach."""
    deps = _deps()

    mine = await _create(deps, folder_name="Mine")
    theirs = await _create(deps, folder_name="Theirs")

    rebac = deps.team_dependencies.rebac
    assert mine.library_id != theirs.library_id
    assert rebac.may_write_in(mine.library_id)
    assert rebac.may_write_in(theirs.library_id)
    # And nothing beyond its own instances: a folder nobody synchronized.
    assert not rebac.may_write_in("lib-someone-elses")
    assert not any(rel == "team_member" for _, rel, _ in rebac.relations)


@pytest.mark.asyncio
async def test_the_grant_never_reaches_the_team():
    """A team-level right would let a pod fill the folder beside its own."""
    deps = _deps()

    instance = await _create(deps)

    assert deps.team_dependencies.rebac.relations == {
        (f"user:{POD_SUBJECT}", "editor", f"tag:{instance.library_id}")
    }


@pytest.mark.asyncio
async def test_a_second_instance_of_one_definition_gets_its_own_everything():
    deps = _deps()

    first = await _create(deps, folder_name="First")
    second = await _create(deps, folder_name="Second")

    assert first.id != second.id
    assert first.library_id != second.library_id
    assert {f"cp-kb-{first.id}", f"cp-kb-{second.id}"} <= set(deps.temporal.schedules)


@pytest.mark.asyncio
async def test_deleting_a_folder_leaves_no_grant_and_no_schedule():
    deps = _deps()
    instance = await _create(deps)

    await delete_instance(
        user=_user(), authorization="Bearer alice", instance_id=instance.id, deps=deps
    )

    assert deps.team_dependencies.rebac.relations == set()
    assert deps.temporal.schedules == {}
    assert _FakeLibraryClient.created == {}
    assert deps.instances.rows == {}


# --------------------------------------------------------------------------
# 3.1 — instances exist only where the definition is enabled
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_creating_an_instance_is_refused_while_the_definition_is_not_enabled():
    deps = _deps(rebac=_FakeRebac(usable=set(), members={TEAM}))

    with pytest.raises(KnowledgeBaseNotEnabled):
        await _create(deps)

    assert _FakeLibraryClient.created == {}


@pytest.mark.asyncio
async def test_two_instances_coexist_independently():
    deps = _deps()

    await _create(
        deps,
        folder_name="First",
        schedule=IntervalSchedule(every_seconds=604_800),
        suspended=True,
    )
    await _create(deps, folder_name="Second")

    listed = {
        row.library_name: row
        for row in await list_instances(user=_user(), team_id=TEAM, deps=deps)
    }
    assert json.loads(listed["First"].schedule_json)["every_seconds"] == 604_800
    assert listed["First"].suspended is True
    assert json.loads(listed["Second"].schedule_json)["every_seconds"] == 86_400
    assert listed["Second"].suspended is False


@pytest.mark.asyncio
async def test_an_instance_is_bound_to_its_creating_team():
    deps = _deps(
        rebac=_FakeRebac(usable={(TEAM, DEFINITION)}, members={TEAM, OTHER_TEAM})
    )

    await _create(deps)

    assert await list_instances(user=_user(), team_id=OTHER_TEAM, deps=deps) == []


# --------------------------------------------------------------------------
# 3.3 — team isolation
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_public_team_does_not_hand_its_knowledge_bases_to_everyone():
    """A PUBLIC team is discoverable, not readable.

    `can_read` is satisfied by the `public: [user:*]` wildcard, so guarding a
    Knowledge Base with it would show every signed-in user which sources a team
    synchronizes and what those sources declare — including which of their
    fields are secret.
    """
    deps = _deps(
        rebac=_FakeRebac(usable={(TEAM, DEFINITION)}, members={TEAM}, public={TEAM})
    )
    instance = await _create(deps)
    stranger = _user("mallory")
    deps.team_dependencies.rebac._members = set()  # noqa: SLF001

    with pytest.raises(KnowledgeBaseInstanceNotFound):
        await instances_module.read_instance(
            user=stranger, instance_id=instance.id, deps=deps
        )
    with pytest.raises(KnowledgeBaseInstanceNotFound):
        await list_instances(user=stranger, team_id=TEAM, deps=deps)


@pytest.mark.asyncio
async def test_a_non_member_cannot_read_delete_or_list():
    deps = _deps()
    instance = await _create(deps)
    stranger = _user("mallory")
    deps.team_dependencies.rebac._members = {TEAM}  # noqa: SLF001

    async def _as_stranger(coro):
        with pytest.raises(KnowledgeBaseInstanceNotFound):
            await coro

    deps.team_dependencies.rebac._members = set()  # noqa: SLF001
    await _as_stranger(
        instances_module.read_instance(
            user=stranger, instance_id=instance.id, deps=deps
        )
    )
    await _as_stranger(
        delete_instance(
            user=stranger, authorization="Bearer m", instance_id=instance.id, deps=deps
        )
    )
    await _as_stranger(list_instances(user=stranger, team_id=TEAM, deps=deps))
    # Nothing was touched by any of it.
    assert deps.instances.rows[instance.id] is not None


# --------------------------------------------------------------------------
# 3.2 — one strict validation, twice
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_invalid_value_is_rejected_naming_the_field():
    deps = _deps()

    with pytest.raises(InstanceConfigurationInvalid) as raised:
        await _create(
            deps, configuration={"base_url": "https://x.test", "depth": "500"}
        )

    assert raised.value.field_key == "depth"
    assert _FakeLibraryClient.created == {}


@pytest.mark.asyncio
async def test_a_missing_required_field_is_rejected_naming_it():
    deps = _deps()

    with pytest.raises(InstanceConfigurationInvalid) as raised:
        await _create(deps, configuration={})

    assert raised.value.field_key == "base_url"


@pytest.mark.asyncio
async def test_a_secret_is_stored_and_handed_to_the_pod_but_never_displayed():
    deps = _deps()
    instance = await _create(
        deps,
        configuration={"base_url": "https://x.test", "token": "s3cret"},
    )

    shown = displayable_configuration(deps.instances.rows[instance.id], _fields())
    context = await build_run_context(
        user=_pod(),
        definition_id=DEFINITION,
        instance_id=instance.id,
        run_id="run-1",
        deps=deps,
    )

    assert "token" not in shown
    assert shown["base_url"] == "https://x.test"
    assert context.configuration["token"] == "s3cret"


@pytest.mark.asyncio
async def test_the_same_validator_refuses_a_stored_configuration_gone_stale():
    """A definition republished with different declared fields.

    The values were valid when written; a handler promised validated
    configuration must not be the one to discover they are not any more.
    """
    deps = _deps()
    instance = await _create(deps)
    deps.definitions.rows[DEFINITION].configuration_fields = [
        FieldSpec(key="base_url", type="integer", title="URL", required=True)
    ]

    with pytest.raises(InstanceConfigurationInvalid) as raised:
        await build_run_context(
            user=_pod(),
            definition_id=DEFINITION,
            instance_id=instance.id,
            run_id="run-1",
            deps=deps,
        )

    assert raised.value.field_key == "base_url"


# --------------------------------------------------------------------------
# 4.4 — the run context, scoped to the client the definition is bound to
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_run_context_carries_the_library_the_pod_must_fill():
    deps = _deps()
    instance = await _create(deps)

    context = await build_run_context(
        user=_pod(),
        definition_id=DEFINITION,
        instance_id=instance.id,
        run_id="run-1",
        deps=deps,
    )

    assert context.library_id == instance.library_id
    assert context.team_id == TEAM
    assert context.run_id == "run-1"


@pytest.mark.asyncio
async def test_another_definitions_client_is_refused():
    deps = _deps()
    instance = await _create(deps)

    with pytest.raises(RunAccessDenied):
        await build_run_context(
            user=_pod(client_id="kb-someone-else"),
            definition_id=DEFINITION,
            instance_id=instance.id,
            run_id="run-1",
            deps=deps,
        )


@pytest.mark.asyncio
async def test_a_broad_service_role_alone_does_not_authorize():
    """Every backend workload holds one, and this is where the secrets are."""
    deps = _deps()
    instance = await _create(deps)
    nameless = KeycloakUser(
        uid="svc", username="svc", roles=[SERVICE_AGENT_ROLE], email=None
    )

    with pytest.raises(RunAccessDenied):
        await build_run_context(
            user=nameless,
            definition_id=DEFINITION,
            instance_id=instance.id,
            run_id="run-1",
            deps=deps,
        )


@pytest.mark.asyncio
async def test_an_instance_of_another_definition_is_not_this_pods_to_read():
    deps = _deps(
        definitions=[
            _FakeDefinition(DEFINITION, subject=POD_SUBJECT, fields=_fields()),
            _FakeDefinition(OTHER_DEFINITION, subject="sa-other", fields=[]),
        ]
    )
    instance = await _create(deps)

    with pytest.raises(RunNotFound):
        await build_run_context(
            user=_pod(),
            definition_id=OTHER_DEFINITION,
            instance_id=instance.id,
            run_id="run-1",
            deps=deps,
        )


_EVERY_DELEGATION_SETTING = pytest.mark.parametrize(
    "config",
    [
        DelegationConfig(),
        DelegationConfig(act_for_people=True),
        DelegationConfig(accept_delegated_calls=True),
        DelegationConfig(act_for_people=True, accept_delegated_calls=True),
    ],
    ids=["delegation-off", "acting-for-people", "accepting-calls", "both"],
)


@pytest.mark.asyncio
@_EVERY_DELEGATION_SETTING
async def test_the_bound_pod_reads_its_run_whatever_the_delegation_setting(
    config: DelegationConfig,
):
    # A run names no person, so the pod's own credential is the whole authority.
    initialize_delegation(config, issuers=[ISSUER], user_clients=["app"])
    deps = _deps()
    instance = await _create(deps)

    context = await knowledge_base_api.get_knowledge_base_run_context(
        DEFINITION, instance.id, "run-1", cast(Any, deps), _pod()
    )

    assert context.run_id == "run-1"
    assert context.library_id == instance.library_id


@pytest.mark.asyncio
@_EVERY_DELEGATION_SETTING
async def test_the_delegation_role_alone_never_reads_a_run(config: DelegationConfig):
    """The caller role lets a workload name people; it is not a service identity."""
    initialize_delegation(config, issuers=[ISSUER], user_clients=["app"])
    deps = _deps()
    instance = await _create(deps)

    with pytest.raises(RunAccessDenied, match="requires a service identity"):
        await build_run_context(
            user=_workload(),
            definition_id=DEFINITION,
            instance_id=instance.id,
            run_id="run-1",
            deps=deps,
        )


@pytest.mark.asyncio
async def test_a_person_named_by_a_grant_cannot_read_a_run():
    _accept_delegated_calls()
    deps = _deps()
    instance = await _create(deps)

    with pytest.raises(HTTPException) as raised:
        await knowledge_base_api.get_knowledge_base_run_context(
            DEFINITION, instance.id, "run-1", cast(Any, deps), _person()
        )

    assert (raised.value.status_code, raised.value.detail) == (
        403,
        "requires_own_credential",
    )


# --------------------------------------------------------------------------
# 4.5 — the run's state comes from the engine, never from the pod
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_suspended_instance_registers_a_paused_schedule():
    deps = _deps()

    instance = await _create(deps, suspended=True)

    assert deps.temporal.schedules[f"cp-kb-{instance.id}"].state.paused is True


@pytest.mark.asyncio
async def test_deleting_an_instance_removes_its_schedule():
    deps = _deps()
    instance = await _create(deps)

    await delete_instance(
        user=_user(), authorization="Bearer alice", instance_id=instance.id, deps=deps
    )

    assert deps.temporal.schedules == {}


@pytest.mark.asyncio
async def test_the_run_a_schedule_starts_carries_freds_attempt_budget():
    deps = _deps()
    deps.configuration.knowledge_bases.run_max_attempts = 3

    instance = await _create(deps)

    action = deps.temporal.schedules[f"cp-kb-{instance.id}"].action
    assert action.args[0].max_attempts == 3
    assert action.args[0].definition_id == DEFINITION
    assert action.args[0].instance_id == instance.id


def test_the_budget_is_read_from_configuration_and_bounded():
    from control_plane_backend.config.models import KnowledgeBasesConfig

    assert KnowledgeBasesConfig().run_max_attempts == 2
    with pytest.raises(ValueError):
        KnowledgeBasesConfig(run_max_attempts=0)


def test_the_workflow_bounds_its_activity_with_that_budget():
    """Without a policy the engine retries for ever and nothing is ever failed."""
    import inspect

    from fred_sdk.knowledge_base import _workflow

    source = inspect.getsource(_workflow.SynchronizeWorkflow)
    assert "retry_policy=RetryPolicy(maximum_attempts=payload.max_attempts)" in source


# --------------------------------------------------------------------------
# What an edit and a deletion must not destroy
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_refused_library_deletion_leaves_the_instance_whole():
    """A member without the right to delete the folder must not half-delete it."""
    deps = _deps()
    instance = await _create(deps)

    class _RefusingLibrary(_FakeLibraryClient):
        async def delete(self, library_id: str) -> None:
            raise PermissionError("knowledge-flow refused the folder deletion")

    instances_module.LibraryClient = _RefusingLibrary
    try:
        with pytest.raises(PermissionError):
            await delete_instance(
                user=_user(),
                authorization="Bearer alice",
                instance_id=instance.id,
                deps=deps,
            )
    finally:
        instances_module.LibraryClient = _FakeLibraryClient

    assert deps.instances.rows[instance.id] is not None
    assert deps.temporal.schedules[f"cp-kb-{instance.id}"] is not None
    assert deps.team_dependencies.rebac.may_write_in(instance.library_id)


@pytest.mark.asyncio
async def test_deletion_removes_the_grant_that_was_made_not_the_one_named_today():
    """A republication can move a definition onto a new service account."""
    deps = _deps()
    instance = await _create(deps)
    deps.definitions.rows[DEFINITION].subject = "service-account-recreated"

    await delete_instance(
        user=_user(), authorization="Bearer alice", instance_id=instance.id, deps=deps
    )

    assert deps.team_dependencies.rebac.relations == set()


@pytest.mark.asyncio
async def test_a_stale_stored_configuration_is_a_bad_request_not_a_server_fault():
    """The documented republished-definition case reaches the pod as a 422."""
    from control_plane_backend.knowledge_bases.validation import (
        InstanceConfigurationInvalid as _Invalid,
    )

    assert _Invalid("x").http_status == 422


@pytest.mark.asyncio
async def test_two_instances_of_one_period_do_not_fire_on_the_same_second():
    """An interval with no offset is measured from the epoch, for everyone."""
    deps = _deps()

    first = await _create(deps, folder_name="First")
    second = await _create(deps, folder_name="Second")

    offsets = {
        deps.temporal.schedules[f"cp-kb-{i.id}"].spec.intervals[0].offset
        for i in (first, second)
    }
    assert len(offsets) == 2


def test_a_badly_typed_declared_default_is_refused_rather_than_handed_over():
    """A default is the author's, and would otherwise be the one unchecked value."""
    from control_plane_backend.knowledge_bases.validation import (
        validate_instance_configuration,
    )

    with pytest.raises(InstanceConfigurationInvalid) as raised:
        validate_instance_configuration(
            [FieldSpec(key="depth", type="integer", title="Depth", default="five")], {}
        )

    assert raised.value.field_key == "depth"
