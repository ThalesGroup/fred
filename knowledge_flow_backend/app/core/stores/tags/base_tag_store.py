from abc import ABC, abstractmethod
from typing import List
from app.features.tag.structure import Tag
from fred_core import KeycloakUser


class TagNotFoundError(Exception):
    """Raised when a tag is not found."""

    pass


class TagAlreadyExistsError(Exception):
    """Raised when trying to create a tag that already exists."""

    pass


class BaseTagStore(ABC):
    """
    Abstract base class for storing and retrieving tags, user-scoped.

    Exceptions:
        - list_tags_for_user: (should not throw)
        - get_tag_by_id: TagNotFoundError if tag does not exist
        - create_tag: TagAlreadyExistsError if tag already exists
        - update_tag_by_id: TagNotFoundError if tag does not exist
        - delete_tag_by_id: TagNotFoundError if tag does not exist
    """

    @abstractmethod
    def list_tags_for_user(self, user: KeycloakUser) -> List[Tag]:
        pass

    @abstractmethod
    def get_tag_by_id(self, tag_id: str) -> Tag:
        pass

    @abstractmethod
    def create_tag(self, tag: Tag) -> Tag:
        pass

    @abstractmethod
    def update_tag_by_id(self, tag_id: str, tag: Tag) -> Tag:
        pass

    @abstractmethod
    def delete_tag_by_id(self, tag_id: str) -> None:
        pass
