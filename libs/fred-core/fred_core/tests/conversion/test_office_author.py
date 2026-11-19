from fred_core.common.utils import user_display_name
from fred_core.conversion.office_author import set_office_author
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


def test_user_display_name_prefers_complete_trimmed_name() -> None:
    assert (
        user_display_name(_user(first_name=" Élodie ", last_name=" D<& "), "user-id")
        == "Élodie D<&"
    )


def test_user_display_name_falls_back_to_username_then_id() -> None:
    assert (
        user_display_name(_user(first_name=" ", last_name=" Smith"), "user-id") == "u"
    )
    assert user_display_name(_user(username=" "), "user-id") == "user-id"
    assert user_display_name(None, "user-id") == "user-id"


def test_office_author_limits_all_sources_to_255_characters() -> None:
    class Properties:
        author = ""
        last_modified_by = ""

    properties = Properties()
    set_office_author(properties, _user(first_name="a" * 250, last_name="Smith"))
    assert properties.author == "a" * 250 + " Smit"
    assert properties.last_modified_by == properties.author

    set_office_author(properties, _user(username="a" * 256))
    assert properties.author == "a" * 255

    set_office_author(properties, "a" * 256)
    assert properties.author == "a" * 255


def test_office_author_clears_unverified_names_instead_of_using_subject_id() -> None:
    class Properties:
        author = "Template author"
        last_modified_by = "Template author"

    properties = Properties()
    set_office_author(properties, _user(username=" "))
    assert properties.author == properties.last_modified_by == ""
