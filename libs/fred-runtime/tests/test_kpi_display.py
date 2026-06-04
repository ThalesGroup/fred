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

"""Offline tests for fred_runtime.cli.kpi_display."""

from __future__ import annotations

from fred_runtime.cli.kpi_display import (
    PrometheusSample,
    filter_prometheus_samples,
    format_metric_value,
    parse_prometheus_text_exposition,
    render_kpi_report,
    summarize_prometheus_histograms,
)

_SAMPLE_EXPOSITION = """\
# HELP agent_turn_latency_ms Agent turn latency
# TYPE agent_turn_latency_ms histogram
agent_turn_latency_ms_bucket{le="50"} 1
agent_turn_latency_ms_bucket{le="200"} 3
agent_turn_latency_ms_bucket{le="+Inf"} 4
agent_turn_latency_ms_sum 520.0
agent_turn_latency_ms_count 4
process_cpu_seconds_total 12.5
agent_tool_call_total{tool_name="search"} 7
"""


def test_parse_prometheus_text_exposition_empty_input() -> None:
    assert parse_prometheus_text_exposition("") == []


def test_parse_prometheus_text_exposition_skips_comments() -> None:
    samples = parse_prometheus_text_exposition("# HELP foo bar\n# TYPE foo counter\n")
    assert samples == []


def test_parse_prometheus_text_exposition_counter() -> None:
    samples = parse_prometheus_text_exposition(
        'agent_tool_call_total{tool_name="search"} 7\n'
    )
    assert len(samples) == 1
    assert samples[0].name == "agent_tool_call_total"
    assert samples[0].labels == {"tool_name": "search"}
    assert samples[0].value == 7.0


def test_parse_prometheus_text_exposition_histogram_bucket() -> None:
    samples = parse_prometheus_text_exposition(_SAMPLE_EXPOSITION)
    names = [s.name for s in samples]
    assert "agent_turn_latency_ms_count" in names
    assert "agent_turn_latency_ms_sum" in names


def test_summarize_prometheus_histograms_returns_summary() -> None:
    samples = parse_prometheus_text_exposition(_SAMPLE_EXPOSITION)
    summaries = summarize_prometheus_histograms(samples)
    assert len(summaries) == 1
    assert summaries[0].name == "agent_turn_latency_ms"
    assert summaries[0].count == 4.0
    assert summaries[0].sum_value == 520.0
    assert summaries[0].avg_value == 130.0


def test_format_metric_value_integer() -> None:
    assert format_metric_value(42.0) == "42"


def test_format_metric_value_float() -> None:
    assert format_metric_value(1.5) == "1.50"


def test_filter_prometheus_samples_by_name() -> None:
    samples = [
        PrometheusSample(name="agent_tool_call_total", labels={}, value=3.0),
        PrometheusSample(name="process_cpu_seconds_total", labels={}, value=1.0),
    ]
    filtered = filter_prometheus_samples(samples, pattern="agent_tool")
    assert len(filtered) == 1
    assert filtered[0].name == "agent_tool_call_total"


def test_render_kpi_report_returns_non_empty() -> None:
    samples = parse_prometheus_text_exposition(_SAMPLE_EXPOSITION)
    lines = render_kpi_report(samples, color_enabled=False)
    assert lines
    combined = "\n".join(lines)
    assert "agent_turn_latency_ms" in combined
