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

from app.features.prompts.structure import Prompt


class PromptNotFoundError(Exception):
    """Raised when a prompt is not found."""
    pass


class PromptAlreadyExistsError(Exception):
    """Raised when trying to create a prompt that already exists."""
    pass


class BasePromptStore(ABC):
    """
    Abstract base class for storing and retrieving prompts, user-scoped.

    Exceptions:
        - list_prompts_for_user: should not raise
        - get_prompt_by_id: PromptNotFoundError if not found
        - create_prompt: PromptAlreadyExistsError if already exists
        - update_prompt: PromptNotFoundError if not found
        - delete_prompt: PromptNotFoundError if not found
    """

    @abstractmethod
    def list_prompts_for_user(self, user: str) -> List[Prompt]:
        pass

    @abstractmethod
    def get_prompt_by_id(self, prompt_id: str) -> Prompt:
        pass

    @abstractmethod
    def create_prompt(self, prompt: Prompt) -> Prompt:
        pass

    @abstractmethod
    def update_prompt(self, prompt_id: str, prompt: Prompt) -> Prompt:
        pass

    @abstractmethod
    def delete_prompt(self, prompt_id: str) -> None:
        pass

    @abstractmethod
    def get_prompt_in_tag(self, tag_id: str) -> List[Prompt]:
        """
        Retrieve all prompts associated with a specific tag.
        Raises:
            PromptNotFoundError: If no prompts are found for the tag.
        """
        pass
