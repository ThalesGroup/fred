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

from typing import cast

from fred_runtime.integrations.v2_runtime.adapters import LangfuseTracerAdapter
from fred_runtime.runtime_support import (
    get_document_library_tags_ids,
    get_search_policy,
    get_vector_search_scopes,
    set_attachments_markdown,
)
from fred_sdk.contracts.context import (
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)


def test_runtime_context_helpers_defaults():
    context = RuntimeContext()

    assert get_document_library_tags_ids(None) is None
    assert get_search_policy(None) == "hybrid"
    assert get_vector_search_scopes(None) == (True, True)

    set_attachments_markdown(context, "# Notes")
    assert context.attachments_markdown == "# Notes"


def test_langfuse_tracer_adapter_preserves_managed_identity_metadata() -> None:
    class _FakeObservation:
        def __init__(self) -> None:
            self.metadata = None
            self.ended = False

        def update(self, *, metadata=None, **kwargs):
            self.metadata = metadata
            return None

        def end(self, *, end_time=None):
            self.ended = True
            return None

    class _FakeLangfuse:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []
            self.observation = _FakeObservation()

        def create_trace_id(self, seed: str) -> str:
            self.calls.append({"seed": seed})
            return "trace-generated"

        def start_observation(self, **kwargs):
            self.calls.append(kwargs)
            return self.observation

    fake = _FakeLangfuse()
    tracer = LangfuseTracerAdapter(fake)  # type: ignore[arg-type]
    span = tracer.start_span(
        "agent.run",
        context=PortableContext(
            request_id="req-1",
            correlation_id="corr-1",
            actor="alice",
            tenant="fred",
            environment=PortableEnvironment.DEV,
            trace_id="trace-upstream",
            agent_id="template-1",
            agent_name="template-1",
            session_id="sess-1",
            user_id="alice",
            team_id="team-red",
            baggage={
                "agent_instance_id": "inst-1",
                "template_agent_id": "template-1",
                "checkpoint_id": "cp-1",
                "execution_action": "resume",
            },
        ),
        attributes={"status": "ok"},
    )
    span.set_attribute("phase", "finalize")
    span.end()

    metadata = cast(dict[str, object], fake.calls[1]["metadata"])
    baggage = cast(dict[str, object], metadata["baggage"])
    observation_metadata = cast(dict[str, object], fake.observation.metadata or {})

    assert metadata["agent_instance_id"] == "inst-1"
    assert metadata["template_agent_id"] == "template-1"
    assert metadata["checkpoint_id"] == "cp-1"
    assert metadata["execution_action"] == "resume"
    assert metadata["trace_id"] == "trace-upstream"
    assert baggage["agent_instance_id"] == "inst-1"
    assert metadata["status"] == "ok"
    assert observation_metadata["phase"] == "finalize"
