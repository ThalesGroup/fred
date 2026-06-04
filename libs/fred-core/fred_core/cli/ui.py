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

import os
import sys
from collections.abc import Callable, Sequence

try:
    import readline
except ImportError:  # pragma: no cover - readline is available on Linux/macOS only.
    readline = None

ANSI_RESET = "\033[0m"
ANSI_BOLD = "\033[1m"
ANSI_CYAN = "\033[36m"
ANSI_GREEN = "\033[32m"
ANSI_RED = "\033[31m"
ANSI_YELLOW = "\033[33m"
ANSI_DIM = "\033[2m"
ANSI_WHITE = "\033[97m"


def colors_enabled(*, no_color: bool) -> bool:
    """
    Decide whether ANSI terminal colors should be used.

    Why this function exists:
    - Fred CLIs should look consistent without forcing ANSI escapes into pipes
      or logs
    - keeping the policy here makes all consoles honor the same `NO_COLOR`
      behavior and `--no-color` flag

    How to use it:
    - pass the parsed CLI `--no-color` flag

    Example:
    - `enabled = colors_enabled(no_color=False)`
    """

    if no_color or os.getenv("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def colorize(text: str, *, color: str, enabled: bool, bold: bool = False) -> str:
    """
    Wrap a string in ANSI escape codes when terminal colors are enabled.

    Why this function exists:
    - Fred CLIs need a tiny shared styling helper without depending on a full
      TUI library

    How to use it:
    - pass one of the exported `ANSI_*` constants and the current color flag

    Example:
    - `label = colorize("fredlab", color=ANSI_GREEN, enabled=True, bold=True)`
    """

    if not enabled:
        return text
    prefix = f"{ANSI_BOLD if bold else ''}{color}"
    return f"{prefix}{text}{ANSI_RESET}"


def complete_slash_commands(
    line_buffer: str,
    *,
    commands: Sequence[str],
) -> list[str]:
    """
    Return command-name completions for one slash-command prompt prefix.

    Why this function exists:
    - Fred CLIs use slash commands across backends and should autocomplete them
      consistently

    How to use it:
    - call after backend-specific argument completion checks
    - pass the CLI command list including the leading `/`

    Example:
    - `matches = complete_slash_commands("/te", commands=("/team", "/teams"))`
    """

    stripped = line_buffer.lstrip()
    if not stripped.startswith("/"):
        return []
    return [command for command in commands if command.startswith(stripped)]


def install_readline_completion(
    candidates_provider: Callable[[str], Sequence[str]],
) -> None:
    """
    Enable tab completion using one line-buffer-aware candidate provider.

    Why this function exists:
    - all Fred CLIs should get the same dependency-free readline completion
      behavior on developer terminals
    - backend-specific CLIs can keep their own completion logic while reusing
      the same readline plumbing

    How to use it:
    - call once before entering an interactive REPL
    - provide a callable that accepts the current prompt line and returns
      completion candidates

    Example:
    - `install_readline_completion(lambda line: ["/help"] if line.startswith("/") else [])`
    """

    if readline is None:
        return

    def _complete(text: str, state: int) -> str | None:
        """
        Resolve the nth readline completion candidate for the active prompt.

        Why this function exists:
        - readline asks for one completion entry at a time by index
        - keeping the adapter nested avoids leaking TTY details to the caller

        How to use it:
        - called automatically by readline after `install_readline_completion`

        Example:
        - `candidate = _complete("te", 0)`
        """

        line_buffer = readline.get_line_buffer() if readline is not None else text
        matches = list(candidates_provider(line_buffer))
        if state >= len(matches):
            return None
        return matches[state]

    readline.set_completer_delims(" \t\n")
    readline.set_completer(_complete)
    readline.parse_and_bind("tab: complete")
