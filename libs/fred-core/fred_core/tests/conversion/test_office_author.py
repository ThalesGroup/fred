from fred_core.conversion.office_author import office_author_name
from fred_pod.security.structure import KeycloakUser


def _user(
    *, first_name: str | None = None, last_name: str | None = None, username: str = "u"
) -> KeycloakUser:
    return KeycloakUser(
        uid="user-id",
        username=username,
        roles=[],
        first_name=first_name,
        last_name=last_name,
    )


def test_office_author_prefers_complete_trimmed_name() -> None:
    assert (
        office_author_name(_user(first_name=" Élodie ", last_name=" D<& "), "user-id")
        == "Élodie D<&"
    )


def test_office_author_falls_back_to_username_then_id() -> None:
    assert (
        office_author_name(_user(first_name=" ", last_name=" Smith"), "user-id") == "u"
    )
    assert office_author_name(_user(username=" "), "user-id") == "user-id"
    assert office_author_name(None, "user-id") == "user-id"


def test_office_author_limits_all_sources_to_255_characters() -> None:
    assert office_author_name(_user(first_name="a" * 250, last_name="Smith"), "id") == (
        "a" * 250 + " Smit"
    )
    assert office_author_name(_user(username="a" * 256), "id") == "a" * 255
    assert office_author_name(None, "a" * 256) == "a" * 255
