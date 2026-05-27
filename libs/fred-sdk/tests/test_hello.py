"""Tests for the hello-world SDK surface."""

from fred_sdk.hello import hello_message


def test_hello_message_defaults_to_world() -> None:
    """Verify the hello-world API returns the default greeting.

    Why: Guard the public SDK contract for callers who omit a name.
    How: Call the function with an empty value and compare the output.
    """

    assert hello_message(None) == "Hello, world!"


def test_hello_message_trims_name() -> None:
    """Verify the hello-world API trims whitespace in the name.

    Why: Keep greetings predictable for agent authors passing user input.
    How: Provide a name with extra whitespace and compare the output.
    """

    assert hello_message("  Ada  ") == "Hello, Ada!"
