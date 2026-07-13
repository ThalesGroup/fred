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

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from fred_core.security.models import AuthorizationError, Resource
from fred_core.security.structure import KeycloakUser

ORGANIZATION_ID = "fred"
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RebacReference:
    """Point to one actor or object in authorization checks.

    Example:
    - `RebacReference(Resource.USER, "alice-id")`
    - `RebacReference(Resource.TEAM, "thales-team-id")`
    """

    type: Resource
    id: str


class RelationType(str, Enum):
    """Named links used to describe who can do what.

    Example:
    - `owner`: full control on a resource (agent/tag ownership — unrelated to
      team roles below).
    - `team_admin`: team governance authority.
    - `team_member`: can access team-scoped reads.
    """

    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"
    PARENT = "parent"
    ORGANIZATION = "organization"
    PUBLIC = "public"

    # AUTHZ-05 target platform roles (RFC FRED-AUTHORIZATION-TARGET-MODEL §6.1).
    # Stored tuples only, granted by config-seeded bootstrap or explicit admin
    # action — never derived from Keycloak roles or groups.
    PLATFORM_ADMIN = "platform_admin"
    PLATFORM_OBSERVER = "platform_observer"

    # AUTHZ-05 target team roles (RFC §26 — renamed from owner/manager/member
    # during the second implementation pass). team_admin and team_editor are
    # orthogonal, not hierarchical (REBAC.md "hard cross-write rule").
    TEAM_ADMIN = "team_admin"
    TEAM_EDITOR = "team_editor"
    TEAM_ANALYST = "team_analyst"
    TEAM_MEMBER = "team_member"


class TagPermission(str, Enum):
    """Actions allowed on libraries/tags.

    Example:
    - `read`: list/search content.
    - `update`: rename tag, edit metadata, attach resources.
    """

    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    SHARE = "share"

    # Normaly those 3 are "relation" and not "permission"
    # but openfga does not make distinction so we added
    # them here to use lookup_resources on them
    OWNER = RelationType.OWNER.value
    EDITOR = RelationType.EDITOR.value
    VIEWER = RelationType.VIEWER.value


class DocumentPermission(str, Enum):
    """Actions allowed on documents stored in libraries."""

    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    # Process a document for RAG / SQL extraction. The `document#process`
    # relation already exists in schema.fga; this enum value exposes it.
    PROCESS = "process"


class ResourcePermission(str, Enum):
    """Actions allowed on non-document resources (files, templates, etc.)."""

    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    SHARE = "share"


class TeamPermission(str, Enum):
    """Actions allowed at team scope.

    Example:
    - `can_update_resources`: create/update team libraries.
    - `can_administer_members`: add/remove team members.
    """

    CAN_READ = "can_read"
    CAN_UPDATE_INFO = "can_update_info"
    CAN_UPDATE_RESOURCES = "can_update_resources"
    CAN_UPDATE_AGENTS = "can_update_agents"
    CAN_READ_MEMEBERS = "can_read_members"
    CAN_ADMINISTER_MEMBERS = "can_administer_members"
    # AUTHZ-05 (RFC §26): renamed from CAN_ADMINISTER_MANAGERS/CAN_ADMINISTER_OWNERS.
    CAN_ADMINISTER_EDITORS = "can_administer_editors"
    CAN_ADMINISTER_ANALYSTS = "can_administer_analysts"
    CAN_ADMINISTER_ADMINS = "can_administer_admins"
    CAN_READ_CONVERSATIONS = "can_read_conversations"
    # AUTHZ-05 review item 1b: `team_member`-only, unlike CAN_READ (which
    # also admits `public`) — gates seeing/using the team's agents.
    CAN_USE_TEAM_AGENTS = "can_use_team_agents"

    # Team-scoped evaluation capabilities (RFC §6.2/§3.2).
    CAN_RUN_EVALUATIONS = "can_run_evaluations"
    CAN_MANAGE_EVALUATION_CORPUS = "can_manage_evaluation_corpus"
    CAN_READ_CONVERSATIONS_FOR_EVALUATION = "can_read_conversations_for_evaluation"


# Team permissions a `service_agent` caller is allowed to satisfy without an OpenFGA
# relation (RFC EVAL-AUTH, Solution A). Read-only: the evaluation worker executes
# agents (gated by CAN_READ) and never mutates a team. Any write permission falls
# through to the normal ReBAC check and is therefore denied.
SERVICE_AGENT_ALLOWED_TEAM_PERMISSIONS = frozenset({TeamPermission.CAN_READ})


class AgentPermission(str, Enum):
    """Actions allowed on agents."""

    READ = "read"
    UPDATE = "update"
    DELETE = "delete"

    # "owner" is a relation in the FGA schema, not a permission,
    # but openfga does not make distinction so we add it here
    # to use lookup_resources on it (for owner-based filtering).
    OWNER = RelationType.OWNER.value


class OrganizationPermission(str, Enum):
    """Actions allowed at global organization scope.

    These gate endpoints that act on global / infrastructure surfaces with no
    resource instance to scope on (observability, platform administration).
    The check target is always the singleton ``organization:fred``. AUTHZ-05
    review item 8a removed the "any connected user" tier entirely (it never
    protected anything specific) — only platform_admin-gated capabilities and
    the raw `platform_observer` relation check remain.
    """

    CAN_EDIT_AGENT_CLASS_PATH = "can_edit_agent_class_path"

    # Already-defined organization relations, now exposed to Python callers.
    CAN_CREATE_TEAM = "can_create_team"

    # AUTHZ-05 review item 9 (RFC Part 6 §32): team-registry governance —
    # existence of teams only, never their data.
    CAN_LIST_ALL_TEAMS = "can_list_all_teams"
    CAN_DELETE_TEAM = "can_delete_team"
    CAN_RESCUE_TEAM_ADMIN = "can_rescue_team_admin"

    # RFC FRED-AUTHORIZATION-TARGET-MODEL §6.1: platform_observer's own named
    # capability (platform_admin included via the platform_observer union) —
    # the one relation for cross-user / platform-wide KPI observation. Gates
    # both the standalone KPI dashboard (`/monitoring/kpis`) and the
    # control-plane Analytics presets (`/admin/analytics`). AUTHZ-05 review
    # item 16: previously split into a second, platform_admin-only
    # `CAN_READ_KPI_GLOBAL` (legacy READ_GLOBAL) for the Analytics presets —
    # retired as a duplicate of this relation the RFC never asked for; today
    # `/admin/analytics` and `/monitoring/kpis` show the same platform-wide
    # recap to both platform_admin and platform_observer. When the Analytics
    # dashboard grows admin-only technical panels, gate those specific
    # widgets on a new, narrower capability — don't resurrect this split.
    CAN_OBSERVE_PLATFORM = "can_observe_platform"

    # Platform administration (platform_admin only).
    CAN_ADMINISTER_USERS = "can_administer_users"
    CAN_MANAGE_PLATFORM = "can_manage_platform"
    CAN_RUN_BENCHMARK = "can_run_benchmark"

    # Direct check against the raw `platform_observer` relation — not a
    # computed capability. Used to derive display-only frontend flags
    # (`PermissionSummary.is_platform_observer`, AUTHZ-05 review item 4/8a)
    # where no gated action exists to piggyback on.
    IS_PLATFORM_OBSERVER = "platform_observer"


RebacPermission = (
    TagPermission
    | DocumentPermission
    | ResourcePermission
    | TeamPermission
    | AgentPermission
    | OrganizationPermission
)


def _resource_for_permission(permission: RebacPermission) -> Resource:
    """Map one permission enum value to the resource type it targets.

    Example:
    - `TeamPermission.CAN_READ` -> `Resource.TEAM`
    - `TagPermission.UPDATE` -> `Resource.TAGS`
    """
    if isinstance(permission, TagPermission):
        return Resource.TAGS
    if isinstance(permission, DocumentPermission):
        return Resource.DOCUMENTS
    if isinstance(permission, ResourcePermission):
        return Resource.RESOURCES
    if isinstance(permission, TeamPermission):
        return Resource.TEAM
    if isinstance(permission, AgentPermission):
        return Resource.AGENT
    if isinstance(permission, OrganizationPermission):
        return Resource.ORGANIZATION
    raise ValueError(f"Unsupported permission type: {permission!r}")


@dataclass(frozen=True)
class Relation:
    """One authorization statement linking an actor to a target.

    Example:
    - `user alice` `owner` of `tag invoices`
    - `team thales` `owner` of `tag cir`
    """

    subject: RebacReference
    relation: RelationType
    resource: RebacReference


class RebacDisabledResult:
    """
    Marker object returned when relationship authorization is disabled.

    Callers can branch on this value and apply fallback behavior.
    """


class RebacEngine(ABC):
    """Core authorization API used by all Fred backends.

    This class provides the common business operations ("can Alice update team
    resources?") while each concrete engine (OpenFGA, noop) handles storage.
    """

    @property
    def enabled(self) -> bool:
        """Tell whether relationship authorization checks are active."""
        return True

    async def close(self) -> None:
        """Release any held connections or sessions. No-op by default."""

    @abstractmethod
    async def add_relation(self, relation: Relation) -> str | None:
        """Persist one authorization statement.

        Example:
        - Save `team thales owner tag cir`.
        Returns a backend-specific consistency token when available.
        """

    @abstractmethod
    async def delete_relation(self, relation: Relation) -> str | None:
        """Remove one authorization statement.

        Returns a backend-specific consistency token when available.
        """

    @abstractmethod
    async def delete_all_relations_of_reference(
        self, reference: RebacReference
    ) -> str | None:
        """Remove every statement touching the given reference.

        Example:
        - deleting an agent can remove all `owner`, `viewer`, or parent links.
        """

    async def add_relations(self, relations: Iterable[Relation]) -> str | None:
        """Persist several statements and return the latest consistency token.

        Example:
        - Add owner and viewer links in one call after resource sharing.
        """

        tokens = await asyncio.gather(
            *(self.add_relation(relation) for relation in relations),
            return_exceptions=False,
        )

        token: str | None = None
        for t in reversed(tokens):
            if t is not None:
                token = t
                break

        return token

    async def ensure_team_organization_relations(
        self,
        team_ids: Iterable[str],
    ) -> str | None:
        """Ensure each team is linked to the singleton organization.

        Team checks in Fred always operate in a team context and require
        deterministic organization/team graph edges for future policy evolution.
        This helper maintains the persistent relation:
        ``organization:fred#organization@team:<team_id>``.

        Example:
        - Before checking team permissions on `team:<id>`, ensure
          `organization:fred -> team:<id>` exists.

        This helper is idempotent and returns the write consistency token when
        available.
        """
        unique_team_ids: list[str] = []
        seen: set[str] = set()
        for team_id in team_ids:
            if not team_id or team_id in seen:
                continue
            seen.add(team_id)
            unique_team_ids.append(team_id)

        if not unique_team_ids:
            return None

        relations = [
            Relation(
                subject=RebacReference(Resource.ORGANIZATION, ORGANIZATION_ID),
                relation=RelationType.ORGANIZATION,
                resource=RebacReference(Resource.TEAM, team_id),
            )
            for team_id in unique_team_ids
        ]
        return await self.add_relations(relations)

    async def add_user_relation(
        self,
        user: KeycloakUser,
        relation: RelationType,
        resource_type: Resource,
        resource_id: str,
    ) -> str | None:
        """Create one statement where the subject is a user.

        Example:
        - Add `user:bob editor tag:finance`.
        """
        return await self.add_relation(
            Relation(
                subject=RebacReference(Resource.USER, user.uid),
                relation=relation,
                resource=RebacReference(resource_type, resource_id),
            )
        )

    async def delete_relations(self, relations: Iterable[Relation]) -> str | None:
        """Delete several statements and return the latest consistency token.

        Example:
        - Remove owner/manager/member links when removing a team member.
        """
        tokens = await asyncio.gather(
            *(self.delete_relation(relation) for relation in relations),
            return_exceptions=False,
        )

        token: str | None = None
        for t in reversed(tokens):
            if t is not None:
                token = t
                break

        return token

    @abstractmethod
    async def list_relations(
        self,
        *,
        resource_type: Resource,
        relation: RelationType,
        subject_type: Resource | None = None,
        consistency_token: str | None = None,
    ) -> list[Relation] | RebacDisabledResult:
        """List persisted statements matching the given filters."""

    async def delete_user_relation(
        self,
        user: KeycloakUser,
        relation: RelationType,
        resource_type: Resource,
        resource_id: str,
    ) -> str | None:
        """Delete one statement where the subject is a user."""
        return await self.delete_relation(
            Relation(
                subject=RebacReference(Resource.USER, user.uid),
                relation=relation,
                resource=RebacReference(resource_type, resource_id),
            )
        )

    async def delete_user_relations(self, user: KeycloakUser) -> str | None:
        """Delete all statements referencing a user."""
        return await self.delete_all_relations_of_reference(
            RebacReference(Resource.USER, user.uid)
        )

    @abstractmethod
    async def lookup_resources(
        self,
        subject: RebacReference,
        permission: RebacPermission,
        resource_type: Resource,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> list[RebacReference] | RebacDisabledResult:
        """List resources a subject can access for one permission.

        Example:
        - Return all teams a user can read.
        """

    @abstractmethod
    async def lookup_subjects(
        self,
        resource: RebacReference,
        relation: RelationType,
        subject_type: Resource,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> list[RebacReference] | RebacDisabledResult:
        """List subjects linked to a resource by one relation.

        Example:
        - List all owners of one team.
        """

    async def lookup_user_resources(
        self,
        user: KeycloakUser,
        permission: RebacPermission,
        *,
        consistency_token: str | None = None,
    ) -> list[RebacReference] | RebacDisabledResult:
        """List resources a user can access for one permission."""
        return await self.lookup_resources(
            subject=RebacReference(Resource.USER, user.uid),
            permission=permission,
            resource_type=_resource_for_permission(permission),
            consistency_token=consistency_token,
        )

    @abstractmethod
    async def has_permission(
        self,
        subject: RebacReference,
        permission: RebacPermission,
        resource: RebacReference,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> bool:
        """Return `True` when a subject is authorized for an action."""

    async def has_user_permission(
        self,
        user: KeycloakUser,
        permission: RebacPermission,
        resource_id: str,
        *,
        consistency_token: str | None = None,
    ) -> bool:
        """Check one permission for one user/resource pair."""
        resource_type = _resource_for_permission(permission)
        return await self.has_permission(
            RebacReference(Resource.USER, user.uid),
            permission,
            RebacReference(resource_type, resource_id),
            consistency_token=consistency_token,
        )

    async def check_permission_or_raise(
        self,
        subject: RebacReference,
        permission: RebacPermission,
        resource: RebacReference,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> None:
        """Raise `AuthorizationError` when access is denied.

        Example:
        - Raises if Bob tries to update a team where he is only a member.
        """
        if not await self.has_permission(
            subject,
            permission,
            resource,
            contextual_relations=contextual_relations,
            consistency_token=consistency_token,
        ):
            logger.warning(
                "ReBAC authorization denied: subject=%s:%s permission=%s resource=%s:%s",
                subject.type.value,
                subject.id,
                permission.value,
                resource.type.value,
                resource.id,
            )
            raise AuthorizationError(
                subject.id,
                permission.value,
                resource.type,
                f"Not authorized to {permission.value} {resource.type.value} {resource.id}",
            )

    async def check_user_permission_or_raise(
        self,
        user: KeycloakUser,
        permission: RebacPermission,
        resource_id: str,
        *,
        consistency_token: str | None = None,
    ) -> None:
        """User-focused wrapper around `check_permission_or_raise`."""
        resource_type = _resource_for_permission(permission)
        await self.check_permission_or_raise(
            RebacReference(Resource.USER, user.uid),
            permission,
            RebacReference(resource_type, resource_id),
            consistency_token=consistency_token,
        )

    async def check_user_team_permission_or_raise(
        self,
        user: KeycloakUser,
        permission: TeamPermission,
        team_id: str,
    ) -> str | None:
        """Check one team permission with the canonical team workflow.

        This helper always ensures the team is linked to the organization
        before checking permissions.
        """
        return await self.check_user_team_permissions_or_raise(
            user=user,
            team_id=team_id,
            permissions=[permission],
        )

    async def check_user_team_permissions_or_raise(
        self,
        user: KeycloakUser,
        team_id: str,
        permissions: Iterable[TeamPermission],
    ) -> str | None:
        """Check team permissions with consistent organization-team bootstrap.

        This is the canonical path for team permission checks across services.
        It ensures ``organization -> team`` exists, propagates the resulting
        consistency token, and executes all requested checks.
        """
        consistency_token = await self.ensure_team_organization_relations([team_id])

        permissions_to_check = list(permissions)
        if not permissions_to_check:
            return consistency_token

        await asyncio.gather(
            *(
                self.check_user_permission_or_raise(
                    user=user,
                    permission=permission,
                    resource_id=team_id,
                    consistency_token=consistency_token,
                )
                for permission in permissions_to_check
            ),
            return_exceptions=False,
        )
        return consistency_token
