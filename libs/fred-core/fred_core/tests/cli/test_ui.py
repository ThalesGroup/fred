# Copyright Thales 2026
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
