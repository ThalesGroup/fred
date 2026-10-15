# SPDX-License-Identifier: Apache-2.0
import asyncio
import math
from collections.abc import Iterable
from uuid import UUID

from fastapi import HTTPException
from fred_core import KeycloackDisabled
from keycloak import KeycloakAdmin
from keycloak.exceptions import KeycloakGetError

from control_plane_backend.users.dependencies import UserServiceDependencies
from control_plane_backend.users.schemas import UserSummary

PAGE_SIZE = 200
MAX_SEARCH_MATCHES = 1000


def _human(raw: dict) -> bool:
    username = raw.get("username")
    if not (
        isinstance(raw.get("id"), str)
        and isinstance(username, str)
        and username.strip()
        and not username.startswith("service-account-")
        and not raw.get("serviceAccountClientId")
    ):
        return False
    try:
        UUID(raw["id"])
    except ValueError:
        return False
    return True


class PlatformAccessDirectory:
    def __init__(self, deps: UserServiceDependencies):
        self.local = deps.configuration.security.user_directory == "local"
        self._factory = deps.create_keycloak_admin_client
        self._admin: KeycloakAdmin | None = None

    def _client(self) -> KeycloakAdmin:
        if self._admin is None:
            try:
                client = self._factory()
            except Exception:
                raise HTTPException(
                    503, "platform_access_directory_unavailable"
                ) from None
            if isinstance(client, KeycloackDisabled):
                raise HTTPException(503, "platform_access_directory_unavailable")
            self._admin = client
        return self._admin

    async def search(self, query: str = "") -> list[UserSummary]:
        if self.local:
            raise ValueError(
                "Local directory search uses the SQL platform-access store"
            )
        admin = self._client()
        users: list[UserSummary] = []
        offset = 0
        try:
            while True:
                params: dict[str, str | int] = {"first": offset, "max": PAGE_SIZE}
                if query:
                    params["search"] = query
                page = await admin.a_get_users(params)
                users.extend(
                    UserSummary.from_raw_user(raw) for raw in page if _human(raw)
                )
                if len(page) < PAGE_SIZE:
                    return list({user.id: user for user in users}.values())
                offset += PAGE_SIZE
        except Exception:
            raise HTTPException(503, "platform_access_directory_unavailable") from None

    async def search_page(
        self, query: str, offset: int, limit: int
    ) -> tuple[list[UserSummary], int]:
        if self.local:
            raise ValueError(
                "Local directory search uses the SQL platform-access store"
            )
        try:
            user_id = str(UUID(query))
        except ValueError:
            pass
        else:
            profile = (await self.by_ids([user_id])).get(user_id)
            matches = [profile] if profile is not None else []
            return matches[offset : offset + limit], len(matches)
        admin = self._client()
        users: list[UserSummary] = []
        first = 0
        try:
            raw_total = int(await admin.a_users_count({"search": query}))
            if raw_total > MAX_SEARCH_MATCHES:
                for field in ("username", "email"):
                    exact = await admin.a_get_users(
                        {field: query, "exact": True, "first": 0, "max": PAGE_SIZE}
                    )
                    matches = [
                        UserSummary.from_raw_user(raw)
                        for raw in exact
                        if _human(raw)
                        and str(raw.get(field, "")).casefold() == query.casefold()
                    ]
                    if matches and len(exact) < PAGE_SIZE:
                        return matches[offset : offset + limit], len(matches)
                raise HTTPException(422, "platform_access_search_too_broad")
            while first < raw_total:
                page = await admin.a_get_users(
                    {"search": query, "first": first, "max": PAGE_SIZE}
                )
                users.extend(
                    UserSummary.from_raw_user(raw) for raw in page if _human(raw)
                )
                if not page:
                    break
                first += len(page)
            return users[offset : offset + limit], len(users)
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(503, "platform_access_directory_unavailable") from None

    async def by_ids(self, ids: Iterable[str]) -> dict[str, UserSummary]:
        if self.local:
            raise ValueError("Local identity lookup uses the SQL platform-access store")
        admin = self._client()
        wanted = set(ids)
        if not wanted:
            return {}
        if len(wanted) >= 20:
            try:
                total = int(await admin.a_users_count())
                if math.ceil(total / PAGE_SIZE) <= math.ceil(len(wanted) / 10):
                    scanned: dict[str, UserSummary] = {}
                    for first in range(0, total, PAGE_SIZE):
                        page = await admin.a_get_users(
                            {"first": first, "max": PAGE_SIZE}
                        )
                        for raw in page:
                            if _human(raw) and raw["id"] in wanted:
                                scanned[raw["id"]] = UserSummary.from_raw_user(raw)
                        if len(page) < PAGE_SIZE:
                            break
                    return scanned
            except Exception:
                raise HTTPException(
                    503, "platform_access_directory_unavailable"
                ) from None
        semaphore = asyncio.Semaphore(10)

        async def one(user_id: str) -> tuple[str, UserSummary | None]:
            async with semaphore:
                try:
                    raw = await admin.a_get_user(user_id)
                except KeycloakGetError as error:
                    if error.response_code == 404:
                        return user_id, None
                    raise HTTPException(
                        503, "platform_access_directory_unavailable"
                    ) from None
                except Exception:
                    raise HTTPException(
                        503, "platform_access_directory_unavailable"
                    ) from None
                return (
                    user_id,
                    UserSummary.from_raw_user(raw)
                    if isinstance(raw, dict) and _human(raw) and raw["id"] == user_id
                    else None,
                )

        found: dict[str, UserSummary] = {}
        ordered = list(wanted)
        for start in range(0, len(ordered), PAGE_SIZE):
            pairs = await asyncio.gather(
                *(one(user_id) for user_id in ordered[start : start + PAGE_SIZE])
            )
            found.update(
                (user_id, profile) for user_id, profile in pairs if profile is not None
            )
        return found

    @staticmethod
    def uuid(profile: UserSummary) -> UUID:
        try:
            return UUID(profile.id)
        except ValueError:
            raise HTTPException(503, "platform_access_directory_unavailable") from None
