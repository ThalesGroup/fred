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

"""No prompt/response/tool-argument content in the generic app-log store
(issue #2009).

`TracingKpiMiddleware._log_model_call`/`_log_model_response` feed the shared
app logger — which flows into the generic, durable log store explorable via
OpenSearch Dashboards (see docs/swift/platform/OBSERVABILITY-AND-AUDIT.md §7:
"Content ... Nowhere in any observability or audit stream"). Lock in that
only lengths/names/counts are logged, never message/argument/answer text.
"""

from __future__ import annotations

import logging
from typing import cast

from fred_runtime.react.middleware import tracing_kpi as tracing_kpi_module
from fred_runtime.react.middleware.tracing_kpi import TracingKpiMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage

SECRET_QUESTION = (
    "what is my confidential account balance of $1,000,000"  # pragma: allowlist secret
)
SECRET_ANSWER = "your confidential account balance is one million dollars"  # pragma: allowlist secret
SECRET_ARG_VALUE = "sk-super-secret-tool-argument-value"  # pragma: allowlist secret


def test_log_model_call_never_logs_message_content(caplog) -> None:
    request = ModelRequest(
        model=cast(BaseChatModel, None),
        messages=[HumanMessage(content=SECRET_QUESTION)],
        system_prompt="be helpful",
        state={"messages": [HumanMessage(content=SECRET_QUESTION)]},
    )

    with caplog.at_level(logging.INFO, logger=tracing_kpi_module.__name__):
        TracingKpiMiddleware._log_model_call(request)

    assert caplog.records, "sanity: a log line was emitted"
    for record in caplog.records:
        assert SECRET_QUESTION not in record.getMessage()


def test_log_model_response_never_logs_tool_args_or_answer_text(caplog) -> None:
    tool_response = ModelResponse(
        result=[
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "lookup", "args": {"query": SECRET_ARG_VALUE}, "id": "1"}
                ],
            )
        ]
    )
    answer_response = ModelResponse(result=[AIMessage(content=SECRET_ANSWER)])

    with caplog.at_level(logging.INFO, logger=tracing_kpi_module.__name__):
        TracingKpiMiddleware._log_model_response(tool_response)
        TracingKpiMiddleware._log_model_response(answer_response)

    assert caplog.records, "sanity: log lines were emitted"
    for record in caplog.records:
        message = record.getMessage()
        assert SECRET_ARG_VALUE not in message
        assert SECRET_ANSWER not in message
