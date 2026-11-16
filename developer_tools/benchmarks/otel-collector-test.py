# /// script
# requires-python = ">=3.11"
# dependencies = ["opentelemetry-proto==1.45.1", "protobuf==6.33.5"]
# ///
"""Synthetic integration against the pinned real Collector; never contacts Fred.

Run: uv run --script otel-collector-test.py /private/fresh-synthetic-directory
"""

import base64
import copy
import gzip
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from google.protobuf.json_format import MessageToDict, ParseDict
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)

HERE = Path(__file__).resolve().parent
SECRET = "SYNTHETIC_PRIVATE_SENTINEL"
TRACE = "0123456789abcdef0123456789abcdef"
ROOT = "1111111111111111"
START = 1794830400000000000  # 2026-11-16T12:00:00Z


def attr(key, value):
    return {
        "key": key,
        "value": value if isinstance(value, dict) else {"stringValue": value},
    }


def spans(message):
    return [
        s
        for r in message.resource_spans
        for scope in r.scope_spans
        for s in scope.spans
    ]


def identities(message):
    return sorted(
        (s.trace_id.hex(), s.span_id.hex(), s.parent_span_id.hex())
        for s in spans(message)
    )


def parse_otlp(value):
    # OTLP JSON uses hex IDs, unlike the generic protobuf JSON base64 mapping.
    def ids(node):
        if isinstance(node, dict):
            return {
                k: base64.b64encode(bytes.fromhex(v)).decode()
                if k in ("traceId", "spanId", "parentSpanId")
                else ids(v)
                for k, v in node.items()
            }
        if isinstance(node, list):
            return [ids(v) for v in node]
        return node

    return ParseDict(ids(value), ExportTraceServiceRequest())


def fixture():
    records = []
    for index in range(1, 7):
        records.append(
            {
                "traceId": TRACE,
                "spanId": f"{index + 1:016x}",
                "parentSpanId": ROOT if index == 1 else "0000000000000002",
                "name": SECRET + "_name",
                "kind": 3,
                "traceState": "secret=" + SECRET,
                "startTimeUnixNano": str(START + index * 10000000),
                "endTimeUnixNano": str(START + 500000000 + index * 10000000),
                "attributes": [
                    attr(
                        "fred.operation",
                        "agent.http" if index == 1 else "v2.react.model",
                    ),
                    attr("fred.category", "runtime" if index == 1 else "llm"),
                    attr("peer.service", "llm"),
                    attr("fred.outcome", "success"),
                    attr("first_chunk_ms", {"doubleValue": 25.5}),
                    attr("http.response.status_code", {"intValue": "200"}),
                    attr(SECRET + "_key", SECRET),
                    attr("langfuse.observation.model.name", "synthetic-model"),
                    attr("langfuse.observation.type", "generation"),
                    attr(
                        "langfuse.observation.usage_details", '{"input":3,"output":2}'
                    ),
                    attr(
                        "langfuse.observation.metadata",
                        json.dumps({"synthetic": SECRET}),
                    ),
                ],
                "status": {"code": 2, "message": SECRET + "_status"},
                "events": [
                    {
                        "name": SECRET,
                        "timeUnixNano": str(START),
                        "attributes": [attr(SECRET, SECRET)],
                    }
                ],
                "links": [
                    {
                        "traceId": TRACE,
                        "spanId": ROOT,
                        "traceState": "secret=" + SECRET,
                        "attributes": [attr(SECRET, SECRET)],
                    }
                ],
            }
        )
    # Wrong types, nested values and sensitive values under otherwise allowed keys.
    poison = [
        {"stringValue": SECRET},
        {"arrayValue": {"values": [{"stringValue": SECRET}]}},
        {"kvlistValue": {"values": [attr(SECRET, SECRET)]}},
        {"bytesValue": "U1lOVEhFVElDX1BSSVZBVEVfU0VOVElORUw="},
    ]
    for index, value in enumerate(poison, 2):
        records[index]["attributes"] = [
            attr(k, value)
            for k in (
                "fred.operation",
                "fred.category",
                "peer.service",
                "fred.outcome",
                "fred.cache",
                "http.request.method",
                "http.response.status_code",
                "first_chunk_ms",
                "duration_ms",
            )
        ]
    resource = {
        "resource": {
            "attributes": [attr("service.name", "fred-agents"), attr(SECRET, SECRET)],
            "entityRefs": [{"schemaUrl": SECRET, "type": SECRET, "idKeys": [SECRET]}],
        },
        "schemaUrl": SECRET + "_resource_schema",
        "scopeSpans": [
            {
                "schemaUrl": SECRET + "_scope_schema",
                "scope": {
                    "name": SECRET,
                    "version": SECRET,
                    "attributes": [attr(SECRET, SECRET)],
                },
                "spans": records,
            }
        ],
    }
    other = copy.deepcopy(resource)
    other["resource"]["attributes"][0] = attr("service.name", SECRET)
    other["scopeSpans"][0]["spans"] = [copy.deepcopy(records[0])]
    other["scopeSpans"][0]["spans"][0]["spanId"] = "0000000000000009"
    # Empty resource/scope must also be sanitized before serialization.
    empty = copy.deepcopy(resource)
    empty["scopeSpans"][0]["spans"] = []
    return parse_otlp({"resourceSpans": [resource, other, empty]})


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def read_file(path):
    result = ExportTraceServiceRequest()
    for line in path.read_text().splitlines():
        part = parse_otlp(json.loads(line))
        result.resource_spans.extend(part.resource_spans)
    return result


def assert_safe(path, expected):
    data = read_file(path)
    assert identities(data) == identities(expected), (
        "Trace/span/parent identity changed"
    )
    raw = path.read_bytes()
    assert SECRET.encode() not in raw and b"U1lOVEhFVElD" not in raw, (
        "Sensitive sentinel reached disk"
    )
    assert b"langfuse" not in raw and b"synthetic-model" not in raw
    for resource in data.resource_spans:
        assert not resource.schema_url and not resource.resource.entity_refs
        assert [
            (a.key, a.value.string_value) for a in resource.resource.attributes
        ] in ([("service.name", "fred-agents")], [("service.name", "unknown")])
        for scope in resource.scope_spans:
            assert (
                not scope.schema_url
                and not scope.scope.name
                and not scope.scope.version
            )
            assert not scope.scope.attributes
            for span in scope.spans:
                assert span.name in (
                    "agent.http",
                    "v2.react.model",
                    "runtime.operation",
                    "agent.stream",
                    "tool.invoke",
                    "mcp.http",
                )
                assert (
                    not span.events
                    and not span.links
                    and not span.trace_state
                    and not span.status.message
                )
    assert path.stat().st_mode & 0o077 == 0
    return data


def main():
    os.umask(0o077)
    root = Path(sys.argv[1]).resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    received = []
    failing = threading.Event()

    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self):
            assert self.path == "/api/public/otel/v1/traces"
            assert self.headers["Authorization"] == "Basic synthetic-only"
            body = self.rfile.read(int(self.headers["Content-Length"]))
            if self.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
            if not failing.is_set():
                received.append(ExportTraceServiceRequest.FromString(body))
            self.send_response(503 if failing.is_set() else 200)
            self.send_header("Content-Type", "application/x-protobuf")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *_):
            pass

    receiver = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
    thread = threading.Thread(target=receiver.serve_forever, daemon=True)
    thread.start()
    request = fixture()
    timings = {}
    native_python = os.environ.get("FRED_OTEL_TEST_PYTHON")
    modes = ["file-only", "multidestination", "langfuse-unavailable"]
    if native_python:
        modes.insert(2, "native-producer")
    try:
        for mode in modes:
            directory = root / mode
            port = free_port()
            env = {
                k: v
                for k, v in os.environ.items()
                if not k.startswith("FRED_LANGFUSE_")
            }
            env["FRED_OTEL_PORT"] = str(port)
            if mode != "file-only":
                env["FRED_LANGFUSE_OTLP_ENDPOINT"] = (
                    f"http://127.0.0.1:{receiver.server_port}/api/public/otel/v1/traces"
                )
                env["FRED_LANGFUSE_AUTHORIZATION"] = "Basic synthetic-only"
            command = [str(HERE / "otel-collector.sh")]
            subprocess.run(command + ["start", str(directory)], env=env, check=True)
            expected = request
            offset = len(received)
            try:
                if mode == "langfuse-unavailable":
                    failing.set()
                t0 = time.monotonic()
                if mode == "native-producer":
                    env["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"] = (
                        f"http://127.0.0.1:{port}/v1/traces"
                    )
                    env["OTEL_SERVICE_NAME"] = "fred-agents"
                    subprocess.run(
                        [native_python, str(HERE / "otel-collector-native-emitter.py")],
                        env=env,
                        check=True,
                        timeout=20,
                    )
                else:
                    body = request.SerializeToString()
                    with urlopen(
                        Request(
                            f"http://127.0.0.1:{port}/v1/traces",
                            body,
                            {"Content-Type": "application/x-protobuf"},
                        ),
                        timeout=3,
                    ) as reply:
                        assert reply.status == 200
                timings[mode + "_accept_seconds"] = time.monotonic() - t0
                if mode in ("multidestination", "native-producer"):
                    deadline = time.monotonic() + 5
                    while len(received) == offset and time.monotonic() < deadline:
                        time.sleep(0.05)
                    assert len(received) == offset + 1, (
                        "Missing or duplicated Langfuse export"
                    )
                    original = received[offset]
                    if mode == "multidestination":
                        assert identities(original) == identities(request)
                        assert original == request, (
                            "Langfuse payload was mutated by file sanitization"
                        )
                        assert spans(original)[0].name == SECRET + "_name", (
                            "File transform mutated Langfuse branch"
                        )
                        assert SECRET in str(original) and "synthetic-model" in str(
                            original
                        )
                    else:
                        expected = original
                        exported = spans(original)
                        assert (
                            len(exported) == 5
                            and len({s.span_id for s in exported}) == 5
                        )
                        assert {s.trace_id.hex() for s in exported} == {"a" * 32}
                        by_name = {s.name: s for s in exported}
                        assert by_name["agent.http"].parent_span_id.hex() == "b" * 16
                        for child, parent in (
                            ("agent.stream", "agent.http"),
                            ("v2.react.model", "agent.stream"),
                            ("tool.invoke", "agent.stream"),
                            ("mcp.http", "tool.invoke"),
                        ):
                            assert (
                                by_name[child].parent_span_id == by_name[parent].span_id
                            )
                        model_attrs = {
                            a.key: a.value.string_value
                            for a in by_name["v2.react.model"].attributes
                        }
                        assert (
                            model_attrs["langfuse.observation.model.name"]
                            == "synthetic-model"
                        )
                        assert json.loads(
                            model_attrs["langfuse.observation.usage_details"]
                        ) == {"input": 3, "output": 5}
                        assert json.loads(
                            model_attrs["langfuse.observation.cost_details"]
                        ) == {"total": 0.1}
                        assert (
                            json.loads(model_attrs["langfuse.observation.metadata"])[
                                "secret"
                            ]
                            == "synthetic-private-metadata"
                        )
                        assert "synthetic-private" in str(original)
                    (root / (mode + "-fake-langfuse.json")).write_text(
                        json.dumps(MessageToDict(original), indent=2)
                    )
                # File must progress while the other destination is failing.
                deadline = time.monotonic() + 5
                while (
                    not (directory / "traces.otlp.jsonl").stat().st_size
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.05)
                assert (directory / "traces.otlp.jsonl").stat().st_size > 0
            finally:
                t0 = time.monotonic()
                subprocess.run(
                    command + ["flush", str(directory)], env=env, check=True, timeout=20
                )
                timings[mode + "_stop_seconds"] = time.monotonic() - t0
            assert_safe(directory / "traces.otlp.jsonl", expected)
            if mode == "native-producer":
                raw = (directory / "traces.otlp.jsonl").read_text()
                assert all(
                    value not in raw
                    for value in (
                        "synthetic-private",
                        "synthetic-session",
                        "synthetic-user",
                    )
                )
            subprocess.run(command + ["retrieve", str(directory)], check=True)
        # A deliberately synthetic scenario, separate from all real campaign files.
        run = {
            "kind": "run",
            "schema_version": "fred.bench.scenario.v1",
            "campaign_id": "synthetic-collector",
            "target": "weaver",
            "turns": 1,
            "concurrency_steps": [1],
            "identity_mode": "per-conversation",
        }
        turn = {
            "kind": "turn",
            "schema_version": "fred.bench.scenario.turn.v1",
            "campaign_id": "synthetic-collector",
            "trace_id": TRACE,
            "span_id": ROOT,
            "target": "weaver",
            "turn": 1,
            "step": 1,
            "concurrency": 1,
            "client_id": 1,
            "first_turn": True,
            "started_at": "2026-11-16T12:00:00Z",
            "execution_started_at": "2026-11-16T12:00:00Z",
            "final_at": "2026-11-16T12:00:01Z",
            "stream_closed_at": "2026-11-16T12:00:01Z",
            "outcome": "success",
            "performance_outcome": "success",
            "integrity": "not_checked",
        }
        (root / "multidestination" / "synthetic-scenario.jsonl").write_text(
            json.dumps(run) + "\n" + json.dumps(turn) + "\n"
        )
        (root / "synthetic-validation.json").write_text(
            json.dumps(
                {
                    "synthetic_only": True,
                    "collector_version": "0.165.0",
                    "protocol_spans_per_mode": len(spans(request)),
                    "native_span_count": 5 if native_python else None,
                    "checks": [
                        "file allowlist",
                        "same IDs/parents",
                        "Langfuse fanout isolation",
                        "bounded failed destination",
                        "private file",
                    ],
                    "native_python_tested": bool(native_python),
                    "timings": timings,
                    "real_langfuse_tested": False,
                    "fred_or_k3d_tested": False,
                },
                indent=2,
            )
        )
        print(f"PASS: synthetic Collector integration in {root}")
    finally:
        receiver.shutdown()
        receiver.server_close()
        thread.join(timeout=2)


if __name__ == "__main__":
    try:
        main()
    except HTTPError as error:
        print(error.read().decode(errors="replace"), file=sys.stderr)
        raise
