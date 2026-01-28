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
from collections.abc import Iterable

from knowledge_flow_backend.features.groups.groups_structures import GroupProfile


class BaseGroupStore(ABC):
    """
    Abstract base class for storing and retrieving group profiles.
    """

    @abstractmethod
    def get_group_profile(self, group_id: str) -> GroupProfile | None:
        pass

    @abstractmethod
    def list_group_profiles(self, group_ids: Iterable[str]) -> dict[str, GroupProfile]:
        pass
