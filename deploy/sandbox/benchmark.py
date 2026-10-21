#!/usr/bin/env python3
"""Measure ready or on-demand broker request-to-result latency."""

from __future__ import annotations

import argparse
import json
import os
import time
from urllib.request import Request, urlopen


def broker_state(base_url: str) -> dict[str, int]:
    with urlopen(f"{base_url}/healthz", timeout=5) as response:
        return json.load(response)


def capacity_available(state: dict[str, int], mode: str) -> bool:
    if mode == "ready":
        return state.get("ready", 0) > 0
    return state.get("allocated", 0) < state.get("limit", 0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--capacity-timeout", type=float, default=120)
    parser.add_argument("--mode", choices=("ready", "cold"), default="cold")
    parser.add_argument("--target-p95", type=float)
    args = parser.parse_args()
    if args.samples < 20:
        parser.error("at least 20 samples are required")
    if args.target_p95 is not None and args.target_p95 <= 0:
        parser.error("--target-p95 must be positive")
    base_url = os.environ["FRED_SANDBOX_BROKER_URL"].rstrip("/")
    token = os.environ["FRED_SANDBOX_BROKER_TOKEN"]
    initial_state = broker_state(base_url)
    warm_target = initial_state.get("warm_target")
    if (args.mode == "cold" and warm_target != 0) or (
        args.mode == "ready" and (warm_target is None or warm_target == 0)
    ):
        parser.error("benchmark mode does not match the broker warm-pool configuration")
    if args.mode == "ready" and initial_state.get("cold_on_miss") != 0:
        parser.error("ready mode requires SANDBOX_COLD_START_ON_MISS=false")
    samples: list[float] = []
    for _ in range(args.samples):
        deadline = time.monotonic() + args.capacity_timeout
        while not capacity_available(broker_state(base_url), args.mode):
            if time.monotonic() >= deadline:
                raise TimeoutError("sandbox capacity did not become available")
            time.sleep(0.1)
        request = Request(
            f"{base_url}/v1/execute",
            data=json.dumps({"language": "python", "code": "print('ok')"}).encode(),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        start = time.perf_counter()
        with urlopen(request, timeout=480) as response:
            result = json.load(response)
        elapsed = time.perf_counter() - start
        if result.get("exit_code") != 0 or result.get("stdout") != "ok\n":
            raise RuntimeError("sandbox benchmark returned an unexpected result")
        samples.append(elapsed)
    ordered = sorted(samples)
    p50 = ordered[(len(ordered) - 1) // 2]
    p95 = ordered[(95 * len(ordered) + 99) // 100 - 1]
    summary = f"mode={args.mode} samples={len(samples)} p50={p50:.3f}s p95={p95:.3f}s"
    if args.target_p95 is not None:
        summary += f" target=<{args.target_p95:.3f}s"
    print(summary)
    return 0 if args.target_p95 is None or p95 < args.target_p95 else 1


if __name__ == "__main__":
    raise SystemExit(main())
