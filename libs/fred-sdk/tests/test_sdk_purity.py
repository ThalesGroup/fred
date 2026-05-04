# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0

"""
Guard that importing fred_sdk never pulls in forbidden runtime dependencies.

Run on every `make test`. Add to _FORBIDDEN any library that must never be a
transitive dependency of the authoring SDK.
"""

import sys

_FORBIDDEN = frozenset(
    {
        "langfuse",
        "sqlalchemy",
        "asyncpg",
        "fred_runtime",
        "agentic_backend",
        "psycopg2",
        "celery",
    }
)


def test_no_forbidden_transitive_imports() -> None:
    mods_before = set(sys.modules)
    import fred_sdk  # noqa: F401

    new_top_level = {k.split(".")[0] for k in sys.modules if k not in mods_before}
    violations = new_top_level & _FORBIDDEN
    assert not violations, (
        f"fred_sdk transitively imported forbidden modules: {sorted(violations)}"
    )
