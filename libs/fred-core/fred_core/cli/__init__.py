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
