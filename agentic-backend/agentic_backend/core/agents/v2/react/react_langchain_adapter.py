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
Thin facade over the ReAct LangChain/LangGraph adapter modules.

Why this module exists:
- the ReAct runtime needs a handful of SDK-facing helpers, but keeping all of them
  in one 900-line file made the adapter look much larger than it really is
- the actual adapter is now split into three small scopes:
  - `react_message_codec`: transcript conversion between Fred models and LangChain
    messages
  - `react_stream_adapter`: parsing streamed LangGraph payloads into Fred runtime
    event pieces
  - `react_model_adapter`: model routing labels and tracing wrappers around chat
    model calls
- this facade keeps existing import sites stable while making the real boundaries
  easier to review

How to use:
- when editing one concern deeply, import from the narrower module directly
- when existing runtime code already imports from `react_langchain_adapter`, it is
  fine to keep using this facade

Example:
- narrow import:
  `from .react_message_codec import to_langchain_message`
- compatibility import:
  `from .react_langchain_adapter import to_langchain_message`
"""

from .react_message_codec import (
    final_assistant_message,
    from_langchain_message,
    graph_input_from_react_input,
    stringify_langchain_content,
    to_langchain_message,
    to_runnable_config,
)
from .react_model_adapter import (
    REACT_MODEL_OPERATION_PLANNING,
    REACT_MODEL_OPERATION_ROUTING,
    TRACE_MODEL_SPAN_NAME,
    CompiledReActAgent,
    build_tool_loop_model_call_wrapper,
    extract_model_name_from_model_response,
    extract_model_name_from_object,
    infer_react_model_operation_from_messages,
)
from .react_stream_adapter import (
    assistant_delta_from_stream_event,
    extract_interrupt_request,
    extract_messages_from_update,
    merge_sources,
    merge_ui_parts,
    normalize_token_usage,
    normalize_tool_artifact,
    runtime_metadata_from_message,
    runtime_metadata_from_stream_event,
    split_stream_event_mode,
)

__all__ = [
    "CompiledReActAgent",
    "REACT_MODEL_OPERATION_PLANNING",
    "REACT_MODEL_OPERATION_ROUTING",
    "TRACE_MODEL_SPAN_NAME",
    "assistant_delta_from_stream_event",
    "build_tool_loop_model_call_wrapper",
    "extract_interrupt_request",
    "extract_messages_from_update",
    "extract_model_name_from_model_response",
    "extract_model_name_from_object",
    "final_assistant_message",
    "from_langchain_message",
    "graph_input_from_react_input",
    "infer_react_model_operation_from_messages",
    "merge_sources",
    "merge_ui_parts",
    "normalize_token_usage",
    "normalize_tool_artifact",
    "runtime_metadata_from_message",
    "runtime_metadata_from_stream_event",
    "split_stream_event_mode",
    "stringify_langchain_content",
    "to_langchain_message",
    "to_runnable_config",
]
