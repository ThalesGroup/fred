from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel


class UserSummary(BaseModel):
    id: str
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None

    @classmethod
    def from_raw_user(cls, raw_user: Dict[str, Any]) -> "UserSummary":
        user_id = raw_user.get("id")
        if not user_id:
            raise ValueError("Cannot build UserSummary without an 'id'.")

        def _sanitize(value: object) -> str | None:
            if value is None:
                return None
            text = str(value).strip()
            return text or None

        return cls(
            id=user_id,
            first_name=_sanitize(raw_user.get("firstName")),
            last_name=_sanitize(raw_user.get("lastName")),
            username=_sanitize(raw_user.get("username")),
        )
