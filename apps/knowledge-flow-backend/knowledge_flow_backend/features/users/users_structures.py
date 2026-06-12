from __future__ import annotations

from pydantic import BaseModel


class UserSummary(BaseModel):
    id: str
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
