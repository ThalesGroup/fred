#!/usr/bin/env python3
"""
Submit many ingestion requests in parallel to stress Temporal ingestion concurrency.

Why:
    We need a repeatable load script to validate that workflow fan-out and worker
    concurrency settings (`ingestion_*`) are effective under pressure.
How:
    The script sends many multipart requests to `/upload-process-documents` using
    an async HTTP client with a configurable semaphore for request concurrency.
    It parses the NDJSON event stream of each request and aggregates success,
    latency, throughput, and workflow identifiers.
Usage example:
    uv run python tests/scripts/temporal_ingestion_load_test.py \
      --base-url http://127.0.0.1:8111/knowledge-flow/v1 \
      --input-dir ./tests/assets \
      --requests 120 \
      --concurrency 24 \
      --files-per-request 2 \
      --profile fast \
      --source-tag fred
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import mimetypes
import os
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


@dataclass(slots=True)
class RequestResult:
    """
    Result payload for one ingestion request.

    Why:
        A typed structure keeps per-request metrics explicit and easy to aggregate.
    How:
        Each worker task creates one RequestResult after the NDJSON stream finishes.
    """

    index: int
    user_index: int
    ok: bool
    http_status: int
    duration_s: float
    done_status: str | None
    workflow_id: str | None
    error: str | None


def parse_args() -> argparse.Namespace:
    """
    Parse CLI options for load generation and reporting.

    Why:
        Ingestion load testing needs tunable request volume, concurrency, payload,
        and auth settings depending on environment.
    How:
        Expose explicit flags and validate ranges early through argparse.
    Usage example:
        `parse_args()` is called from `main()` before launching async workers.
    """

    parser = argparse.ArgumentParser(description="Parallel ingestion load test for knowledge-flow backend.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8111/knowledge-flow/v1", help="Knowledge-flow base URL.")
    parser.add_argument("--endpoint", default="/upload-process-documents", help="Ingestion endpoint path.")
    parser.add_argument("--requests", type=int, default=50, help="Total ingestion requests to submit.")
    parser.add_argument("--users", type=int, default=1, help="Number of simulated concurrent users.")
    parser.add_argument(
        "--requests-per-user",
        type=int,
        default=0,
        help="If > 0, overrides --requests and uses users * requests-per-user total requests.",
    )
    parser.add_argument("--concurrency", type=int, default=10, help="Maximum concurrent HTTP requests.")
    parser.add_argument("--files-per-request", type=int, default=1, help="How many files to send in each request.")
    parser.add_argument(
        "--file",
        action="append",
        default=[],
        help="Explicit file path to upload. Can be repeated. If omitted, files are read from --input-dir.",
    )
    parser.add_argument(
        "--input-dir",
        default=None,
        help="Directory scanned recursively for files when --file is not provided.",
    )
    parser.add_argument(
        "--extensions",
        default=".pdf,.docx,.pptx,.txt,.md,.csv,.jsonl",
        help="Comma-separated file extensions used with --input-dir.",
    )
    parser.add_argument("--source-tag", default="fred", help="Ingestion metadata source_tag.")
    parser.add_argument("--tags", default="", help="Comma-separated metadata tags.")
    parser.add_argument("--profile", default="", help="Optional ingestion profile: fast|medium|rich.")
    parser.add_argument("--token", default=os.getenv("FRED_BEARER_TOKEN", ""), help="Optional Bearer token.")
    parser.add_argument(
        "--user-tokens-file",
        default="",
        help="Optional text file with one bearer token per line to simulate distinct authenticated users.",
    )
    parser.add_argument("--connect-timeout", type=float, default=10.0, help="HTTP connect timeout in seconds.")
    parser.add_argument("--read-timeout", type=float, default=3600.0, help="HTTP read timeout in seconds.")
    parser.add_argument("--insecure", action="store_true", help="Disable TLS verification.")
    parser.add_argument("--report-json", default="", help="Optional output path for JSON report.")
    return parser.parse_args()


def collect_files(args: argparse.Namespace) -> list[Path]:
    """
    Build the list of uploadable files for the load run.

    Why:
        The request generator needs a deterministic pool of files to pick from.
    How:
        Prefer explicit `--file` inputs; otherwise scan `--input-dir` recursively
        with allowed extensions, then return a stable sorted list.
    Usage example:
        `files = collect_files(args)` in `main_async()`.
    """

    explicit = [Path(raw).expanduser().resolve() for raw in args.file]
    if explicit:
        missing = [str(path) for path in explicit if not path.exists() or not path.is_file()]
        if missing:
            raise ValueError(f"Missing file(s): {', '.join(missing)}")
        return explicit

    if not args.input_dir:
        raise ValueError("Provide at least one --file or set --input-dir.")

    root = Path(args.input_dir).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Input directory not found: {root}")

    allowed = {token.strip().lower() for token in args.extensions.split(",") if token.strip()}
    normalized_allowed = {ext if ext.startswith(".") else f".{ext}" for ext in allowed}

    files = [path for path in sorted(root.rglob("*")) if path.is_file() and path.suffix.lower() in normalized_allowed]
    if not files:
        allowed_str = ", ".join(sorted(normalized_allowed))
        raise ValueError(f"No matching files found in {root} for extensions: {allowed_str}")
    return files


def select_request_files(files: list[Path], request_index: int, files_per_request: int) -> list[Path]:
    """
    Select files for one request with round-robin distribution.

    Why:
        Reusing a bounded file pool avoids requiring huge local datasets while still
        varying payload composition between requests.
    How:
        Compute deterministic offsets based on request index and requested count.
    Usage example:
        Called once per request in `run_single_request()`.
    """

    total = len(files)
    start = (request_index * files_per_request) % total
    return [files[(start + offset) % total] for offset in range(files_per_request)]


def build_metadata_json(*, source_tag: str, tags: list[str], profile: str) -> str:
    """
    Build the `metadata_json` form field expected by ingestion endpoints.

    Why:
        The endpoint requires one JSON string payload shared by all uploaded files
        in a request.
    How:
        Include mandatory source/tag fields and conditionally add profile.
    Usage example:
        `metadata_json = build_metadata_json(...)` before HTTP POST.
    """

    payload: dict[str, Any] = {
        "tags": tags,
        "source_tag": source_tag,
    }
    profile_value = profile.strip().lower()
    if profile_value:
        payload["profile"] = profile_value
    return json.dumps(payload)


async def run_single_request(
    *,
    client: httpx.AsyncClient,
    base_url: str,
    endpoint: str,
    request_index: int,
    user_index: int,
    files_for_request: list[Path],
    metadata_json: str,
    semaphore: asyncio.Semaphore,
    auth_header: str | None,
) -> RequestResult:
    """
    Submit one multipart ingestion request and parse its NDJSON stream.

    Why:
        Per-request handling must capture both transport status and logical pipeline
        completion status emitted in streamed events.
    How:
        POST multipart form data, iterate NDJSON lines, extract `workflow_id` and
        terminal `done` event, then return a typed result.
    Usage example:
        Launched by `run_load()` inside `asyncio.gather`.
    """

    url = f"{base_url.rstrip('/')}{endpoint}"
    started = time.perf_counter()
    file_handles = []

    async with semaphore:
        try:
            multipart_files: list[tuple[str, tuple[str, Any, str]]] = []
            for file_path in files_for_request:
                file_handle = file_path.open("rb")
                file_handles.append(file_handle)
                guessed = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
                multipart_files.append(("files", (file_path.name, file_handle, guessed)))

            done_status: str | None = None
            workflow_id: str | None = None
            stream_error: str | None = None

            async with client.stream(
                "POST",
                url,
                data={"metadata_json": metadata_json},
                files=multipart_files,
                headers={"Authorization": auth_header} if auth_header else None,
            ) as response:
                http_status = response.status_code
                if http_status != 200:
                    body = (await response.aread()).decode("utf-8", errors="replace")
                    return RequestResult(
                        index=request_index,
                        user_index=user_index,
                        ok=False,
                        http_status=http_status,
                        duration_s=time.perf_counter() - started,
                        done_status=None,
                        workflow_id=None,
                        error=body[:1000],
                    )

                async for raw_line in response.aiter_lines():
                    if not raw_line:
                        continue
                    try:
                        event = json.loads(raw_line)
                    except json.JSONDecodeError:
                        stream_error = f"Invalid NDJSON line: {raw_line[:200]}"
                        continue

                    event_workflow_id = event.get("workflow_id")
                    if isinstance(event_workflow_id, str) and event_workflow_id:
                        workflow_id = event_workflow_id

                    if event.get("step") == "done":
                        value = event.get("status")
                        done_status = value if isinstance(value, str) else None
                        error = event.get("error")
                        if isinstance(error, str) and error:
                            stream_error = error

            ok = done_status == "success"
            return RequestResult(
                index=request_index,
                user_index=user_index,
                ok=ok,
                http_status=200,
                duration_s=time.perf_counter() - started,
                done_status=done_status,
                workflow_id=workflow_id,
                error=stream_error,
            )
        except Exception as exc:  # noqa: BLE001
            return RequestResult(
                index=request_index,
                user_index=user_index,
                ok=False,
                http_status=0,
                duration_s=time.perf_counter() - started,
                done_status=None,
                workflow_id=None,
                error=f"{type(exc).__name__}: {exc}",
            )
        finally:
            for handle in file_handles:
                handle.close()


async def run_load(args: argparse.Namespace, files: list[Path]) -> list[RequestResult]:
    """
    Run the configured load campaign and collect all request results.

    Why:
        A single orchestration function keeps the concurrency lifecycle, client
        configuration, and fan-out logic easy to reason about.
    How:
        Create one async client, spawn request tasks, and wait with gather.
    Usage example:
        Called once from `main_async(args)`.
    """

    timeout = httpx.Timeout(
        connect=args.connect_timeout,
        read=args.read_timeout,
        write=args.read_timeout,
        pool=args.connect_timeout,
    )
    default_auth_header = f"Bearer {args.token.strip()}" if args.token else None
    user_tokens = load_user_tokens(args.user_tokens_file)

    metadata_json = build_metadata_json(
        source_tag=args.source_tag,
        tags=[token.strip() for token in args.tags.split(",") if token.strip()],
        profile=args.profile,
    )

    semaphore = asyncio.Semaphore(max(1, args.concurrency))

    requests_total = resolve_total_requests(args)
    async with httpx.AsyncClient(timeout=timeout, verify=not args.insecure) as client:
        tasks = []
        for request_index in range(requests_total):
            user_index = request_index % max(1, args.users)
            files_for_request = select_request_files(files, request_index, max(1, args.files_per_request))
            auth_header = user_tokens[user_index] if user_index < len(user_tokens) else default_auth_header
            tasks.append(
                asyncio.create_task(
                    run_single_request(
                        client=client,
                        base_url=args.base_url,
                        endpoint=args.endpoint,
                        request_index=request_index,
                        user_index=user_index,
                        files_for_request=files_for_request,
                        metadata_json=metadata_json,
                        semaphore=semaphore,
                        auth_header=auth_header,
                    )
                )
            )
        return await asyncio.gather(*tasks)


def percentile(values: list[float], pct: float) -> float:
    """
    Compute percentile with linear interpolation.

    Why:
        Tail latency (p95/p99) is critical for ingestion throughput tuning.
    How:
        Sort values and interpolate by percentile rank.
    Usage example:
        `p95 = percentile(latencies, 95.0)`.
    """

    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    rank = (pct / 100.0) * (len(values) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return values[low]
    weight = rank - low
    return values[low] * (1 - weight) + values[high] * weight


def build_summary(*, results: list[RequestResult], started_at: float, finished_at: float) -> dict[str, Any]:
    """
    Build aggregated metrics from all request results.

    Why:
        Quick feedback loops need concise throughput and reliability indicators.
    How:
        Aggregate counts and latency statistics, plus sampled errors/workflow IDs.
    Usage example:
        `summary = build_summary(results=..., started_at=..., finished_at=...)`.
    """

    total = len(results)
    ok_results = [item for item in results if item.ok]
    failed_results = [item for item in results if not item.ok]
    latencies = sorted(item.duration_s for item in results)
    workflow_ids = sorted({item.workflow_id for item in results if item.workflow_id})
    users_seen = sorted({item.user_index for item in results})
    elapsed_s = max(0.000001, finished_at - started_at)

    return {
        "total_requests": total,
        "successful_requests": len(ok_results),
        "failed_requests": len(failed_results),
        "success_rate": (len(ok_results) / total) if total else 0.0,
        "elapsed_seconds": elapsed_s,
        "throughput_req_per_sec": total / elapsed_s,
        "latency_seconds": {
            "min": min(latencies) if latencies else 0.0,
            "avg": statistics.mean(latencies) if latencies else 0.0,
            "p50": percentile(latencies, 50.0),
            "p95": percentile(latencies, 95.0),
            "p99": percentile(latencies, 99.0),
            "max": max(latencies) if latencies else 0.0,
        },
        "workflow_ids_count": len(workflow_ids),
        "workflow_ids_sample": workflow_ids[:20],
        "users_simulated": len(users_seen),
        "errors_sample": [
            {
                "request_index": item.index,
                "user_index": item.user_index,
                "http_status": item.http_status,
                "done_status": item.done_status,
                "error": item.error,
            }
            for item in failed_results[:20]
        ],
    }


def print_human_summary(summary: dict[str, Any]) -> None:
    """
    Print a concise human-readable summary to stdout.

    Why:
        Developers often need a quick verdict without opening JSON artifacts.
    How:
        Render key counters and latency metrics in plain text.
    Usage example:
        Called from `main()` after load execution.
    """

    latency = summary["latency_seconds"]
    print("\n=== Ingestion Load Test Summary ===")
    print(f"Requests: {summary['total_requests']}")
    print(f"Simulated users: {summary['users_simulated']}")
    print(f"Success:  {summary['successful_requests']} | Failed: {summary['failed_requests']}")
    print(f"Success rate: {summary['success_rate'] * 100:.2f}%")
    print(f"Elapsed: {summary['elapsed_seconds']:.2f}s | Throughput: {summary['throughput_req_per_sec']:.2f} req/s")
    print(f"Latency (s): min={latency['min']:.2f} avg={latency['avg']:.2f} p50={latency['p50']:.2f} p95={latency['p95']:.2f} p99={latency['p99']:.2f} max={latency['max']:.2f}")
    print(f"Unique workflow IDs observed: {summary['workflow_ids_count']}")
    if summary["errors_sample"]:
        print("Sample errors:")
        for entry in summary["errors_sample"][:5]:
            print(f"- user={entry['user_index']} request={entry['request_index']} status={entry['http_status']} done={entry['done_status']} error={entry['error']}")


def load_user_tokens(tokens_file: str) -> list[str]:
    """
    Load optional per-user bearer tokens from a text file.

    Why:
        Multi-user load tests may need distinct auth identities to exercise access
        control and per-user scheduling behavior.
    How:
        Read non-empty lines from the provided file and normalize them as bearer
        authorization header values.
    Usage example:
        `tokens = load_user_tokens(\"./tokens.txt\")`
    """

    if not tokens_file:
        return []
    path = Path(tokens_file).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise ValueError(f"User tokens file not found: {path}")
    tokens = []
    for line in path.read_text(encoding="utf-8").splitlines():
        token = line.strip()
        if not token:
            continue
        tokens.append(f"Bearer {token}")
    return tokens


def resolve_total_requests(args: argparse.Namespace) -> int:
    """
    Resolve total request count from total or per-user CLI options.

    Why:
        Multi-user scenarios are easier to configure with requests per user.
    How:
        When `--requests-per-user` is set, compute users * requests-per-user;
        otherwise keep `--requests`.
    Usage example:
        `requests_total = resolve_total_requests(args)`
    """

    if args.requests_per_user > 0:
        return max(1, args.users) * args.requests_per_user
    return max(1, args.requests)


async def main_async(args: argparse.Namespace) -> dict[str, Any]:
    """
    Execute the load scenario and return the final summary.

    Why:
        Keeps async orchestration separate from CLI plumbing.
    How:
        Resolve input files, run load tasks, aggregate metrics.
    Usage example:
        Called by sync `main()` via `asyncio.run`.
    """

    files = collect_files(args)
    started = time.perf_counter()
    results = await run_load(args, files)
    finished = time.perf_counter()
    return build_summary(results=results, started_at=started, finished_at=finished)


def main() -> int:
    """
    CLI entrypoint for ingestion load testing.

    Why:
        Provide a single command developers can run locally or in CI smoke jobs.
    How:
        Parse args, run async campaign, print summary, optionally write JSON report,
        and return non-zero on failures.
    Usage example:
        `uv run python tests/scripts/temporal_ingestion_load_test.py --help`
    """

    args = parse_args()
    try:
        summary = asyncio.run(main_async(args))
    except Exception as exc:  # noqa: BLE001
        print(f"Load test failed before completion: {type(exc).__name__}: {exc}")
        return 2

    print_human_summary(summary)
    print("\nJSON summary:")
    print(json.dumps(summary, indent=2))

    if args.report_json:
        report_path = Path(args.report_json).expanduser().resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"\nReport written to: {report_path}")

    return 0 if summary["failed_requests"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
