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
The namespace Fred keeps for itself in an instance's configuration.

Recurrence used to be declared here as a `FieldSpec`, so a form rendered it
generically and then had to fish the value back out by key. It is Fred's own,
typed in Fred's own API — `schedule` and `suspended` on the instance schemas —
so nothing generic is involved and no key has to travel beside the fields.

What remains is the guard: an author may not declare a field under `fred.`,
because that is where Fred's own would collide with theirs.
"""

from __future__ import annotations

# Every key Fred owns in an instance's configuration sits under this one
# segment, so what belongs to the platform and what belongs to the author are
# told apart by reading a key rather than by consulting a list.
FRED_FIELD_NAMESPACE = "fred"
FRED_FIELD_PREFIX = f"{FRED_FIELD_NAMESPACE}."


def is_platform_field(key: str) -> bool:
    """Whether this configuration key belongs to Fred rather than to the author."""
    return key == FRED_FIELD_NAMESPACE or key.startswith(FRED_FIELD_PREFIX)


__all__ = ["FRED_FIELD_NAMESPACE", "FRED_FIELD_PREFIX", "is_platform_field"]
