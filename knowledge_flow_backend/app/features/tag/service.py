from typing import List

from app.features.tag.structure import TagModel
from app.security.keycloak import KeycloakUser


class TagAuthorizationError(Exception):
    """Raised when a user is not authorized to perform a tag operation."""

    pass


class TagNotFoundError(Exception):
    """Raised when a tag is not found."""

    pass


class TagService:
    """
    Service for Tag resource CRUD operations, user-scoped.
    """

    def list_tags_for_user(self, user: KeycloakUser) -> List[TagModel]:
        raise TagAuthorizationError()

    def get_tag_for_user(self, tag_id: str, user: KeycloakUser) -> TagModel:
        raise TagNotFoundError()

    def create_tag_for_user(self, tag: TagModel, user: KeycloakUser) -> TagModel:
        raise TagAuthorizationError()

    def update_tag_for_user(self, tag_id: str, tag: TagModel, user: KeycloakUser) -> TagModel:
        raise TagNotFoundError()

    def delete_tag_for_user(self, tag_id: str, user: KeycloakUser) -> None:
        raise TagNotFoundError()
