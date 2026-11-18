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

from fred_core.common.utils import user_display_name
from fred_pod.security.structure import KeycloakUser


class OfficeCoreProperties(Protocol):
    @property
    def author(self) -> str:
        raise NotImplementedError

    @author.setter
    def author(self, value: str) -> None:
        raise NotImplementedError

    @property
    def last_modified_by(self) -> str:
        raise NotImplementedError

    @last_modified_by.setter
    def last_modified_by(self, value: str) -> None:
        raise NotImplementedError


def set_office_author(
    properties: OfficeCoreProperties, author: KeycloakUser | str
) -> None:
    """Set the same bounded author on Word and PowerPoint core properties."""
    if isinstance(author, KeycloakUser):
        name = user_display_name(author, author.uid)
    else:
        name = author
    name = name[:255]
    properties.author = name
    properties.last_modified_by = name
