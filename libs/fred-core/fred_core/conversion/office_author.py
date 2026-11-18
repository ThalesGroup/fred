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

"""Select the embedded author of a generated Office file."""

from typing import Protocol

from fred_pod.security.structure import KeycloakUser


class OfficeCoreProperties(Protocol):
    @property
    def author(self) -> str: ...

    @author.setter
    def author(self, value: str) -> None: ...

    @property
    def last_modified_by(self) -> str: ...

    @last_modified_by.setter
    def last_modified_by(self, value: str) -> None: ...


def office_author_name(user: KeycloakUser | None, fallback_user_id: str) -> str:
    """Use a complete profile name, then username, then the verified user ID."""
    if user is not None:
        first_name = (user.first_name or "").strip()
        last_name = (user.last_name or "").strip()
        if first_name and last_name:
            return f"{first_name} {last_name}"[:255]
        if user.username.strip():
            return user.username[:255]
    return fallback_user_id[:255]


def set_office_author(
    properties: OfficeCoreProperties, author: KeycloakUser | str
) -> None:
    """Set the same bounded author on Word and PowerPoint core properties."""
    if isinstance(author, KeycloakUser):
        name = office_author_name(author, author.uid)
    else:
        name = office_author_name(None, author)
    properties.author = name
    properties.last_modified_by = name
