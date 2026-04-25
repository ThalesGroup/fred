"""Shared CLI helpers for Fred developer/operator consoles.

Why this package exists:
- multiple Fred backends need the same terminal ergonomics around auth,
  configuration bootstrap, ANSI styling, and readline completion
- keeping those helpers here avoids backend-specific copy/paste while
  preserving the rule that runtime-only behavior stays out of `fred-core`

How to use it:
- import auth/bootstrap helpers from `fred_core.cli.auth`
- import color and completion helpers from `fred_core.cli.ui`

Example:
- `from fred_core.cli.auth import load_cli_environment`
- `from fred_core.cli.ui import colorize`
"""
