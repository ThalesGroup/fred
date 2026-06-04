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
Compatibility shim — all implementation has moved to fred_runtime.cli.*

This module re-exports every name that external code (tests, entry-points,
downstream packages) previously imported from fred_runtime.client.
"""

from __future__ import annotations

# Re-export fred_core auth helpers that callers imported via this module
from fred_core.cli.auth import (
    KeycloakLoginConfig,
    KeycloakUserSessionManager,
    build_cli_token_provider,
    default_keycloak_token_file,
    load_cli_environment,
    resolve_keycloak_login_config,
)

from fred_runtime.cli import (
    DEFAULT_AGENT_POD_BASE_URL,
    AgentPodClient,
    ExecutionMode,
    HistogramSeriesSummary,
    PrometheusSample,
    build_hitl_resume_payload,
    build_parser,
    completion_candidates,
    default_agent_metrics_url,
    default_agent_pod_base_url,
    execution_mode_color,
    execution_mode_label,
    filter_prometheus_samples,
    fmt_bytes,
    format_metric_value,
    format_prometheus_labels,
    main,
    normalize_base_url,
    parse_mode_command,
    parse_prometheus_text_exposition,
    print_eval_trace,
    print_help,
    print_history,
    print_runtime_event,
    render_kpi_report,
    run_eval_turn,
    run_interactive_chat,
    run_single_turn,
    summarize_prometheus_histograms,
)

__all__ = [
    "AgentPodClient",
    "DEFAULT_AGENT_POD_BASE_URL",
    "ExecutionMode",
    "HistogramSeriesSummary",
    "KeycloakLoginConfig",
    "KeycloakUserSessionManager",
    "PrometheusSample",
    "build_cli_token_provider",
    "build_hitl_resume_payload",
    "build_parser",
    "completion_candidates",
    "default_agent_metrics_url",
    "default_agent_pod_base_url",
    "default_keycloak_token_file",
    "execution_mode_color",
    "execution_mode_label",
    "print_eval_trace",
    "filter_prometheus_samples",
    "fmt_bytes",
    "format_metric_value",
    "format_prometheus_labels",
    "load_cli_environment",
    "main",
    "normalize_base_url",
    "parse_mode_command",
    "parse_prometheus_text_exposition",
    "print_help",
    "print_history",
    "print_runtime_event",
    "render_kpi_report",
    "resolve_keycloak_login_config",
    "run_eval_turn",
    "run_interactive_chat",
    "run_single_turn",
    "summarize_prometheus_histograms",
]

if __name__ == "__main__":
    raise SystemExit(main())
