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

"""Deterministic RAG self-test agent (VALID-02).

Retrieves from the per-turn selected libraries through the real knowledge-search
tool and echoes the retrieved chunks verbatim — no LLM — so the admin self-test
page can assert that a marker phrase was retrieved end-to-end through the real
execution pipeline. See docs/swift/rfc/ADMIN-SELF-TEST-HARNESS-RFC.md (Amendment A).
"""

from fred_agents.self_test.graph_agent import SELF_TEST_AGENT

__all__ = ["SELF_TEST_AGENT"]
