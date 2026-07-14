# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License").

"""
Offline unit tests for the validation harness itself (factory_config.py,
conftest.py helpers) - no running stack required.

Deliberately isolated from `validation/scenarios/`: the parent
`validation/conftest.py` has two autouse, session-scoped fixtures that talk to
a live stack - `_require_stack` (fails fast if the control-plane is
unreachable) and `_bootstrap_collaborative_teams` (logs in as the platform
admin and calls the control-plane team APIs) - because every scenario under
`scenarios/` is a black-box test against a live Fred platform. These tests are
not that - they exercise pure Python (YAML parsing, role resolution) - so this
conftest.py overrides both as no-ops for everything collected under
`validation/tests/` (a closer conftest.py's fixture shadows an ancestor's
fixture of the same name; this is the standard pytest override mechanism, not
a workaround).

`../factory_config.py` is imported directly (not installed), so `validation/`
is added to `sys.path` here the same way pytest's own rootdir insertion would
for a file colocated with conftest.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(scope="session", autouse=True)
def _require_stack() -> None:
    """Override: these are offline unit tests, no live stack is needed."""
    return None


@pytest.fixture(scope="session", autouse=True)
def _bootstrap_collaborative_teams() -> None:
    """Override: no control-plane to bootstrap teams against in offline unit tests."""
    return None
