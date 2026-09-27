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

"""Contributed-name rules.

Moved to `fred_pod.common.naming` so a pod can read its configuration without installing the
agents platform. Re-exported here so existing imports keep working."""

from fred_pod.common.naming import (
    CONTRIBUTED_NAME_PATTERN,
    MAX_NAME_CHARS,
    PREFIX_PATTERN,
    InvalidContributedName,
    prefix_covers,
    require_contributed_name,
)

__all__ = [
    "CONTRIBUTED_NAME_PATTERN",
    "MAX_NAME_CHARS",
    "PREFIX_PATTERN",
    "InvalidContributedName",
    "prefix_covers",
    "require_contributed_name",
]
