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
