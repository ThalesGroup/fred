# Copyright Thales 2025
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

"""Model tests: PptFillerParams round-trips through the ToolParams union.

Asserts the discriminated union (discriminated by ``provider``) selects PptFillerParams
for ``provider: "ppt_filler"`` and preserves the persisted schema, the fixed template key,
and the transient base64 upload field across (de)serialization.
"""

from pydantic import TypeAdapter

from agentic_backend.core.agents.agent_spec import MCPServerRef, ToolParams
from agentic_backend.integrations.ppt_filler.ppt_filler_params import (
    PPT_FILLER_TEMPLATE_KEY,
    PptFillerParams,
)

_tool_params_adapter = TypeAdapter(ToolParams)


def test_union_selects_ppt_filler_params_by_provider():
    parsed = _tool_params_adapter.validate_python({"provider": "ppt_filler"})

    assert isinstance(parsed, PptFillerParams)
    # The fixed per-agent template-key convention is the default (creator never picks it).
    assert parsed.template_key == PPT_FILLER_TEMPLATE_KEY
    assert parsed.schema_slides == []
    assert parsed.template_upload_b64 is None


def test_union_still_selects_kf_vector_search_params():
    from agentic_backend.integrations.kf_vector_search.kf_vector_search_params import (
        KfVectorSearchParams,
    )

    parsed = _tool_params_adapter.validate_python({"provider": "kf_vector_search"})

    assert isinstance(parsed, KfVectorSearchParams)


def test_ppt_filler_params_round_trips_with_schema_and_upload():
    payload = {
        "provider": "ppt_filler",
        "schema": [
            {
                "slide": 2,
                "keys": [{"key": "name", "description": "The person's name"}],
            }
        ],
        "template_upload_b64": "QUJD",  # transient bytes (base64 of b"ABC")
    }

    parsed = _tool_params_adapter.validate_python(payload)
    assert isinstance(parsed, PptFillerParams)
    assert parsed.schema_slides[0].slide == 2
    assert parsed.schema_slides[0].keys[0].key == "name"
    assert parsed.template_upload_b64 == "QUJD"

    # Round-trip back to a dict using the JSON aliases (schema, not schema_slides).
    dumped = parsed.model_dump(by_alias=True)
    assert dumped["provider"] == "ppt_filler"
    assert dumped["schema"] == [
        {"slide": 2, "keys": [{"key": "name", "description": "The person's name"}]}
    ]
    assert dumped["template_upload_b64"] == "QUJD"

    # Re-parse the dump: stable.
    reparsed = _tool_params_adapter.validate_python(dumped)
    assert reparsed == parsed


def test_ppt_filler_params_round_trips_through_mcp_server_ref():
    """The union is reached in practice via MCPServerRef.params; assert that path too."""
    ref = MCPServerRef.model_validate(
        {"id": "mcp-ppt-filler", "params": {"provider": "ppt_filler"}}
    )
    assert isinstance(ref.params, PptFillerParams)

    dumped = ref.model_dump(by_alias=True)
    assert dumped["params"]["provider"] == "ppt_filler"

    reparsed = MCPServerRef.model_validate(dumped)
    assert isinstance(reparsed.params, PptFillerParams)
    assert reparsed.params == ref.params
