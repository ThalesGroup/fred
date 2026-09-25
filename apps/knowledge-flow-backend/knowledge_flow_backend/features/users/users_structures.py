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
