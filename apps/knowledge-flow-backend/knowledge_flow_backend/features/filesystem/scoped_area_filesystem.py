# Copyright Thales 2025
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

from dataclasses import dataclass
from typing import List

from fred_core import (
    FilesystemResourceInfoResult,
    KeycloakUser,
    RebacDisabledResult,
    TeamPermission,
)

from .virtual_fs_contract import (
    AREA_TEAMS,
    SUBAREA_AGENT_CONFIG,
    SUBAREA_AGENTS,
    SUBAREA_SHARED,
    SUBAREA_USERS,
    dir_entry,
    join_segments,
)
from .workspace_filesystem import WorkspaceFilesystem


@dataclass(frozen=True)
class ScopedAreaTarget:
    """
    Resolved storage target for one path inside a team box.

    Why this exists:
    - every team sub-area (`users`, `shared`, `agents`) maps onto the same storage
      primitive with `root_prefix="teams"` and `owner_override=team_id`
    - routing once into a concrete target removes repeated branching

    How to use:
    - build it through `ScopedAreaFilesystem._resolve_target(...)`
    - pass the fields to `WorkspaceFilesystem` operations

    Example:
    - `ScopedAreaTarget(visible_root="/teams/acme", subpath="shared/notes.md", ...)`
    """

    visible_root: str
    subpath: str
    owner_override: str
    root_prefix: str = AREA_TEAMS


class ScopedAreaFilesystem:
    """
    Filesystem router for the writable, team-rooted virtual area (`/teams/...`).

    Why this exists:
    - the unified layout (FILES-04) makes the team the confidentiality perimeter: every
      writable path is `/teams/{team_id}/{users|shared|agents}/...`
    - one router keeps the public MCP service thin and the permission rules in one place

    Permission model (the team box is sealed by ReBAC):
    - **enter the box:** `CAN_READ` on the team is required to touch anything under it
    - **`shared/`:** read needs `CAN_READ`; write/delete/mkdir need `CAN_UPDATE_RESOURCES`
    - **`users/{uid}/`:** the path uid MUST equal the acting user (personal-in-team)
    - **`agents/{agent_id}/users/{uid}/`:** same ownership rule as `users/`
    - **`agents/{agent_id}/config/`:** agent-config assets (#1903) — read needs
      `CAN_READ` (any member chatting with the agent fetches them); write/delete
      need `CAN_UPDATE_RESOURCES`, same as `shared/`

    The acting `team_id` always arrives as the first path segment (injected upstream from
    the verified session context); this router never derives it from agent-supplied state.

    Example:
    - `await scoped_fs.list_area(user, ("acme", "shared"))`
    """

    def __init__(self, *, scoped_storage: WorkspaceFilesystem, rebac) -> None:
        self.scoped_storage = scoped_storage
        self.rebac = rebac

    # ── permission helpers ────────────────────────────────────────────────

    async def _ensure_team(
        self,
        user: KeycloakUser,
        team_id: str,
        permission: TeamPermission,
    ) -> None:
        """Check one team permission, raising if the user lacks it."""
        await self.rebac.check_user_permission_or_raise(user, permission, team_id)

    def _ensure_own_uid(self, user: KeycloakUser, uid: str) -> None:
        """Reject access to another user's personal sub-area inside the team box."""
        if uid != user.uid:
            raise PermissionError("Cannot access another user's personal space")

    async def _list_readable_teams(
        self,
        user: KeycloakUser,
    ) -> List[FilesystemResourceInfoResult]:
        """List the team ids the user can read, as `/teams` directory entries."""
        readable_refs = await self.rebac.lookup_user_resources(user, TeamPermission.CAN_READ)
        if isinstance(readable_refs, RebacDisabledResult):
            return []
        readable_ids = sorted({ref.id for ref in readable_refs if ref.id})
        return [dir_entry(team_id) for team_id in readable_ids]

    async def _list_agent_ids(
        self,
        user: KeycloakUser,
        team_id: str,
    ) -> list[str]:
        """List agent ids that have per-user storage under one team."""
        entries = await self.scoped_storage.list(
            user,
            SUBAREA_AGENTS,
            owner_override=team_id,
            root_prefix=AREA_TEAMS,
        )
        return [entry.path for entry in entries if entry.is_dir()]

    # ── target resolution ─────────────────────────────────────────────────

    async def _resolve_target(
        self,
        user: KeycloakUser,
        segments: tuple[str, ...],
        *,
        want_write: bool,
        check_membership: bool = True,
    ) -> ScopedAreaTarget:
        """
        Resolve one `/teams/...` path to a concrete storage target, enforcing permissions.

        Raises FileNotFoundError for directory-only / malformed paths and PermissionError
        when the caller lacks the required team permission or owns a different uid.

        `check_membership` may be set False by callers that already verified `CAN_READ` on
        the team (e.g. listing/grep fan-out), to avoid a redundant ReBAC round-trip.
        """
        if not segments:
            raise FileNotFoundError("Team path must include a team id")
        team_id = segments[0]
        # Box-entry gate: membership is required to touch anything in the team.
        if check_membership:
            await self._ensure_team(user, team_id, TeamPermission.CAN_READ)
        if len(segments) < 2:
            raise FileNotFoundError(f"/{AREA_TEAMS}/{team_id} is a directory")

        sub = segments[1]
        rest = segments[2:]
        if sub == SUBAREA_SHARED:
            if want_write:
                await self._ensure_team(user, team_id, TeamPermission.CAN_UPDATE_RESOURCES)
            subpath_parts: tuple[str, ...] = (SUBAREA_SHARED, *rest)
        elif sub == SUBAREA_USERS:
            if not rest:
                raise FileNotFoundError(f"/{AREA_TEAMS}/{team_id}/{SUBAREA_USERS} is a directory")
            self._ensure_own_uid(user, rest[0])
            subpath_parts = (SUBAREA_USERS, *rest)
        elif sub == SUBAREA_AGENTS:
            # /teams/{team}/agents/{agent_id}/users/{uid}/...   (per-user agent space)
            # /teams/{team}/agents/{agent_id}/config/...        (agent-config assets, #1903)
            if len(rest) >= 2 and rest[1] == SUBAREA_AGENT_CONFIG:
                if want_write:
                    await self._ensure_team(user, team_id, TeamPermission.CAN_UPDATE_RESOURCES)
            elif len(rest) >= 3 and rest[1] == SUBAREA_USERS:
                self._ensure_own_uid(user, rest[2])
            else:
                raise FileNotFoundError(
                    f"Agent path must be /{AREA_TEAMS}/{team_id}/{SUBAREA_AGENTS}/{{agent_id}}/{SUBAREA_USERS}/{{uid}}/... "
                    f"or /{AREA_TEAMS}/{team_id}/{SUBAREA_AGENTS}/{{agent_id}}/{SUBAREA_AGENT_CONFIG}/..."
                )
            subpath_parts = (SUBAREA_AGENTS, *rest)
        else:
            raise FileNotFoundError(f"Unsupported team sub-area: {sub!r}")

        return ScopedAreaTarget(
            visible_root=f"/{AREA_TEAMS}/{team_id}",
            subpath=join_segments(subpath_parts),
            owner_override=team_id,
        )

    def _visible_path(self, team_id: str, relative_path: str) -> str:
        """Rebuild a stable absolute virtual path from a team-relative storage hit."""
        return f"/{AREA_TEAMS}/{team_id}/{relative_path.lstrip('/')}"

    # ── public operations ─────────────────────────────────────────────────

    async def list_area(
        self,
        user: KeycloakUser,
        segments: tuple[str, ...],
    ) -> List[FilesystemResourceInfoResult]:
        """List one directory inside the `/teams` area (synthetic levels + storage)."""
        if not segments:
            return await self._list_readable_teams(user)

        team_id = segments[0]
        await self._ensure_team(user, team_id, TeamPermission.CAN_READ)

        if len(segments) == 1:
            return [dir_entry(SUBAREA_USERS), dir_entry(SUBAREA_SHARED), dir_entry(SUBAREA_AGENTS)]

        sub = segments[1]
        rest = segments[2:]
        # Synthetic intermediate directories that expose only the caller's own spaces.
        if sub == SUBAREA_USERS and not rest:
            return [dir_entry(user.uid)]
        if sub == SUBAREA_AGENTS and not rest:
            return [dir_entry(agent_id) for agent_id in await self._list_agent_ids(user, team_id)]
        if sub == SUBAREA_AGENTS and len(rest) == 1:
            return [dir_entry(SUBAREA_USERS), dir_entry(SUBAREA_AGENT_CONFIG)]
        if sub == SUBAREA_AGENTS and len(rest) == 2 and rest[1] == SUBAREA_USERS:
            return [dir_entry(user.uid)]

        target = await self._resolve_target(user, segments, want_write=False, check_membership=False)
        return await self.scoped_storage.list(
            user,
            target.subpath,
            owner_override=target.owner_override,
            root_prefix=target.root_prefix,
        )

    async def stat_area(
        self,
        user: KeycloakUser,
        segments: tuple[str, ...],
    ) -> FilesystemResourceInfoResult:
        """Stat one path inside the `/teams` area."""
        if not segments:
            return dir_entry(AREA_TEAMS)

        team_id = segments[0]
        await self._ensure_team(user, team_id, TeamPermission.CAN_READ)
        if len(segments) == 1:
            return dir_entry(team_id)

        sub = segments[1]
        rest = segments[2:]
        # Synthetic directory levels (not stored objects).
        if sub == SUBAREA_SHARED and not rest:
            return dir_entry(SUBAREA_SHARED)
        if sub == SUBAREA_USERS and not rest:
            return dir_entry(SUBAREA_USERS)
        if sub == SUBAREA_USERS and len(rest) == 1:
            self._ensure_own_uid(user, rest[0])
            return dir_entry(rest[0])
        if sub == SUBAREA_AGENTS and not rest:
            return dir_entry(SUBAREA_AGENTS)
        if sub == SUBAREA_AGENTS and len(rest) == 1:
            return dir_entry(rest[0])
        if sub == SUBAREA_AGENTS and len(rest) == 2 and rest[1] == SUBAREA_USERS:
            return dir_entry(SUBAREA_USERS)
        if sub == SUBAREA_AGENTS and len(rest) == 2 and rest[1] == SUBAREA_AGENT_CONFIG:
            return dir_entry(SUBAREA_AGENT_CONFIG)
        if sub == SUBAREA_AGENTS and len(rest) == 3 and rest[1] == SUBAREA_USERS:
            self._ensure_own_uid(user, rest[2])
            return dir_entry(rest[2])

        target = await self._resolve_target(user, segments, want_write=False, check_membership=False)
        return await self.scoped_storage.stat(
            user,
            target.subpath,
            owner_override=target.owner_override,
            root_prefix=target.root_prefix,
        )

    async def cat_area(
        self,
        user: KeycloakUser,
        segments: tuple[str, ...],
    ) -> str:
        """Read one file inside the `/teams` area."""
        target = await self._resolve_target(user, segments, want_write=False)
        return await self.scoped_storage.get_text(
            user,
            target.subpath,
            owner_override=target.owner_override,
            root_prefix=target.root_prefix,
        )

    async def write_area(
        self,
        user: KeycloakUser,
        segments: tuple[str, ...],
        data: str,
    ) -> None:
        """Write one file inside the `/teams` area."""
        target = await self._resolve_target(user, segments, want_write=True)
        await self.scoped_storage.put(
            user,
            target.subpath,
            data,
            owner_override=target.owner_override,
            root_prefix=target.root_prefix,
        )

    async def read_bytes_area(
        self,
        user: KeycloakUser,
        segments: tuple[str, ...],
    ) -> bytes:
        """Read one file inside the `/teams` area as raw bytes (binary-safe)."""
        target = await self._resolve_target(user, segments, want_write=False)
        return await self.scoped_storage.get_bytes(
            user,
            target.subpath,
            owner_override=target.owner_override,
            root_prefix=target.root_prefix,
        )

    async def write_bytes_area(
        self,
        user: KeycloakUser,
        segments: tuple[str, ...],
        data: bytes,
    ) -> None:
        """Write one file inside the `/teams` area from raw bytes (binary-safe)."""
        target = await self._resolve_target(user, segments, want_write=True)
        await self.scoped_storage.put(
            user,
            target.subpath,
            data,
            owner_override=target.owner_override,
            root_prefix=target.root_prefix,
        )

    async def delete_area(
        self,
        user: KeycloakUser,
        segments: tuple[str, ...],
    ) -> None:
        """Delete one file or folder inside the `/teams` area."""
        target = await self._resolve_target(user, segments, want_write=True)
        await self.scoped_storage.delete(
            user,
            target.subpath,
            owner_override=target.owner_override,
            root_prefix=target.root_prefix,
        )

    async def mkdir_area(
        self,
        user: KeycloakUser,
        segments: tuple[str, ...],
    ) -> None:
        """Create one directory inside the `/teams` area."""
        target = await self._resolve_target(user, segments, want_write=True)
        await self.scoped_storage.mkdir(
            user,
            target.subpath,
            owner_override=target.owner_override,
            root_prefix=target.root_prefix,
        )

    async def grep_area(
        self,
        user: KeycloakUser,
        pattern: str,
        segments: tuple[str, ...],
    ) -> List[str]:
        """
        Search the `/teams` area and return visible absolute paths.

        Crucially, a team-wide or sub-area-wide search only ever descends into scopes the
        caller may read — `shared/` plus the caller's own `users/{uid}` and per-agent
        folders — so another user's personal files are never matched.
        """
        if not segments:
            matches: list[str] = []
            for team_entry in await self._list_readable_teams(user):
                matches.extend(await self.grep_area(user, pattern, (team_entry.path,)))
            return matches

        team_id = segments[0]
        await self._ensure_team(user, team_id, TeamPermission.CAN_READ)
        sub = segments[1] if len(segments) > 1 else None

        # Fan out the broad cases into the caller's allowed scopes only.
        if sub is None:
            scopes: list[tuple[str, ...]] = [(team_id, SUBAREA_SHARED), (team_id, SUBAREA_USERS, user.uid)]
            for agent_id in await self._list_agent_ids(user, team_id):
                scopes.append((team_id, SUBAREA_AGENTS, agent_id, SUBAREA_USERS, user.uid))
                scopes.append((team_id, SUBAREA_AGENTS, agent_id, SUBAREA_AGENT_CONFIG))
            return [hit for scope in scopes for hit in await self._grep_scope(user, pattern, scope)]
        if sub == SUBAREA_USERS and len(segments) == 2:
            return await self._grep_scope(user, pattern, (team_id, SUBAREA_USERS, user.uid))
        if sub == SUBAREA_AGENTS and len(segments) == 2:
            out: list[str] = []
            for agent_id in await self._list_agent_ids(user, team_id):
                out.extend(await self._grep_scope(user, pattern, (team_id, SUBAREA_AGENTS, agent_id, SUBAREA_USERS, user.uid)))
            return out
        return await self._grep_scope(user, pattern, segments)

    async def _grep_scope(
        self,
        user: KeycloakUser,
        pattern: str,
        segments: tuple[str, ...],
    ) -> List[str]:
        """Grep one concrete scope (team membership already verified by the caller)."""
        target = await self._resolve_target(user, segments, want_write=False, check_membership=False)
        return [
            self._visible_path(target.owner_override, hit)
            for hit in await self.scoped_storage.grep(
                user,
                pattern,
                target.subpath,
                owner_override=target.owner_override,
                root_prefix=target.root_prefix,
            )
        ]
