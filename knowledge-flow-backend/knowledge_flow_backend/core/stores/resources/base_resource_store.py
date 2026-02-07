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

from abc import ABC, abstractmethod
from typing import List

from knowledge_flow_backend.features.resources.structures import Resource, ResourceKind


class ResourceNotFoundError(Exception):
    """Raised when a resource is not found."""

    pass


class ResourceAlreadyExistsError(Exception):
    """Raised when trying to create a resource that already exists."""

    pass


class BaseResourceStore(ABC):
    """
    Abstract base class for storing and retrieving resources, user-scoped.

    Exceptions:
        - list_resources_for_user: should not raise
        - get_resource_by_id: ResourceNotFoundError if not found
        - create_resource: ResourceAlreadyExistsError if already exists
        - update_resource: ResourceNotFoundError if not found
        - delete_resource: ResourceNotFoundError if not found
    """

    @abstractmethod
    async def get_all_resources(self, kind: ResourceKind) -> list[Resource]:
        pass

    @abstractmethod
    async def get_resource_by_id(self, resource_id: str) -> Resource:
        pass

    @abstractmethod
    async def create_resource(self, resource: Resource) -> Resource:
        pass

    @abstractmethod
    async def update_resource(self, resource_id: str, resource: Resource) -> Resource:
        pass

    @abstractmethod
    async def delete_resource(self, resource_id: str) -> None:
        pass

    @abstractmethod
    async def get_resources_in_tag(self, tag_id: str) -> List[Resource]:
        """
        Retrieve all resources associated with a specific tag.
        Raises:
            ResourceNotFoundError: If no resources are found for the tag.
        """
        pass
