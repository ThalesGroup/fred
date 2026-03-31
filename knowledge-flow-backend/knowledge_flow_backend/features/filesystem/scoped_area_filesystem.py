from __future__ import annotations

from dataclasses import dataclass
from typing import List

from fred_core import (
    AgentPermission,
    FilesystemResourceInfoResult,
    KeycloakUser,
    RebacDisabledResult,
    TeamPermission,
)

from .virtual_fs_contract import (
    AREA_AGENT,
    AREA_TEAM,
    AREA_WORKSPACE,
    VirtualArea,
    dir_entry,
    join_segments,
)
from .workspace_filesystem import WorkspaceFilesystem


@dataclass(frozen=True)
class ScopedAreaTarget:
    """
    Resolved storage target for one writable virtual filesystem area.

    Why this exists:
    - workspace, agent, and team areas share the same storage primitive
    - routing once into a concrete storage target removes repeated branching

    How to use:
    - build it through `ScopedAreaFilesystem._resolve_target(...)`
    - pass the fields to `WorkspaceFilesystem` operations

    Example:
    - `ScopedAreaTarget(visible_root="/agent/a1", subpath="notes.md", ...)`
    """

    visible_root: str
    subpath: str
    owner_override: str | None = None
    root_prefix: str | None = None


class ScopedAreaFilesystem:
    """
    Filesystem router for the writable virtual areas.

    Why this exists:
    - `/workspace`, `/agent`, and `/team` share one storage backend but differ in
      permission rules and visible root layout
    - isolating that routing keeps the public MCP service thin and easy to test

    How to use:
    - instantiate once with `WorkspaceFilesystem` and the rebac engine
    - call the area-specific methods with a resolved `VirtualArea`

    Example:
    - `await scoped_fs.list_area(user, VirtualArea.WORKSPACE, ("notes",))`
    """

    def __init__(self, *, scoped_storage: WorkspaceFilesystem, rebac) -> None:
        """
        Store the shared collaborators for scoped storage operations.

        Why this exists:
        - all writable virtual areas use the same storage adapter and permission engine
        - constructor injection keeps the router reusable and easy to unit test

        How to use:
        - pass the configured storage facade and rebac engine once at startup

        Example:
        - `ScopedAreaFilesystem(scoped_storage=workspace_fs, rebac=engine)`
        """

        self.scoped_storage = scoped_storage
        self.rebac = rebac

    async def _list_readable_agent_roots(
        self,
        user: KeycloakUser,
    ) -> List[FilesystemResourceInfoResult]:
        """
        List readable agent ids under the virtual `/agent` root.

        Why this exists:
        - `/agent` should expose only agent folders the current user can actually read
        - root browsing should behave like a permission-shaped filesystem, not a fixed menu

        How to use:
        - call when listing the virtual `/agent` directory itself

        Example:
        - `await _list_readable_agent_roots(user)`
        """

        readable_refs = await self.rebac.lookup_user_resources(user, AgentPermission.READ)
        if isinstance(readable_refs, RebacDisabledResult):
            return []
        readable_ids = sorted({ref.id for ref in readable_refs if ref.id})
        return [dir_entry(agent_id) for agent_id in readable_ids]

    async def _list_readable_team_roots(
        self,
        user: KeycloakUser,
    ) -> List[FilesystemResourceInfoResult]:
        """
        List readable team ids under the virtual `/team` root.

        Why this exists:
        - `/team` should expose only team folders the current user can actually read
        - root browsing should behave like a permission-shaped filesystem, not a fixed menu

        How to use:
        - call when listing the virtual `/team` directory itself

        Example:
        - `await _list_readable_team_roots(user)`
        """

        readable_refs = await self.rebac.lookup_user_resources(user, TeamPermission.CAN_READ)
        if isinstance(readable_refs, RebacDisabledResult):
            return []
        readable_ids = sorted({ref.id for ref in readable_refs if ref.id})
        return [dir_entry(team_id) for team_id in readable_ids]

    async def _ensure_agent_permission(
        self,
        user: KeycloakUser,
        *,
        agent_id: str,
        permission: AgentPermission,
    ) -> None:
        """
        Check one permission against an agent-scoped area.

        Why this exists:
        - agent files live in a shared storage backend but require dedicated rebac checks
        - centralizing the call keeps agent routing concise

        How to use:
        - pass the user, target agent id, and required permission

        Example:
        - `await _ensure_agent_permission(user, agent_id="a1", permission=AgentPermission.READ)`
        """

        await self.rebac.check_user_permission_or_raise(user, permission, agent_id)

    async def _ensure_team_permission(
        self,
        user: KeycloakUser,
        *,
        team_id: str,
        permission: TeamPermission,
    ) -> None:
        """
        Check one permission against a team-scoped area.

        Why this exists:
        - team files live in the same storage backend as user files
        - team-specific rebac checks should stay in one place

        How to use:
        - pass the user, target team id, and required permission

        Example:
        - `await _ensure_team_permission(user, team_id="t1", permission=TeamPermission.CAN_READ)`
        """

        await self.rebac.check_user_permission_or_raise(user, permission, team_id)

    def _visible_path(self, target: ScopedAreaTarget, relative_path: str) -> str:
        """
        Build one visible absolute path under a scoped area root.

        Why this exists:
        - grep-style operations return storage-relative hits
        - callers should receive stable absolute virtual paths instead

        How to use:
        - pass the resolved target plus the relative hit from scoped storage

        Example:
        - `_visible_path(target, "notes.md")` returns `"/agent/a1/notes.md"`
        """

        return f"{target.visible_root}/{relative_path.lstrip('/')}"

    def _workspace_target(self, segments: tuple[str, ...]) -> ScopedAreaTarget:
        """
        Resolve one workspace path into the shared storage contract.

        Why this exists:
        - `/workspace` is the canonical writable root for user files
        - the workspace area does not need extra rebac lookup beyond the caller user

        How to use:
        - pass workspace-relative segments from `resolve_virtual_path(...)`

        Example:
        - `_workspace_target(("notes", "todo.md"))`
        """

        return ScopedAreaTarget(
            visible_root=f"/{AREA_WORKSPACE}",
            subpath=join_segments(segments),
        )

    async def _agent_target(
        self,
        user: KeycloakUser,
        segments: tuple[str, ...],
        *,
        permission: AgentPermission,
    ) -> ScopedAreaTarget:
        """
        Resolve one agent path into the shared storage contract.

        Why this exists:
        - agent files live under a different storage root and owner mapping
        - permission checks must happen before any storage access

        How to use:
        - pass agent-relative segments where the first segment is the agent id

        Example:
        - `await _agent_target(user, ("a1", "config.yaml"), permission=AgentPermission.READ)`
        """

        if not segments:
            raise FileNotFoundError("Agent path must include an agent id")
        agent_id = segments[0]
        await self._ensure_agent_permission(
            user,
            agent_id=agent_id,
            permission=permission,
        )
        return ScopedAreaTarget(
            visible_root=f"/{AREA_AGENT}/{agent_id}",
            subpath=join_segments(segments[1:]),
            owner_override=f"{agent_id}/config",
            root_prefix="agents",
        )

    async def _team_target(
        self,
        user: KeycloakUser,
        segments: tuple[str, ...],
        *,
        permission: TeamPermission,
    ) -> ScopedAreaTarget:
        """
        Resolve one team path into the shared storage contract.

        Why this exists:
        - team files live under a different storage root and owner mapping
        - permission checks must happen before any storage access

        How to use:
        - pass team-relative segments where the first segment is the team id

        Example:
        - `await _team_target(user, ("team-1", "docs"), permission=TeamPermission.CAN_READ)`
        """

        if not segments:
            raise FileNotFoundError("Team path must include a team id")
        team_id = segments[0]
        await self._ensure_team_permission(
            user,
            team_id=team_id,
            permission=permission,
        )
        return ScopedAreaTarget(
            visible_root=f"/{AREA_TEAM}/{team_id}",
            subpath=join_segments(segments[1:]),
            owner_override=team_id,
            root_prefix="teams",
        )

    async def _resolve_target(
        self,
        user: KeycloakUser,
        area: VirtualArea,
        segments: tuple[str, ...],
        *,
        read_permission: AgentPermission | TeamPermission | None = None,
        write_permission: AgentPermission | TeamPermission | None = None,
    ) -> ScopedAreaTarget:
        """
        Resolve one non-corpus area path into a storage target.

        Why this exists:
        - the main difference between list/read/write/delete flows is the permission type
        - one resolver keeps the service layer free from per-area plumbing

        How to use:
        - pass the resolved virtual area plus the required permission for that operation

        Example:
        - `await _resolve_target(user, VirtualArea.TEAM, ("t1", "notes.md"), read_permission=TeamPermission.CAN_READ)`
        """

        if area == VirtualArea.WORKSPACE:
            return self._workspace_target(segments)
        if area == VirtualArea.AGENT:
            permission = read_permission or write_permission
            if not isinstance(permission, AgentPermission):
                raise ValueError("Agent area requires an AgentPermission")
            return await self._agent_target(
                user,
                segments,
                permission=permission,
            )
        if area == VirtualArea.TEAM:
            permission = read_permission or write_permission
            if not isinstance(permission, TeamPermission):
                raise ValueError("Team area requires a TeamPermission")
            return await self._team_target(
                user,
                segments,
                permission=permission,
            )
        raise FileNotFoundError("Unsupported filesystem area")

    def _ensure_supported_area(self, area: VirtualArea) -> None:
        """
        Reject non-writable virtual areas before routing to scoped storage.

        Why this exists:
        - this router is intentionally limited to workspace, agent, and team areas
        - failing early avoids accidental corpus/root routing through team defaults

        How to use:
        - call at the start of public scoped-area operations

        Example:
        - `_ensure_supported_area(VirtualArea.WORKSPACE)`
        """

        if area not in {VirtualArea.WORKSPACE, VirtualArea.AGENT, VirtualArea.TEAM}:
            raise FileNotFoundError("Unsupported filesystem area")

    async def list_area(
        self,
        user: KeycloakUser,
        area: VirtualArea,
        segments: tuple[str, ...],
    ) -> List[FilesystemResourceInfoResult]:
        """
        List one writable virtual area directory.

        Why this exists:
        - list behavior differs slightly for workspace, agent, and team roots
        - callers should not duplicate those root rules

        How to use:
        - pass the resolved writable area plus its relative segments

        Example:
        - `await list_area(user, VirtualArea.AGENT, ("a1",))`
        """

        self._ensure_supported_area(area)
        if area == VirtualArea.WORKSPACE:
            target = self._workspace_target(segments)
            return await self.scoped_storage.list(
                user,
                target.subpath,
                owner_override=target.owner_override,
                root_prefix=target.root_prefix,
            )
        if area == VirtualArea.AGENT and not segments:
            return await self._list_readable_agent_roots(user)
        if area == VirtualArea.TEAM and not segments:
            return await self._list_readable_team_roots(user)

        permission = AgentPermission.READ if area == VirtualArea.AGENT else TeamPermission.CAN_READ
        target = await self._resolve_target(
            user,
            area,
            segments,
            read_permission=permission,
        )
        return await self.scoped_storage.list(
            user,
            target.subpath,
            owner_override=target.owner_override,
            root_prefix=target.root_prefix,
        )

    async def stat_area(
        self,
        user: KeycloakUser,
        area: VirtualArea,
        segments: tuple[str, ...],
    ) -> FilesystemResourceInfoResult:
        """
        Stat one writable virtual area path.

        Why this exists:
        - area roots and owner roots are virtual directories, not stored entries
        - callers still expect normal file-or-directory answers

        How to use:
        - pass the resolved writable area plus its relative segments

        Example:
        - `await stat_area(user, VirtualArea.WORKSPACE, ("notes.md",))`
        """

        self._ensure_supported_area(area)
        if area == VirtualArea.WORKSPACE:
            if not segments:
                return dir_entry(AREA_WORKSPACE)
            target = self._workspace_target(segments)
            return await self.scoped_storage.stat(
                user,
                target.subpath,
                owner_override=target.owner_override,
                root_prefix=target.root_prefix,
            )

        if area == VirtualArea.AGENT and not segments:
            return dir_entry(AREA_AGENT)
        if area == VirtualArea.TEAM and not segments:
            return dir_entry(AREA_TEAM)

        permission = AgentPermission.READ if area == VirtualArea.AGENT else TeamPermission.CAN_READ
        target = await self._resolve_target(
            user,
            area,
            segments,
            read_permission=permission,
        )
        if not target.subpath:
            return dir_entry(target.visible_root.lstrip("/"))
        return await self.scoped_storage.stat(
            user,
            target.subpath,
            owner_override=target.owner_override,
            root_prefix=target.root_prefix,
        )

    async def cat_area(
        self,
        user: KeycloakUser,
        area: VirtualArea,
        segments: tuple[str, ...],
    ) -> str:
        """
        Read one file from a writable virtual area.

        Why this exists:
        - file reads need the same area routing as list/stat, but with stricter root checks
        - callers should not repeat the per-area validation rules

        How to use:
        - pass the resolved area plus a path that points to one file

        Example:
        - `await cat_area(user, VirtualArea.TEAM, ("t1", "notes.md"))`
        """

        self._ensure_supported_area(area)
        permission = AgentPermission.READ if area == VirtualArea.AGENT else TeamPermission.CAN_READ if area == VirtualArea.TEAM else None
        target = await self._resolve_target(
            user,
            area,
            segments,
            read_permission=permission,
        )
        if not target.subpath:
            raise FileNotFoundError(f"Cannot read {target.visible_root} as file")
        return await self.scoped_storage.get_text(
            user,
            target.subpath,
            owner_override=target.owner_override,
            root_prefix=target.root_prefix,
        )

    async def write_area(
        self,
        user: KeycloakUser,
        area: VirtualArea,
        segments: tuple[str, ...],
        data: str,
    ) -> None:
        """
        Write one file inside a writable virtual area.

        Why this exists:
        - write permission rules differ across workspace, agent, and team areas
        - callers should not duplicate the storage-target plumbing

        How to use:
        - pass the resolved area plus the file segments and text payload

        Example:
        - `await write_area(user, VirtualArea.WORKSPACE, ("notes.md",), "hello")`
        """

        self._ensure_supported_area(area)
        permission = AgentPermission.UPDATE if area == VirtualArea.AGENT else TeamPermission.CAN_UPDATE_RESOURCES if area == VirtualArea.TEAM else None
        target = await self._resolve_target(
            user,
            area,
            segments,
            write_permission=permission,
        )
        if not target.subpath:
            raise PermissionError(f"Cannot write to {target.visible_root} root")
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
        area: VirtualArea,
        segments: tuple[str, ...],
    ) -> None:
        """
        Delete one file or folder inside a writable virtual area.

        Why this exists:
        - delete permission rules differ across workspace, agent, and team areas
        - callers should not duplicate the storage-target plumbing

        How to use:
        - pass the resolved area plus the target path segments

        Example:
        - `await delete_area(user, VirtualArea.AGENT, ("a1", "cache.txt"))`
        """

        self._ensure_supported_area(area)
        permission = AgentPermission.DELETE if area == VirtualArea.AGENT else TeamPermission.CAN_UPDATE_RESOURCES if area == VirtualArea.TEAM else None
        target = await self._resolve_target(
            user,
            area,
            segments,
            write_permission=permission,
        )
        if not target.subpath:
            raise PermissionError(f"Cannot delete {target.visible_root} root")
        await self.scoped_storage.delete(
            user,
            target.subpath,
            owner_override=target.owner_override,
            root_prefix=target.root_prefix,
        )

    async def grep_area(
        self,
        user: KeycloakUser,
        area: VirtualArea,
        pattern: str,
        segments: tuple[str, ...],
    ) -> List[str]:
        """
        Search one writable virtual area and return visible absolute paths.

        Why this exists:
        - scoped storage returns relative hits
        - callers need stable visible paths that match manual browsing

        How to use:
        - pass the resolved area, regex pattern, and optional area-relative prefix

        Example:
        - `await grep_area(user, VirtualArea.WORKSPACE, "todo", ("notes",))`
        """

        self._ensure_supported_area(area)
        if area == VirtualArea.AGENT and not segments:
            matches: list[str] = []
            for agent_entry in await self._list_readable_agent_roots(user):
                matches.extend(
                    await self.grep_area(
                        user,
                        VirtualArea.AGENT,
                        pattern,
                        (agent_entry.path,),
                    )
                )
            return matches
        if area == VirtualArea.TEAM and not segments:
            matches = []
            for team_entry in await self._list_readable_team_roots(user):
                matches.extend(
                    await self.grep_area(
                        user,
                        VirtualArea.TEAM,
                        pattern,
                        (team_entry.path,),
                    )
                )
            return matches

        permission = AgentPermission.READ if area == VirtualArea.AGENT else TeamPermission.CAN_READ if area == VirtualArea.TEAM else None
        target = await self._resolve_target(
            user,
            area,
            segments,
            read_permission=permission,
        )
        return [
            self._visible_path(target, path)
            for path in await self.scoped_storage.grep(
                user,
                pattern,
                target.subpath,
                owner_override=target.owner_override,
                root_prefix=target.root_prefix,
            )
        ]

    async def mkdir_area(
        self,
        user: KeycloakUser,
        area: VirtualArea,
        segments: tuple[str, ...],
    ) -> None:
        """
        Create one directory inside a writable virtual area.

        Why this exists:
        - mkdir permission rules differ across workspace, agent, and team areas
        - callers should not duplicate the storage-target plumbing

        How to use:
        - pass the resolved area plus the target directory segments

        Example:
        - `await mkdir_area(user, VirtualArea.TEAM, ("team-1", "reports"))`
        """

        self._ensure_supported_area(area)
        permission = AgentPermission.UPDATE if area == VirtualArea.AGENT else TeamPermission.CAN_UPDATE_RESOURCES if area == VirtualArea.TEAM else None
        target = await self._resolve_target(
            user,
            area,
            segments,
            write_permission=permission,
        )
        if not target.subpath:
            raise PermissionError(f"Cannot create {target.visible_root} root")
        await self.scoped_storage.mkdir(
            user,
            target.subpath,
            owner_override=target.owner_override,
            root_prefix=target.root_prefix,
        )
