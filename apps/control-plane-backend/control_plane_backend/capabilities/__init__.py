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
Per-team agent-capability scoping (CAPAB-01 / #1980, RFC AGENT-CAPABILITY §8).

Splits enablement into the two halves the RFC mandates:
- **authorization** — OpenFGA `capability` type tuples (`enabled` / `disabled` /
  `default_on`), checked as `can_use` / `can_manage`;
- **configuration** — the `team_capability_settings` table.

The enablement service enforces the write ordering (settings row THEN tuple) and
wires the revocation → suspension seam (#1975).
"""
