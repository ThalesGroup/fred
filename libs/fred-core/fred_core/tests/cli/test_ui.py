from __future__ import annotations

from fred_core.cli.ui import complete_slash_commands


def test_complete_slash_commands_filters_matching_commands() -> None:
    """
    Verify the shared slash-command completer keeps only matching entries.

    Why this test exists:
    - Fred CLIs should autocomplete slash commands consistently across
      backends

    How to use it:
    - run with the default offline `fred-core` test suite

    Example:
    - `pytest fred_core/tests/cli/test_ui.py -q`
    """

    matches = complete_slash_commands(
        "/te",
        commands=("/teams", "/team", "/templates", "/help"),
    )

    assert matches == ["/teams", "/team", "/templates"]
