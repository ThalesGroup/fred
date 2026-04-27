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
    HistogramSeriesSummary,
    PrometheusSample,
    ScenarioSkipped,
    _complete_scenario_path,
    build_hitl_resume_payload,
    build_parser,
    completion_candidates,
    default_agent_metrics_url,
    default_agent_pod_base_url,
    execution_mode_label,
    filter_prometheus_samples,
    fmt_bytes,
    format_metric_value,
    format_prometheus_labels,
    main,
    normalize_base_url,
    parse_mode_command,
    parse_prometheus_text_exposition,
    print_help,
    print_history,
    print_runtime_event,
    render_kpi_report,
    run_interactive_chat,
    run_scenario_file,
    run_single_turn,
    summarize_prometheus_histograms,
)

__all__ = [
    "AgentPodClient",
    "DEFAULT_AGENT_POD_BASE_URL",
    "HistogramSeriesSummary",
    "KeycloakLoginConfig",
    "KeycloakUserSessionManager",
    "PrometheusSample",
    "ScenarioSkipped",
    "_complete_scenario_path",
    "build_cli_token_provider",
    "build_hitl_resume_payload",
    "build_parser",
    "completion_candidates",
    "default_agent_metrics_url",
    "default_agent_pod_base_url",
    "default_keycloak_token_file",
    "execution_mode_label",
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
    "run_interactive_chat",
    "run_scenario_file",
    "run_single_turn",
    "summarize_prometheus_histograms",
]

if __name__ == "__main__":
    raise SystemExit(main())
