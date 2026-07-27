#!/usr/bin/env python3
"""Run a guarded local FRED managed-SSE performance campaign."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any


DEFAULT_FRED_ROOT = pathlib.Path("/home/dimi/Fred/fred")
DEFAULT_MOCK_ROOT = pathlib.Path("/home/dimi/Fred/mock-openai-server")
DEFAULT_TARGET = "http://127.0.0.1:8000/fred/agents/v2/agents/execute/stream"
DEFAULT_MOCK_URL = "http://127.0.0.1:8383"
DEFAULT_RUNTIME_METRICS = "http://127.0.0.1:9000/metrics"
DEFAULT_CONTROL_METRICS = "http://127.0.0.1:9222/metrics"
DEFAULT_PROMPT = "Réponds simplement : test réussi"
CONSOLIDATION_STAGES = [
    ("preflight", 1, 1),
    ("baseline", 1, 10),
    ("scale-05", 5, 3),
    ("scale-10", 10, 3),
    ("scale-20", 20, 3),
    ("scale-50", 50, 3),
]
OVERLOAD_STAGES = [("overload", 75, 1), ("recovery", 1, 3)]
EXPECTED_DEFAULT_REQUESTS = sum(c * r for _, c, r in CONSOLIDATION_STAGES)
EXPECTED_OVERLOAD_REQUESTS = EXPECTED_DEFAULT_REQUESTS + sum(
    c * r for _, c, r in OVERLOAD_STAGES
)


@dataclass(frozen=True)
class Stage:
    name: str
    clients: int
    requests_per_client: int

    @property
    def total(self) -> int:
        return self.clients * self.requests_per_client


class CampaignError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Guarded localhost-only FRED managed-SSE campaign"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true", help="print the budget only")
    mode.add_argument("--execute", action="store_true", help="execute after confirmation")
    parser.add_argument("--agent-instance-id")
    parser.add_argument("--team-id")
    parser.add_argument("--target", default=DEFAULT_TARGET)
    parser.add_argument("--mock-url", default=DEFAULT_MOCK_URL)
    parser.add_argument("--runtime-metrics-url", default=DEFAULT_RUNTIME_METRICS)
    parser.add_argument("--control-metrics-url", default=DEFAULT_CONTROL_METRICS)
    parser.add_argument("--fred-root", type=pathlib.Path, default=DEFAULT_FRED_ROOT)
    parser.add_argument("--mock-root", type=pathlib.Path, default=DEFAULT_MOCK_ROOT)
    parser.add_argument("--results-root", type=pathlib.Path)
    parser.add_argument("--mock-delay-ms", type=int, default=1000)
    parser.add_argument("--mock-summary-interval-ms", type=int, default=1000)
    parser.add_argument("--expected-model", default="mock-openai-chat")
    parser.add_argument("--start-mock", action="store_true")
    parser.add_argument("--allow-missing-metrics", action="store_true")
    parser.add_argument("--allow-overload", action="store_true")
    parser.add_argument("--confirm-max-clients", type=int)
    parser.add_argument("--confirm-overload-max-clients", type=int)
    parser.add_argument("--confirm-total-requests", type=int)
    parser.add_argument("--stage-timeout-seconds", type=int, default=180)
    parser.add_argument("--cooldown-seconds", type=int, default=8)
    parser.add_argument("--min-memory-available-percent", type=float, default=20.0)
    parser.add_argument("--max-load-per-cpu", type=float, default=0.85)
    return parser.parse_args()


def stages_for(args: argparse.Namespace) -> list[Stage]:
    definitions = list(CONSOLIDATION_STAGES)
    if args.allow_overload:
        definitions.extend(OVERLOAD_STAGES)
    return [Stage(*definition) for definition in definitions]


def ensure_loopback(raw_url: str, label: str) -> None:
    parsed = urllib.parse.urlsplit(raw_url)
    if parsed.scheme not in {"http", "https"}:
        raise CampaignError(f"{label} must use http(s): {raw_url}")
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise CampaignError(f"{label} must be loopback-only: {raw_url}")
    if parsed.username or parsed.password:
        raise CampaignError(f"{label} must not contain URL credentials")
    sensitive_query_keys = {"token", "access_token", "api_key", "key"}
    if sensitive_query_keys.intersection(urllib.parse.parse_qs(parsed.query)):
        raise CampaignError(f"{label} must not contain credentials in its query")


def print_plan(args: argparse.Namespace) -> None:
    stages = stages_for(args)
    estimated_floor_seconds = (
        sum(stage.requests_per_client for stage in stages)
        * args.mock_delay_ms
        / 1000
        + max(len(stages) - 1, 0) * args.cooldown_seconds
    )
    hard_upper_bound_seconds = (
        len(stages) * args.stage_timeout_seconds
        + max(len(stages) - 1, 0) * args.cooldown_seconds
    )
    print("FRED local managed-SSE performance campaign")
    print(f"Target: {args.target}")
    print(f"Mock: {args.mock_url} (fixed asynchronous delay {args.mock_delay_ms} ms)")
    print(f"Max clients: {max(stage.clients for stage in stages)}")
    print(f"Total requests: {sum(stage.total for stage in stages)}")
    print(
        "Stages: "
        + ", ".join(
            f"{stage.name}={stage.clients}x{stage.requests_per_client}"
            for stage in stages
        )
    )
    print(
        "Upper-bound stage timeout: "
        f"{args.stage_timeout_seconds}s; cooldown: {args.cooldown_seconds}s"
    )
    print(
        f"Duration: mock/cooldown floor ~{estimated_floor_seconds:.0f}s; "
        f"hard campaign bound ~{hard_upper_bound_seconds / 60:.1f}min"
    )
    print("Adaptive stop: >1% errors, p50 >3x baseline, or host resource guard")
    if not args.allow_overload:
        print("Overload: disabled (requires separate explicit confirmation)")


def validate_execution(args: argparse.Namespace, stages: list[Stage]) -> None:
    for value, label in [
        (args.target, "target"),
        (args.mock_url, "mock URL"),
        (args.runtime_metrics_url, "runtime metrics URL"),
        (args.control_metrics_url, "control-plane metrics URL"),
    ]:
        ensure_loopback(value, label)
    if not args.agent_instance_id or not args.team_id:
        raise CampaignError("--agent-instance-id and --team-id are required")
    if not args.team_id.startswith("personal-"):
        raise CampaignError("this campaign requires a personal-space team_id")
    if not os.environ.get("AGENTIC_TOKEN"):
        raise CampaignError("AGENTIC_TOKEN must be present in the environment")
    if args.mock_delay_ms < 0 or args.mock_summary_interval_ms < 0:
        raise CampaignError("mock timing values must be non-negative")
    expected_max = max(stage.clients for stage in stages)
    expected_total = sum(stage.total for stage in stages)
    if args.confirm_max_clients != 50:
        raise CampaignError("--confirm-max-clients must explicitly equal 50")
    if args.allow_overload and args.confirm_overload_max_clients != 75:
        raise CampaignError(
            "overload requires --confirm-overload-max-clients 75"
        )
    if args.confirm_total_requests != expected_total:
        raise CampaignError(
            f"--confirm-total-requests must equal this plan ({expected_total})"
        )
    if expected_max > 75:
        raise CampaignError("hard safety cap exceeded")
    benchmark_dir = args.fred_root / "developer_tools" / "benchmarks"
    for required in [args.fred_root, benchmark_dir, args.mock_root]:
        if not required.is_dir():
            raise CampaignError(f"required directory missing: {required}")


def fetch(url: str, timeout: float = 5.0) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        if response.status != 200:
            raise CampaignError(f"GET {url} returned HTTP {response.status}")
        return response.read()


def fetch_json(url: str) -> dict[str, Any]:
    try:
        return json.loads(fetch(url).decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise CampaignError(f"cannot read JSON from {url}: {exc}") from exc


def write_json(path: pathlib.Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def host_resources(args: argparse.Namespace) -> dict[str, float | bool]:
    mem_total = 0
    mem_available = 0
    for line in pathlib.Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        key, raw_value = line.split(":", 1)
        if key == "MemTotal":
            mem_total = int(raw_value.strip().split()[0])
        elif key == "MemAvailable":
            mem_available = int(raw_value.strip().split()[0])
    memory_percent = 100.0 * mem_available / mem_total if mem_total else 0.0
    load_one = os.getloadavg()[0]
    cpu_count = os.cpu_count() or 1
    load_per_cpu = load_one / cpu_count
    return {
        "memory_available_percent": round(memory_percent, 2),
        "load_1m_per_cpu": round(load_per_cpu, 3),
        "healthy": (
            memory_percent >= args.min_memory_available_percent
            and load_per_cpu <= args.max_load_per_cpu
        ),
    }


def verify_mock_profile(health: dict[str, Any], args: argparse.Namespace) -> None:
    profile = health.get("performance_profile", {})
    expected = {
        "response_delay_enabled": args.mock_delay_ms > 0,
        "response_delay_min_ms": args.mock_delay_ms,
        "response_delay_max_ms": args.mock_delay_ms,
        "summary_log_interval_ms": args.mock_summary_interval_ms,
    }
    mismatches = {
        key: {"expected": value, "actual": profile.get(key)}
        for key, value in expected.items()
        if profile.get(key) != value
    }
    if health.get("status") != "ok" or mismatches:
        raise CampaignError(f"mock performance profile mismatch: {mismatches}")


def start_or_verify_mock(
    args: argparse.Namespace, run_dir: pathlib.Path
) -> tuple[subprocess.Popen[str] | None, Any]:
    try:
        health = fetch_json(f"{args.mock_url}/health")
    except CampaignError:
        health = None
    if health is not None:
        verify_mock_profile(health, args)
        return None, None
    if not args.start_mock:
        raise CampaignError(
            "mock is not reachable; start it or rerun with --start-mock"
        )

    parsed = urllib.parse.urlsplit(args.mock_url)
    mock_log = (run_dir / "mock.stdout.log").open("w", encoding="utf-8")
    env = os.environ.copy()
    env.update(
        {
            "HOST": parsed.hostname or "127.0.0.1",
            "PORT": str(parsed.port or 8383),
            "RESPONSE_DELAY_MS": str(args.mock_delay_ms),
            "SUMMARY_LOG_INTERVAL_MS": str(args.mock_summary_interval_ms),
        }
    )
    process = subprocess.Popen(
        ["make", "run"],
        cwd=args.mock_root,
        env=env,
        stdout=mock_log,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    try:
        for _ in range(60):
            if process.poll() is not None:
                raise CampaignError(
                    "owned mock exited during startup; inspect mock.stdout.log"
                )
            try:
                health = fetch_json(f"{args.mock_url}/health")
                verify_mock_profile(health, args)
                return process, mock_log
            except CampaignError:
                time.sleep(0.5)
        raise CampaignError("owned mock did not become healthy within 30 seconds")
    except Exception:
        stop_owned_mock(process, mock_log)
        raise


def stop_owned_mock(process: subprocess.Popen[str] | None, log_file: Any) -> None:
    if process is not None and process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
    if log_file is not None:
        log_file.close()


def snapshot_url(url: str, path: pathlib.Path, allow_missing: bool) -> bool:
    try:
        path.write_bytes(fetch(url))
        return True
    except CampaignError as exc:
        path.write_text(f"UNAVAILABLE: {exc}\n", encoding="utf-8")
        if not allow_missing:
            raise
        return False


def git_state(root: pathlib.Path) -> dict[str, Any]:
    def output(*command: str) -> str:
        completed = subprocess.run(
            command,
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        return completed.stdout.strip()

    return {
        "commit": output("git", "rev-parse", "HEAD"),
        "branch": output("git", "branch", "--show-current"),
        "dirty": bool(output("git", "status", "--porcelain")),
        "worktree": str(root.resolve()),
    }


def mock_counter(health: dict[str, Any], name: str) -> int:
    return int(health.get("monitoring", {}).get(name, 0))


def run_stage(
    args: argparse.Namespace,
    stage: Stage,
    run_dir: pathlib.Path,
) -> dict[str, Any]:
    resources_before = host_resources(args)
    if not resources_before["healthy"]:
        raise CampaignError(
            f"host resource guard refused {stage.name}: {resources_before}"
        )

    before_health = fetch_json(f"{args.mock_url}/health")
    verify_mock_profile(before_health, args)
    write_json(run_dir / f"{stage.name}.mock.before.json", before_health)
    snapshot_url(
        args.runtime_metrics_url,
        run_dir / f"{stage.name}.runtime.before.metrics",
        args.allow_missing_metrics,
    )
    snapshot_url(
        args.control_metrics_url,
        run_dir / f"{stage.name}.control-plane.before.metrics",
        args.allow_missing_metrics,
    )

    report_path = run_dir / f"{stage.name}.json"
    benchmark_dir = args.fred_root / "developer_tools" / "benchmarks"
    benchmark_args = " ".join(
        [
            "-protocol=sse",
            f"-url={args.target}",
            f"-agent-instance-id={args.agent_instance_id}",
            f"-sse-team-id={args.team_id}",
            f"-message={json.dumps(DEFAULT_PROMPT, ensure_ascii=False)}",
            f"-clients={stage.clients}",
            f"-requests-per-client={stage.requests_per_client}",
            "-ramp-duration=0s",
            "-timeout=30s",
            f"-json-report={report_path}",
        ]
    )
    env = os.environ.copy()
    try:
        completed = subprocess.run(
            ["make", "run", f"ARGS={benchmark_args}"],
            cwd=benchmark_dir,
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=args.stage_timeout_seconds,
        )
        output = completed.stdout + completed.stderr
        return_code = completed.returncode
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + (exc.stderr or "")
        return_code = 124

    token = os.environ["AGENTIC_TOKEN"]
    redacted_output = output.replace(token, "[REDACTED]").replace(
        DEFAULT_PROMPT, "[REDACTED]"
    )
    (run_dir / f"{stage.name}.stdout.log").write_text(
        redacted_output, encoding="utf-8"
    )
    if return_code != 0:
        raise CampaignError(f"{stage.name} benchmark exited {return_code}")
    if not report_path.is_file():
        raise CampaignError(f"{stage.name} did not produce its JSON report")

    benchmark = json.loads(report_path.read_text(encoding="utf-8"))
    after_health = fetch_json(f"{args.mock_url}/health")
    write_json(run_dir / f"{stage.name}.mock.after.json", after_health)
    runtime_metrics_path = run_dir / f"{stage.name}.runtime.after.metrics"
    control_metrics_path = run_dir / f"{stage.name}.control-plane.after.metrics"
    snapshot_url(
        args.runtime_metrics_url,
        runtime_metrics_path,
        args.allow_missing_metrics,
    )
    snapshot_url(
        args.control_metrics_url,
        control_metrics_path,
        args.allow_missing_metrics,
    )
    resources_after = host_resources(args)

    started_delta = mock_counter(after_health, "total_started") - mock_counter(
        before_health, "total_started"
    )
    completed_delta = mock_counter(after_health, "total_completed") - mock_counter(
        before_health, "total_completed"
    )
    error_delta = mock_counter(after_health, "total_errors") - mock_counter(
        before_health, "total_errors"
    )
    result = {
        "name": stage.name,
        "clients": stage.clients,
        "requests_per_client": stage.requests_per_client,
        "total": stage.total,
        "benchmark": benchmark,
        "mock_delta": {
            "started": started_delta,
            "completed": completed_delta,
            "errors": error_delta,
        },
        "resources_before": resources_before,
        "resources_after": resources_after,
    }

    if stage.name == "preflight":
        last_model = after_health.get("monitoring", {}).get("last_chat_model")
        if started_delta != 1 or completed_delta != 1 or error_delta != 0:
            raise CampaignError(f"preflight mock counters invalid: {result['mock_delta']}")
        if last_model != args.expected_model:
            raise CampaignError(
                f"preflight routed to {last_model!r}, expected {args.expected_model!r}"
            )
        if not args.allow_missing_metrics:
            metrics = (
                runtime_metrics_path.read_text(encoding="utf-8")
                + control_metrics_path.read_text(encoding="utf-8")
            )
            for metric in ["runtime_stage_latency_ms", "rebac_call_latency_ms"]:
                if metric not in metrics:
                    raise CampaignError(f"required metric absent after preflight: {metric}")
    return result


def stage_stop_reason(
    result: dict[str, Any], baseline_p50: int | None
) -> str | None:
    benchmark = result["benchmark"]
    total = max(int(benchmark.get("total_requests", 0)), 1)
    error_rate = int(benchmark.get("errors", 0)) / total
    if error_rate > 0.01:
        return f"error rate {error_rate:.2%} exceeds 1%"
    if result["mock_delta"]["errors"] > 0:
        return f"mock observed {result['mock_delta']['errors']} errors"
    if not result["resources_after"]["healthy"]:
        return f"host resource guard degraded: {result['resources_after']}"
    latency = benchmark.get("latency") or {}
    p50 = latency.get("p50_ms")
    if baseline_p50 and p50 is not None and p50 > 3 * baseline_p50:
        return f"p50 {p50}ms exceeds 3x baseline {baseline_p50}ms"
    return None


def build_report(campaign: dict[str, Any], run_dir: pathlib.Path) -> None:
    lines = [
        "# FRED local performance campaign",
        "",
        f"- Started: {campaign['started_at']}",
        f"- Commit: `{campaign['repository']['commit']}`",
        f"- Branch: `{campaign['repository']['branch']}`",
        f"- Worktree dirty: `{campaign['repository']['dirty']}`",
        f"- Target: `{campaign['target']}`",
        f"- Mock delay: `{campaign['mock_profile']['fixed_delay_ms']} ms`",
        f"- Verdict: **{campaign['verdict']}**",
    ]
    if campaign.get("stop_reason"):
        lines.append(f"- Stop reason: {campaign['stop_reason']}")
    lines.extend(
        [
            "",
            "| Stage | Load | Success/errors | req/s | p50/p95/p99 ms | p50 vs baseline |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    baseline = campaign.get("baseline_p50_ms")
    for result in campaign["stages"]:
        benchmark = result["benchmark"]
        latency = benchmark.get("latency") or {}
        p50 = latency.get("p50_ms")
        ratio = f"{p50 / baseline:.2f}x" if baseline and p50 is not None else "—"
        lines.append(
            "| {name} | {clients}x{requests} | {success}/{errors} | {rps:.2f} | "
            "{p50}/{p95}/{p99} | {ratio} |".format(
                name=result["name"],
                clients=result["clients"],
                requests=result["requests_per_client"],
                success=benchmark.get("success", 0),
                errors=benchmark.get("errors", 0),
                rps=float(benchmark.get("requests_per_second", 0)),
                p50=latency.get("p50_ms", "—"),
                p95=latency.get("p95_ms", "—"),
                p99=latency.get("p99_ms", "—"),
                ratio=ratio,
            )
        )
    lines.extend(
        [
            "",
            "This is a local mock-based regression-discovery run, not a production capacity claim.",
            "Interpret KPI snapshots and create one durable file per confirmed finding.",
            "",
        ]
    )
    (run_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


def execute(args: argparse.Namespace) -> pathlib.Path:
    stages = stages_for(args)
    validate_execution(args, stages)
    resources = host_resources(args)
    if not resources["healthy"]:
        raise CampaignError(f"initial host resource guard refused run: {resources}")

    results_root = args.results_root or (
        args.fred_root / "developer_tools" / "benchmarks" / "results"
    )
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = results_root / f"campaign-{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=False)

    campaign: dict[str, Any] = {
        "schema_version": "v1",
        "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "repository": git_state(args.fred_root),
        "target": args.target,
        "agent_instance_id": args.agent_instance_id,
        "team_id": args.team_id,
        "mock_url": args.mock_url,
        "mock_profile": {
            "fixed_delay_ms": args.mock_delay_ms,
            "summary_log_interval_ms": args.mock_summary_interval_ms,
            "expected_model": args.expected_model,
        },
        "budget": {
            "max_clients": max(stage.clients for stage in stages),
            "total_requests": sum(stage.total for stage in stages),
            "stage_timeout_seconds": args.stage_timeout_seconds,
        },
        "host_initial": resources,
        "stages": [],
        "baseline_p50_ms": None,
        "verdict": "RUNNING",
        "stop_reason": None,
    }
    write_json(run_dir / "campaign.json", campaign)

    owned_mock: subprocess.Popen[str] | None = None
    mock_log: Any = None
    try:
        owned_mock, mock_log = start_or_verify_mock(args, run_dir)
        for stage in stages:
            result = run_stage(args, stage, run_dir)
            campaign["stages"].append(result)
            if stage.name == "baseline":
                latency = result["benchmark"].get("latency") or {}
                campaign["baseline_p50_ms"] = latency.get("p50_ms")
            reason = stage_stop_reason(result, campaign["baseline_p50_ms"])
            if reason:
                campaign["verdict"] = f"STOPPED AT {stage.name}"
                campaign["stop_reason"] = reason
                break
            write_json(run_dir / "campaign.json", campaign)
            if stage.name != stages[-1].name:
                time.sleep(args.cooldown_seconds)
        else:
            campaign["verdict"] = "PASS"
    except CampaignError as exc:
        if campaign["stages"]:
            campaign["verdict"] = f"STOPPED AT {campaign['stages'][-1]['name']}"
        else:
            campaign["verdict"] = "INVALID"
        campaign["stop_reason"] = str(exc)
    finally:
        stop_owned_mock(owned_mock, mock_log)
        campaign["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        write_json(run_dir / "campaign.json", campaign)
        build_report(campaign, run_dir)

    return run_dir


def main() -> int:
    args = parse_args()
    try:
        ensure_loopback(args.target, "target")
        ensure_loopback(args.mock_url, "mock URL")
        print_plan(args)
        if args.plan:
            return 0
        run_dir = execute(args)
        campaign = json.loads((run_dir / "campaign.json").read_text(encoding="utf-8"))
        print(f"Artifacts: {run_dir}")
        print(f"Verdict: {campaign['verdict']}")
        if campaign.get("stop_reason"):
            print(f"Stop reason: {campaign['stop_reason']}")
        return 0 if campaign["verdict"] == "PASS" else 2
    except CampaignError as exc:
        print(f"Campaign refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
