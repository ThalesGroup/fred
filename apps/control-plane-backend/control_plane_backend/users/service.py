from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from fred_core import Action, BaseUserStore, KeycloakUser, Resource, authorize
from fred_core.sql import make_session_factory, use_session
from fred_core.users import GcuVersionsType, UserRow
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from control_plane_backend.users.dependencies import UserServiceDependencies
from control_plane_backend.users.schemas import (
    CreateUserRequest,
    UserAlreadyExistsError,
    UserNotFoundError,
    UserSummary,
)

logger = logging.getLogger(__name__)


@authorize(Action.READ, Resource.USER)
async def list_users(
    _current_user: KeycloakUser,
    deps: UserServiceDependencies,
) -> list[UserSummary]:
    sessions = make_session_factory(deps.db)
    async with use_session(sessions) as s:
        rows = (await s.execute(select(UserRow))).scalars().all()
    return [_to_summary(row) for row in rows]


@authorize(Action.CREATE, Resource.USER)
async def create_user(
    _current_user: KeycloakUser,
    request: CreateUserRequest,
    deps: UserServiceDependencies,
) -> UserSummary:
    row = UserRow(
        id=uuid4(),
        username=request.username,
        email=request.email,
        first_name=request.first_name,
        last_name=request.last_name,
        enabled=request.enabled,
    )
    sessions = make_session_factory(deps.db)
    try:
        async with use_session(sessions) as s:
            s.add(row)
    except IntegrityError as exc:
        raise UserAlreadyExistsError(request.username) from exc
    return _to_summary(row)


@authorize(Action.DELETE, Resource.USER)
async def delete_user(
    _current_user: KeycloakUser,
    user_id: str,
    deps: UserServiceDependencies,
) -> None:
    try:
        uid = UUID(user_id)
    except ValueError:
        raise UserNotFoundError(user_id)
    sessions = make_session_factory(deps.db)
    async with use_session(sessions) as s:
        result = await s.execute(delete(UserRow).where(UserRow.id == uid))
    if result.rowcount == 0:
        raise UserNotFoundError(user_id)


async def get_user_by_id(
    user_id: str,
    deps: UserServiceDependencies,
) -> UserSummary:
    try:
        uid = UUID(user_id)
    except ValueError:
        raise UserNotFoundError(user_id)
    sessions = make_session_factory(deps.db)
    async with use_session(sessions) as s:
        row = await s.get(UserRow, uid)
    if row is None:
        raise UserNotFoundError(user_id)
    return _to_summary(row)


async def get_users_by_ids(
    user_ids: Iterable[str],
    deps: UserServiceDependencies,
) -> dict[str, UserSummary]:
    unique_ids = {uid for uid in user_ids if uid}
    if not unique_ids:
        return {}

    uuid_map: dict[str, UUID] = {}
    for uid in unique_ids:
        try:
            uuid_map[uid] = UUID(uid)
        except ValueError:
            logger.debug("Skipping non-UUID user id: %s", uid)

    sessions = make_session_factory(deps.db)
    async with use_session(sessions) as s:
        rows = (
            await s.execute(select(UserRow).where(UserRow.id.in_(uuid_map.values())))
        ).scalars().all()

    found = {str(row.id): _to_summary(row) for row in rows}
    for uid in unique_ids:
        if uid not in found:
            found[uid] = UserSummary(id=uid)
    return found


def _to_summary(row: UserRow) -> UserSummary:
    return UserSummary(
        id=str(row.id),
        username=row.username,
        email=row.email,
        first_name=row.first_name,
        last_name=row.last_name,
    )


async def upsert_user_from_jwt(
    user: KeycloakUser,
    deps: UserServiceDependencies,
) -> None:
    try:
        user_uuid = UUID(user.uid)
    except ValueError:
        logger.debug("Non-UUID subject %r — skipping user upsert", user.uid)
        return
    email = user.email or f"{user.uid}@unknown"
    sessions = make_session_factory(deps.db)
    async with use_session(sessions) as s:
        stmt = (
            pg_insert(UserRow)
            .values(
                id=user_uuid,
                username=user.username,
                email=email,
                first_name=user.first_name,
                last_name=user.last_name,
                enabled=True,
                created_at=datetime.now(tz=timezone.utc),
            )
            .on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "username": user.username,
                    "email": email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                },
            )
        )
        await s.execute(stmt)


async def find_user_details_by_id(
    user_id: UUID,
    user_store: BaseUserStore,
) -> Optional[UserRow]:
    return await user_store.find_user_by_id(user_id)


async def update_gcu_validation(
    user_id: UUID,
    user_store: BaseUserStore,
    deps: UserServiceDependencies,
) -> None:
    cfg = deps.configuration
    if cfg.app.gcu_version is None:
        return
    await user_store.update_gcu_version(user_id, GcuVersionsType(cfg.app.gcu_version))
