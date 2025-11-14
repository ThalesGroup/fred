from __future__ import annotations

from openfga_sdk.models.user import User


class ListUsersResponse:
    users: list[User]

    def __init__(
        self,
        users: list[User],
    ) -> None: ...
