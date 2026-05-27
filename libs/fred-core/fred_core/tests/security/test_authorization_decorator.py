from __future__ import annotations

import pytest

import fred_core.security.authorization_decorator as authorization_decorator
from fred_core.security.models import Action, AuthorizationError, Resource
from fred_core.security.structure import KeycloakUser


def _admin_user() -> KeycloakUser:
    """Return one admin user for decorator authorization tests."""

    return KeycloakUser(
        uid="admin-1",
        username="admin",
        roles=["admin"],
        email="admin@test.com",
    )


def _viewer_user() -> KeycloakUser:
    """Return one non-admin viewer user for decorator denial tests."""

    return KeycloakUser(
        uid="viewer-1",
        username="viewer",
        roles=["viewer"],
        email="viewer@test.com",
    )


class _DocumentService:
    @authorization_decorator.authorize(Action.READ, Resource.DOCUMENTS)
    def read_document(self, user: KeycloakUser, document_id: str) -> str:
        """Return the requested document id once authorization succeeds."""

        return document_id

    @authorization_decorator.authorize(Action.UPDATE, Resource.TAGS)
    def update_tag(self, *, user: KeycloakUser, tag_id: str) -> str:
        """Return the updated tag id once authorization succeeds."""

        return tag_id

    @authorization_decorator.authorize(Action.READ, Resource.DOCUMENTS)
    def broken_read(self, document_id: str) -> str:
        """Intentionally omit the user parameter to exercise the guard rail."""

        return document_id


def test_authorize_decorator_checks_positional_user_and_preserves_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Authorize decorated methods when the user is supplied positionally."""

    calls: list[tuple[KeycloakUser, Action, Resource]] = []

    def fake_authorize_or_raise(
        user: KeycloakUser,
        action: Action,
        resource: Resource,
    ) -> None:
        calls.append((user, action, resource))

    monkeypatch.setattr(
        authorization_decorator,
        "authorize_or_raise",
        fake_authorize_or_raise,
    )

    service = _DocumentService()
    user = _admin_user()

    assert service.read_document(user, "doc-123") == "doc-123"
    assert service.read_document.__name__ == "read_document"
    assert calls == [(user, Action.READ, Resource.DOCUMENTS)]


def test_authorize_decorator_checks_keyword_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Authorize decorated methods when the user is supplied by keyword."""

    calls: list[tuple[KeycloakUser, Action, Resource]] = []

    def fake_authorize_or_raise(
        user: KeycloakUser,
        action: Action,
        resource: Resource,
    ) -> None:
        calls.append((user, action, resource))

    monkeypatch.setattr(
        authorization_decorator,
        "authorize_or_raise",
        fake_authorize_or_raise,
    )

    service = _DocumentService()
    user = _admin_user()

    assert service.update_tag(user=user, tag_id="tag-123") == "tag-123"
    assert calls == [(user, Action.UPDATE, Resource.TAGS)]


def test_authorize_decorator_bubbles_authorization_error() -> None:
    """Raise AuthorizationError when the wrapped call is not authorized."""

    service = _DocumentService()

    with pytest.raises(AuthorizationError):
        service.update_tag(user=_viewer_user(), tag_id="tag-123")


def test_authorize_decorator_requires_user_parameter() -> None:
    """Raise ValueError when a decorated method exposes no user parameter."""

    service = _DocumentService()

    with pytest.raises(ValueError, match="must have a 'user: KeycloakUser' parameter"):
        service.broken_read("doc-123")
