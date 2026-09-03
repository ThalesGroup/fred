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

"""Admin-ops capability family: platform introspection tools for Fred admins.

One subpackage per concern, each registered as its own `fred.capabilities`
entry point in `pyproject.toml` (`postgres/` → `platform_postgres`). Shared
connection clients/config helpers for future Tier A concerns would live here,
once; Tier B concerns (like `platform_postgres`) keep the credentialed
executor OUT of this package entirely — see
`docs/swift/rfc/ADMIN-OPS-AGENTS-RFC.md` §2.
"""
