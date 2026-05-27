from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from fred_core.cli.ui import (
    ANSI_CYAN,
    ANSI_DIM,
    ANSI_GREEN,
    ANSI_RED,
    ANSI_WHITE,
    ANSI_YELLOW,
    colorize,
)

_PROM_SAMPLE_RE = re.compile(
    r"^(?P<name>[^{\s]+)(?:\{(?P<labels>[^}]*)\})?\s+"
    r"(?P<value>[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)"
    r"(?:\s+\d+)?$"
)


@dataclass(frozen=True, slots=True)
class PrometheusSample:
    """One parsed Prometheus exposition sample line."""

    name: str
    labels: dict[str, str]
    value: float


@dataclass(frozen=True, slots=True)
class HistogramSeriesSummary:
    """One summarized Prometheus histogram series."""

    name: str
    labels: dict[str, str]
    count: float
    sum_value: float

    @property
    def avg_value(self) -> float:
        if self.count <= 0:
            return 0.0
        return self.sum_value / self.count


def parse_prometheus_text_exposition(text: str) -> list[PrometheusSample]:
    """Parse Prometheus exposition text into typed sample rows."""
    samples: list[PrometheusSample] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _PROM_SAMPLE_RE.match(line)
        if match is None:
            continue
        labels = _parse_prometheus_labels(match.group("labels") or "")
        samples.append(
            PrometheusSample(
                name=match.group("name"),
                labels=labels,
                value=float(match.group("value")),
            )
        )
    return samples


def _parse_prometheus_labels(label_block: str) -> dict[str, str]:
    """Parse one Prometheus label block into a plain dict."""
    labels: dict[str, str] = {}
    if not label_block:
        return labels
    for part in label_block.split(","):
        if "=" not in part:
            continue
        key, raw_value = part.split("=", 1)
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] == '"':
            value = bytes(value[1:-1], "utf-8").decode("unicode_escape")
        labels[key.strip()] = value
    return labels


def summarize_prometheus_histograms(
    samples: Sequence[PrometheusSample],
) -> list[HistogramSeriesSummary]:
    """Summarize Prometheus histogram families into `count/sum/avg` rows."""
    grouped: dict[tuple[str, tuple[tuple[str, str], ...]], dict[str, float]] = {}
    label_maps: dict[tuple[str, tuple[tuple[str, str], ...]], dict[str, str]] = {}
    for sample in samples:
        suffix = None
        for candidate in ("_count", "_sum"):
            if sample.name.endswith(candidate):
                suffix = candidate
                break
        if suffix is None:
            continue
        base_name = sample.name.removesuffix(suffix)
        filtered_labels = {k: v for k, v in sample.labels.items() if k != "le"}
        key = (base_name, tuple(sorted(filtered_labels.items())))
        grouped.setdefault(key, {})[suffix] = sample.value
        label_maps[key] = filtered_labels

    summaries: list[HistogramSeriesSummary] = []
    for key, values in grouped.items():
        name, _ = key
        if "_count" not in values and "_sum" not in values:
            continue
        summaries.append(
            HistogramSeriesSummary(
                name=name,
                labels=label_maps[key],
                count=values.get("_count", 0.0),
                sum_value=values.get("_sum", 0.0),
            )
        )
    return sorted(
        summaries,
        key=lambda item: (-item.count, item.name, sorted(item.labels.items())),
    )


def filter_prometheus_samples(
    samples: Sequence[PrometheusSample],
    *,
    pattern: str | None = None,
) -> list[PrometheusSample]:
    """Filter Prometheus samples by a free-text pattern over names and labels."""
    if not pattern:
        return list(samples)
    needle = pattern.lower()
    kept: list[PrometheusSample] = []
    for sample in samples:
        haystacks = [sample.name]
        haystacks.extend(f"{key}={value}" for key, value in sample.labels.items())
        if any(needle in haystack.lower() for haystack in haystacks):
            kept.append(sample)
    return kept


def format_metric_value(value: float) -> str:
    """Format one Prometheus sample value for compact terminal display."""
    if value.is_integer():
        return str(int(value))
    return f"{value:.2f}"


def format_prometheus_labels(
    labels: dict[str, str], *, keys: Sequence[str] | None = None
) -> str:
    """Render a compact label string for CLI KPI output."""
    if not labels:
        return "-"
    ordered_keys = list(keys or ())
    ordered_keys.extend(key for key in labels if key not in ordered_keys)
    parts = [f"{key}={labels[key]}" for key in ordered_keys if key in labels]
    return ", ".join(parts)


def render_kpi_report(
    samples: Sequence[PrometheusSample],
    *,
    color_enabled: bool,
    pattern: str | None = None,
) -> list[str]:
    """Render a compact human-readable KPI report from Prometheus samples."""
    filtered = filter_prometheus_samples(samples, pattern=pattern)
    if not filtered:
        return [
            colorize(
                "  No KPI metrics matched the requested filter.",
                color=ANSI_DIM,
                enabled=color_enabled,
            )
        ]

    histograms = summarize_prometheus_histograms(filtered)
    histogram_bases = {summary.name for summary in histograms}
    value_samples = [
        sample
        for sample in filtered
        if not any(
            sample.name == f"{base}{suffix}"
            for base in histogram_bases
            for suffix in ("_bucket", "_sum", "_count")
        )
    ]

    process_samples = [
        sample for sample in value_samples if sample.name.startswith("process_")
    ]
    counter_samples = [
        sample
        for sample in value_samples
        if sample.name.endswith("_total")
        and not sample.name.startswith("process_")
        and sample.value > 0
    ]
    other_samples = [
        sample
        for sample in value_samples
        if sample not in process_samples
        and sample not in counter_samples
        and not sample.name.endswith("_created")
    ]

    lines: list[str] = []
    title = "  KPI snapshot"
    if pattern:
        title += f" — filter={pattern}"
    lines.append(colorize(title, color=ANSI_DIM, enabled=color_enabled, bold=True))
    lines.append(colorize("  " + "─" * 72, color=ANSI_DIM, enabled=color_enabled))

    if histograms:
        _SUPPRESS_ALWAYS = {"actor_type", "status"}
        _CONTEXT_KEYS = (
            "session_id",
            "template_agent_id",
            "agent_instance_id",
            "team_id",
            "service",
            "agent_id",
        )
        if len(histograms) == 1:
            shared_labels = {
                k: v
                for k, v in histograms[0].labels.items()
                if k not in _SUPPRESS_ALWAYS
            }
        else:
            shared_labels = {}
            for key in histograms[0].labels:
                if key in _SUPPRESS_ALWAYS:
                    continue
                val = histograms[0].labels[key]
                if all(s.labels.get(key) == val for s in histograms[1:]):
                    shared_labels[key] = val

        lines.append(
            colorize(
                "  Phase / latency breakdown:",
                color=ANSI_WHITE,
                enabled=color_enabled,
                bold=True,
            )
        )
        if shared_labels:
            ctx_parts = [
                colorize(k + "=", color=ANSI_DIM, enabled=color_enabled)
                + colorize(shared_labels[k], color=ANSI_GREEN, enabled=color_enabled)
                for k in _CONTEXT_KEYS
                if k in shared_labels
            ]
            extra_ctx = [
                colorize(f"{k}={v}", color=ANSI_DIM, enabled=color_enabled)
                for k, v in shared_labels.items()
                if k not in _CONTEXT_KEYS
            ]
            ctx_line = (
                "  "
                + colorize(
                    "context  ", color=ANSI_DIM, enabled=color_enabled, bold=True
                )
                + "  ".join(ctx_parts + extra_ctx)
            )
            lines.append(ctx_line)

        for summary in histograms[:10]:
            phase = summary.labels.get("phase", "")
            tool = summary.labels.get("tool_name", "")
            phase_label = phase or tool or summary.name
            row_labels = {
                k: v
                for k, v in summary.labels.items()
                if k not in _SUPPRESS_ALWAYS
                and k not in shared_labels
                and k not in ("phase", "tool_name")
            }
            row_label_str = format_prometheus_labels(
                row_labels,
                keys=("agent_step", "agent_instance_id", "team_id"),
            )
            lines.append(
                "  "
                + colorize(
                    f"[{phase_label}]",
                    color=ANSI_CYAN,
                    enabled=color_enabled,
                    bold=True,
                )
                + "  "
                + colorize(
                    f"avg={format_metric_value(summary.avg_value):>7} ms",
                    color=ANSI_YELLOW,
                    enabled=color_enabled,
                    bold=True,
                )
                + colorize(
                    f"  n={format_metric_value(summary.count):>4}"
                    f"  total={format_metric_value(summary.sum_value):>8} ms",
                    color=ANSI_DIM,
                    enabled=color_enabled,
                )
                + (
                    colorize(
                        f"  ({row_label_str})", color=ANSI_DIM, enabled=color_enabled
                    )
                    if row_label_str != "-"
                    else ""
                )
            )

    if process_samples:
        lines.append("")
        lines.append(
            colorize(
                "  Process gauges:", color=ANSI_DIM, enabled=color_enabled, bold=True
            )
        )
        for sample in sorted(process_samples, key=lambda item: item.name):
            lines.append(
                "  "
                + colorize(
                    sample.name, color=ANSI_GREEN, enabled=color_enabled, bold=True
                )
                + colorize(
                    f"  value={format_metric_value(sample.value):>8}",
                    color=ANSI_DIM,
                    enabled=color_enabled,
                )
                + colorize(
                    f"  [{format_prometheus_labels(sample.labels, keys=('pool',))}]",
                    color=ANSI_DIM,
                    enabled=color_enabled,
                )
            )

    if counter_samples:
        lines.append("")
        lines.append(
            colorize("  Counters:", color=ANSI_DIM, enabled=color_enabled, bold=True)
        )
        for sample in sorted(
            counter_samples, key=lambda item: (-item.value, item.name)
        )[:10]:
            counter_color = (
                ANSI_RED
                if any(word in sample.name for word in ("failed", "error"))
                else ANSI_YELLOW
            )
            lines.append(
                "  "
                + colorize(
                    sample.name, color=counter_color, enabled=color_enabled, bold=True
                )
                + colorize(
                    f"  total={format_metric_value(sample.value):>8}",
                    color=ANSI_DIM,
                    enabled=color_enabled,
                )
                + colorize(
                    f"  [{format_prometheus_labels(sample.labels, keys=('tool_name', 'agent_instance_id', 'team_id', 'session_id', 'error_code'))}]",
                    color=ANSI_DIM,
                    enabled=color_enabled,
                )
            )

    if other_samples and not pattern:
        lines.append("")
        lines.append(
            colorize(
                "  Other samples:", color=ANSI_DIM, enabled=color_enabled, bold=True
            )
        )
        for sample in sorted(other_samples, key=lambda item: item.name)[:5]:
            lines.append(
                "  "
                + colorize(sample.name, color=ANSI_DIM, enabled=color_enabled)
                + colorize(
                    f"  value={format_metric_value(sample.value):>8}",
                    color=ANSI_DIM,
                    enabled=color_enabled,
                )
            )

    return lines
