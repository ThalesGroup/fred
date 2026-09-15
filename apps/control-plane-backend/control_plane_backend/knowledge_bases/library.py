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

"""
The library a synchronized folder fills, created through knowledge-flow's own
folder path.

Not created by hand. Going through the same endpoint a person's folder creation
goes through is what makes a synchronized folder an ordinary folder in every
other respect — the same team-level right is required to make one, the same
cascade takes its documents when it is deleted, and permission over it reaches
everything nested inside it. A second creation path here would be a second set
of rules to keep in step.

The acting user's own token is forwarded, so the right to create a folder in
this team is checked where it always is, against the person asking.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(15.0)


class LibraryRequestFailed(Exception):
    """knowledge-flow refused or could not serve a library operation."""

    def __init__(self, message: str, *, http_status: int = 502) -> None:
        super().__init__(message)
        self.message = message
        self.http_status = http_status


class LibraryClient:
    """Create and delete a team's library, as the user asking for it."""

    def __init__(self, base_url: str, authorization: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._authorization = authorization

    async def create(self, *, name: str, team_id: str, description: str) -> str:
        """Create a top-level folder owned by the team, and return its id."""
        payload = await self._request(
            "POST",
            "/tags",
            json={
                "name": name,
                "path": None,
                "description": description,
                "type": "document",
                "team_id": team_id,
            },
        )
        library_id = payload.get("id")
        if not library_id:
            raise LibraryRequestFailed("knowledge-flow returned a folder with no id")
        return str(library_id)

    async def delete(self, library_id: str) -> None:
        """Delete the folder and, through its own cascade, its documents.

        A folder already gone is not an error: this runs on the undo path of a
        creation that failed halfway, where "it was never created" and "it is
        deleted" are the same outcome.
        """
        try:
            await self._request("DELETE", f"/tags/{library_id}")
        except LibraryRequestFailed as exc:
            if exc.http_status == 404:
                logger.info("[knowledge-base] library %s was already gone", library_id)
                return
            raise

    async def _request(
        self, method: str, path: str, json: object | None = None
    ) -> dict:
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.request(
                    method,
                    f"{self._base_url}{path}",
                    json=json,
                    headers={"Authorization": self._authorization},
                )
        except httpx.RequestError as exc:
            raise LibraryRequestFailed(f"knowledge-flow is unreachable: {exc}") from exc
        if response.status_code >= 400:
            # The status is carried through, so a team-level refusal reaches the
            # caller as a refusal and not as a platform fault.
            raise LibraryRequestFailed(
                f"knowledge-flow refused {method} {path}: {response.status_code}",
                http_status=response.status_code,
            )
        if not response.content:
            return {}
        return response.json()
