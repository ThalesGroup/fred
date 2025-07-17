# Copyright Thales 2025
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

from pathlib import Path
from typing import List
from app.core.stores.tags.base_tag_store import BaseTagStore, TagNotFoundError, TagAlreadyExistsError
from app.features.tag.structure import Tag
from fred_core import KeycloakUser
from fred_core import LocalJsonStore, ResourceNotFoundError, ResourceAlreadyExistsError


class LocalTagStore(BaseTagStore):
    """
    A simple file-based tag store implementation that persists tags in a local JSON file.
    Tags are user-scoped: each tag is associated with a user (by user.uid).
    Raises TagNotFoundError if a tag is not found, TagAlreadyExistsError if a tag already exists (see BaseTagStore for details).
    """

    def __init__(self, json_path: Path):
        self._store = LocalJsonStore(json_path, id_field="id", model=Tag)

    def list_tags_for_user(self, user: KeycloakUser) -> List[Tag]:
        return self._store.list(filter_fn=lambda item: item.owner_id == user.uid)

    def get_tag_by_id(self, tag_id: str) -> Tag:
        try:
            return self._store.get_by_id(tag_id)
        except ResourceNotFoundError as e:
            raise TagNotFoundError(str(e)) from e

    def create_tag(self, tag: Tag) -> Tag:
        try:
            return self._store.create(tag)
        except ResourceAlreadyExistsError as e:
            raise TagAlreadyExistsError(str(e)) from e

    def update_tag_by_id(self, tag_id: str, tag: Tag) -> Tag:
        try:
            return self._store.update(tag_id, tag)
        except ResourceNotFoundError as e:
            raise TagNotFoundError(str(e)) from e

    def delete_tag_by_id(self, tag_id: str) -> None:
        try:
            self._store.delete(tag_id)
        except ResourceNotFoundError as e:
            raise TagNotFoundError(str(e)) from e
