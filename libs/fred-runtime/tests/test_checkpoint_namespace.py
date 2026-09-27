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

from fred_runtime.runtime_support.checkpoints import checkpoint_namespace


def test_checkpoint_namespace_prefers_agent_instance_id() -> None:
    assert (
        checkpoint_namespace(
            agent_instance_id="instance-123",
            agent_id="agent.template",
        )
        == "instance-123"
    )


def test_checkpoint_namespace_falls_back_to_agent_id() -> None:
    assert (
        checkpoint_namespace(
            agent_instance_id=None,
            agent_id="agent.template",
        )
        == "agent.template"
    )
