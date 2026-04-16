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
Standalone Fred agent pod package.

Why this package exists:
- it hosts runnable agent definitions outside `agentic-backend`
- it exercises the public `fred-sdk` and `fred-runtime` surfaces directly

How to use it:
- import `create_app()` from `fred_agents.main` for the ASGI application
- import `REGISTRY` from `fred_agents.agents` to inspect registered agents

Example:
- `from fred_agents.main import app`
"""
