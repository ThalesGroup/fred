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

from .completion import completion_candidates
from .entrypoint import build_parser, main
from .history_display import (
    build_hitl_resume_payload,
    print_eval_trace,
    print_history,
    print_runtime_event,
    run_eval_turn,
    run_single_turn,
)
from .kpi_display import (
    HistogramSeriesSummary,
    PrometheusSample,
    filter_prometheus_samples,
    format_metric_value,
    format_prometheus_labels,
    parse_prometheus_text_exposition,
    render_kpi_report,
    summarize_prometheus_histograms,
)
from .pod_client import DEFAULT_AGENT_POD_BASE_URL, AgentPodClient
from .repl import run_interactive_chat
from .repl_helpers import (
    ExecutionMode,
    execution_mode_color,
    execution_mode_label,
    fmt_bytes,
    parse_mode_command,
    print_help,
)
from .url_helpers import (
    default_agent_metrics_url,
    default_agent_pod_base_url,
    normalize_base_url,
)

__all__ = [
    "AgentPodClient",
    "DEFAULT_AGENT_POD_BASE_URL",
    "ExecutionMode",
    "HistogramSeriesSummary",
    "PrometheusSample",
    "build_hitl_resume_payload",
    "build_parser",
    "completion_candidates",
    "default_agent_metrics_url",
    "default_agent_pod_base_url",
    "execution_mode_color",
    "execution_mode_label",
    "print_eval_trace",
    "filter_prometheus_samples",
    "fmt_bytes",
    "format_metric_value",
    "format_prometheus_labels",
    "main",
    "normalize_base_url",
    "parse_mode_command",
    "parse_prometheus_text_exposition",
    "print_help",
    "print_history",
    "print_runtime_event",
    "render_kpi_report",
    "run_eval_turn",
    "run_interactive_chat",
    "run_single_turn",
    "summarize_prometheus_histograms",
]
