# Fred bench

```bash
./bench
```

Choose **Diagnostic** or **Performance**, connect in your browser, then select your
**space** and **agent** by name. Before you start, the CLI explains the load, warm-up,
client KPIs and server traces, and displays the model currently selected by Fred.
Afterwards it prints a compact recap and the saved JSON/JSONL paths. It does not
generate HTML or open a result browser. Use arrows and Enter; Ctrl+C stops the run and preserves
observations already recorded. `NO_COLOR=1` disables colors; a plain terminal uses
numbered choices.

```bash
./bench run --origin URL    # Choose another Fred platform
./bench --help
```

Build once inside the checkout, and repeat after updating the Go sources:

```bash
cd developer_tools/benchmarks
./build.sh                  # Builds ./bench; no installation or deployment
```

Help accepts `-h`, `--h`, `-help`, `--help` and `help`, including after `run`
or `report`; `./bench help run` and `./bench help report` show command usage.
CLI prompts and diagnostics are in English. Help writes to stdout and exits 0
without connecting or creating files; usage errors write to stderr and exit 2.

Go 1.24 is required; the build respects `GOTOOLCHAIN`. Nothing is installed into
`~/.local/bin`, and no shell configuration or `PATH` is changed.

**Questions.** “General English” covers explanation, arithmetic, summarization,
rewriting, reasoning and conversation follow-up. “Documents” asks only for a topic
(such as RAGuard) and constructs ten English questions requesting evidence and
citations. You can preview the selected questions before starting. Generic
questions do not guarantee document retrieval. The benchmark measures performance
and stream/history integrity; it does not grade the factual quality of answers.
The agent's Fred configuration selects models, suppliers and capabilities. The
client has no mock-specific contract and never calls a supplier directly.

**Model.** Bench asks Fred for the current model selection before confirmation,
including defaults/fallbacks; a saved recommendation alone is not authoritative.
The model name and configured source are displayed without credentials. This is a
preview, not a model pin: Fred admits each turn using its current configuration.
Bench does not infer whether a source is a paid provider or a mock from a model
name, and never changes it. Select the desired model on the agent in Fred.

**What the files mean:**

| File | Contents |
| --- | --- |
| `conversation.jsonl` | Measured turn timings/outcomes, run settings and verification records; one JSON record per line |
| `summary.json` | Aggregate client KPIs: counts, latency, throughput and errors |
| `traces.otlp.jsonl` | Optional server trace snapshot, correlated with sampled turns |
| `warmup/conversation.jsonl` | Extra warm-up observations, excluded from measured KPIs |

Client KPIs cover every measured question regardless of trace sampling. Latency
statistics use successful turns with observed timestamps; errors are counted
separately. Traces help explain internal calls; they are not needed for client KPIs.

**Connection.** Browser login uses the platform's public Keycloak configuration,
authorization code with PKCE and a temporary loopback callback. The public client
must allow `http://127.0.0.1:<port>/callback`; the local factory's `app` client does.
Keycloak browser SSO avoids repeated credential entry. Access and refresh tokens
stay in memory and are renewed during the session, never saved in preferences or
reports. This guided flow currently supports Keycloak with the `sub` identity
claim. Local HTTP issuer aliases `keycloak` and `app-keycloak` are accepted only
when every resolved address is loopback; other nonlocal issuers require HTTPS.
Existing advanced bearer/credential-file commands remain available.
Onboarding and current terms must be completed in Fred; bench never accepts them
or approves an agent's human-input request automatically.

**Results.** Private timestamped directories under
`.bench/` alongside the binary hold client measurements, this run's
filtered traces and `summary.json`. Preferences remember the platform, selected
space/agent and latest run, without credentials. Questions and answers are not
exported. Conversations remain available in Fred unless `--cleanup` is selected. “Run again”
creates new conversations and a new result directory. The binary and `.bench/` are ignored by
Git. `BENCH_STATE_DIR` can explicitly select another absolute results directory.

**Traces.** Automatic retrieval targets the existing local deployment at
`http://weaver.localhost:8088`, context `k3d-fred`, namespace `fred-infra`. It requires
`kubectl`, Docker access and the already configured collector/PVC described in
[k3d collection](#k3d-collection-separate-operator-rollout). Discovery reads the
volume and node dynamically; collection reads current and rotated files without
creating pods, restarting services or deploying anything. Only this run's spans
and report-safe attributes are retained. It waits briefly for export stabilization;
a snapshot is not an acknowledged SDK flush or proof of exhaustive instrumentation.
The terminal shows how many sampled questions have correlated traces. If the collector is not
accessible, bench offers to exit or explicitly continue with client timings only.
Other deployments can use `bench run --client-only` and the offline trace import
below. No missing span is interpreted as zero time.

## Diagnostic or performance

| Mode | Measured questions | Concurrent conversations | Warm-up | Traces requested |
| --- | ---: | ---: | ---: | ---: |
| `diagnostic` | 10 | 1 | 0 | 100% |
| `performance` | 1000 | 10 | 20, excluded | 0% |

```bash
./bench run --mode diagnostic
./bench run --mode performance
./bench run --mode performance --requests 10000 --concurrency 20 --cleanup
./bench run --mode performance --trace-sample 0.01
```

The same ten questions repeat in **new conversations of at most ten turns**; the
last conversation can be shorter. `--requests` counts Fred agent turns, not model
calls. `--concurrency` bounds simultaneous conversations under the same signed-in
identity. This is a closed-loop workload: each conversation waits for its answer
before sending its next question. It does not impose a fixed arrival rate or
simulate distinct users. A failed turn stops that conversation; other conversations
continue. There are no automatic benchmark retries; unstarted turns remain visible.

`--warmup 0` disables warm-up. Otherwise warm-up must succeed before measurement;
its separate `warmup/` records never enter the measured KPIs. Choose `--cleanup` to
request deletion of this run's new conversations after measurement and history
verification, including warm-up. Deletion is asynchronous; the receipt does not
prove physical disk reclamation. By default conversations remain available in Fred.

**Statistics independent of traces.** `summary.json` contains counts, errors,
timeouts, successful turns/second, and exact mean/P50/P95/P99/max for successful
turns, including first-text and full-stream latencies. Each metric has its own
sample count; absent observations are not zero. Raw `conversation.jsonl` preserves
all observed measured turns, including failures. CPU and RAM are not collected. Throughput covers the measured load window, including session setup
and client scheduling/writes, excluding warm-up, initial login, history checks,
cleanup and trace retrieval. Compare like-for-like deployments and model settings.

**Sampling at the source.** Bench sends W3C `traceparent` sampled flags: `01` for
selected turns, `00` otherwise. `--trace-sample 0.01` randomly selects about 1% of
turns, while client statistics still cover the whole measured run. Setup, history
and cleanup requests carry `00`. Weaver services must select
`observability.tracer: diagnostic` and `diagnostic.collector_endpoint` in their YAML
configuration. That backend fixes parent-based sampling with new roots dropped;
no SDK environment settings are needed. Prepare the environment once, then change
the bench's sampling between runs without restarting Fred. A sampled header is
not an authorization mechanism; other clients can send one in the same development
environment. The bench never changes server configuration.
`--client-only` skips
trace retrieval only; use `--trace-sample 0` to request no turn trace recording.
Missing server spans are never interpreted as zero server work.

**Bounded overhead and storage.** Performance mode batches JSONL writes in a
64 KiB buffer, syncing at most once per second while records arrive and flushing
on normal/Ctrl+C exit. An abrupt process/machine failure can lose buffered data.
Progress refreshes once per second; no per-turn console output. Limits: 50,000
measured turns, 256 concurrent conversations, 1,000 warm-up turns, 120 MiB per raw
file and 128 MiB trace snapshots. Bench refuses another run when
existing `.bench/` files exceed 512 MiB; archive old runs yourself. This is a
per-run guard, not a filesystem quota for simultaneous bench processes. The existing
k3d collector rotates files separately. Sampling does not disable application logs,
conversation persistence, or unrelated traffic; those retain their own costs.

**Using the OpenAI-compatible mock.** Select a Fred agent whose model uses the
mock's URL, exactly as you select an agent using Mistral. No mock flag, marker or
special questions belong in bench. In the mock repository, `reference` produces
one fixed text response after 1000 ms; `streaming` produces 100 fragments after
1000 ms, spaced by 50 ms. Server-side `config.benchmark.initialDelayMs` and
`fragmentIntervalMs` configure the pacing in Helm values (see the mock README).
Use `reference` first for a simple baseline and `streaming` for sustained SSE.
These profiles answer text only, so they do not exercise retrieval/tool calls or
reasoning quality. Watch mock CPU and its periodic summaries: a saturated mock
can be the bottleneck. Fragments are not tokens; no token throughput is invented.

## Advanced and automated use

The same Go engine supports Weaver managed SSE, Swift managed/direct SSE and the
historical Swift WebSocket commands. With explicit legacy flags, `-target=swift`
remains the default; unsupported Weaver combinations fail before network access.
`-questions-file` accepts a JSON array of 1–100 questions, sent unchanged in order.
`questions.example.json` is an optional RAGuard example, not the interactive default.
`make conversation` remains a scripting shortcut with explicit space/agent IDs,
output directory and an existing Fred user bearer in `AGENTIC_TOKEN`.

## Optional legacy HTML tool

HTML rendering is separate from the guided benchmark. Existing reports are kept;
no HTML is generated by `./bench` or `./bench run`. The explicit offline command
remains available for older workflows:

```bash
cd developer_tools/benchmarks
make report DIR=/path/to/results
# Equivalent; Go 1.24.0 must already be installed/cached for offline use:
GOTOOLCHAIN=go1.24.0 GOPROXY=off go run . report -input /path/to/results
# Keep an earlier report and choose another output:
make report DIR=/path/to/results OUTPUT=/path/to/results/report-2.html
```

Open `report.html` directly in a browser. No server, CDN, library, fetch or network
resource is required; JavaScript must be enabled. `make report` defaults to the
Go 1.24.0 toolchain while respecting an explicit `GOTOOLCHAIN` override. It does
not change the existing build/run targets. The `report` subcommand dispatches
before benchmark flags, credentials or runtime initialization, and never starts
load or contacts Fred. Toolchain/dependencies must be installed beforehand;
set `GOPROXY=off` to forbid dependency downloads during the command.

The input is a flat directory of canonical conversation scenario JSONL files:
first record `kind=run`, `schema_version=fred.bench.scenario.v1`, followed by
`fred.bench.scenario.turn.v1` turns and optional step/final records. Each campaign
must appear once. Several targets, runs and concurrency levels may share the
directory. Identity preparation JSONL is recognized by its record kinds and
terminal `fred.bench.preparation.v1` schema and ignored, regardless of filename.
Other JSONL formats, mixed campaigns, duplicate turns and unsupported legacy
formats fail explicitly. JSON, receipts, API captures and private configuration
files are not read, except the optional explicit OTLP input below. A malformed scenario line preserves the preceding observations
and marks the report incomplete; a missing final summary never becomes successful.
An inconsistent summary is marked incomplete; observed history records establish
history counts. Input files are never changed. The output must be a new `.html`
file, created with mode `0600`; existing files and links are never overwritten.
Remove a generated report deliberately or choose another `-output` to regenerate.

The French interface compares runs, filters concurrency and first/following turns,
shows mean/median/P95/P99/max with sample counts, and paginates the turn/error table.
Execution latencies start at execution; total latencies also include Weaver's
per-turn preparation, which Swift does not perform. Only successful turns with
observed timestamps contribute to latency statistics. N=0 means **not measured**,
never zero latency. Duration and history cover whole selected levels, even when
filtering first/following turns; run status and authentication cover the whole run.
Per-turn charts show medians across clients; per-concurrency charts show medians
across the selected turns. Graphs display at most 2,000 points and 16 legend items,
with an explicit notice; summaries and the 50-row paginated table retain all data.

Bounds are 128 MiB of JSONL, 2 MiB per record, 64 runs and 100,000 turns. This covers
campaigns such as 500 conversations with 10 turns without unbounded DOM growth.
Different identity modes produce a comparability warning. Keep agent settings,
questions and deployment conditions comparable yourself; the client does not infer them.
Deployed versions, machines and model configuration are not inferred from the
checkout. Only canonical campaign/trace/span IDs, bounded error
categories, enums, counts and timings enter the report. Identities, conversation
IDs, prompts, arbitrary error strings and unknown fields are omitted. JSON is
escaped through `html/template` in JavaScript context. No conversation link is
invented from pseudonymous identifiers. This report distinguishes client observations and imported server spans; neither
establishes production capacity. Client timing is not server admission time.

### Local collection: one turn, then a campaign

These are **operator-run commands**, not a record of a Fred run. Use an already
configured local Weaver installation, its existing credentials/space/instance,
and the selected agent configuration. This recipe neither
creates identities nor configures agents/models. Prerequisites: Docker on Linux,
Go 1.24.0 and Go dependencies cached, and dependencies for the normal service
startup commands. No Langfuse installation is required.

From the checkout, prepare a fresh private destination and start collection:

```bash
cd developer_tools/benchmarks
umask 077
export RESULTS="$(mktemp -d "${TMPDIR:-/tmp}/fred-traced-run.XXXXXX")"
make traces-start TRACE_DIR="$RESULTS"
```

In both services' existing YAML configuration, select:

```yaml
observability:
  tracer: diagnostic
  diagnostic:
    collector_endpoint: http://127.0.0.1:4318/v1/traces
```

Preserve the rest of each configuration, including KPI settings. Restart the two
services with their normal commands (`make -C apps/control-plane run` and
`make -C apps/fred-agents run`). Report generation never starts or reconfigures
Fred; normal startup prerequisites still apply. Diagnostic collection records
only sampled request contexts and never prompts, answers or identity metadata.

Back in the benchmark terminal, set `WEAVER_ORIGIN`, `WEAVER_SPACE`,
`WEAVER_INSTANCE` and `CREDENTIAL_FILE` to the existing local setup's values.
The public origin must already route both services. Check a single turn first;
only continue with the campaign if it succeeded:

```bash
: "${WEAVER_ORIGIN:?}" "${WEAVER_SPACE:?}" "${WEAVER_INSTANCE:?}" "${CREDENTIAL_FILE:?}"
GOTOOLCHAIN=go1.24.0 make run ARGS="-scenario=conversation -target=weaver -protocol=sse \
  -fred-origin=$WEAVER_ORIGIN -space-id=$WEAVER_SPACE \
  -agent-instance-id=$WEAVER_INSTANCE -credential-file=$CREDENTIAL_FILE \
  -concurrency-steps=1 -requests-per-client=1 -trace-turns \
  -delete-session=false \
  -raw-report=$RESULTS/weaver-one-turn.jsonl"
# Then a distinct ten-turn campaign, using the same trace destination:
GOTOOLCHAIN=go1.24.0 make run ARGS="-scenario=conversation -target=weaver -protocol=sse \
  -fred-origin=$WEAVER_ORIGIN -space-id=$WEAVER_SPACE \
  -agent-instance-id=$WEAVER_INSTANCE -credential-file=$CREDENTIAL_FILE \
  -concurrency-steps=1 -requests-per-client=10 -trace-turns \
  -delete-session=false \
  -raw-report=$RESULTS/weaver-campaign.jsonl"
```

After the campaign, let the producers finish exporting **before** stopping the
Collector. Gracefully stop those operator-started services and wait for their
shutdown/SDK drain to finish. A one-second scheduled batch interval alone is not
a flush acknowledgement; unavailable destinations and full queues can lose spans.
Python shutdown has a 30-second join bound; Rust has a five-second shutdown wait.
Only then close/retrieve the file and generate the report:

```bash
make traces-flush TRACE_DIR="$RESULTS"  # graceful Collector stop, not an SDK flush
make traces-retrieve TRACE_DIR="$RESULTS"
GOPROXY=off make report DIR="$RESULTS"
xdg-open "$RESULTS/report.html"
```

Expected: two separate runs (one and ten turns), client observations and, for
instrumented successful exports, matching server spans. Use **Explorer** to inspect
parent links and overlapping timings, then filter runs to compare component
coverage. Missing spans remain missing; inspect producer/Collector errors rather
than interpreting them as zero cost. Langfuse real ingestion and Fred/k3d journeys
require their own operator validation; synthetic integration proves neither.

No special engine or concurrency policy is introduced. Remove `-trace-turns`
for the existing measurement behavior. With this opt-in, each attempted execution
gets a fresh W3C trace ID and root span ID **before** token refresh; they are
optional `trace_id`/`span_id` fields on `fred.bench.scenario.turn.v1`. Requests
inside the turn carry `traceparent: 00-<trace_id>-<span_id>-01`, without baggage.
The root is an observation from existing client timestamps, not an exported OTel
span; the Go client neither installs an SDK nor exports telemetry. Initial login,
session opening, preflight, post-history and cleanup stay outside this correlation.
Refresh performed by a turn is measured separately; waiting for another refresh
is included in total turn latency, not in the individual Keycloak exchange.

Instrumentation must preserve these IDs to correlate server spans. Tracing is
opt-in and its overhead belongs to the run: compare targets with the same choice.
The Go flag cannot instrument an unchanged Swift deployment. Swift's existing
client phases remain comparable where their definitions match Weaver; server
coverage is not equivalent unless that Swift deployment actually exports the
same boundaries. Historical runs retain their client metrics with no invented
LLM, MCP or Control Plane timings.

### k3d collection (separate operator rollout)

Use the deployment factory's
[Weaver traces recipe](https://github.com/fred-agent/fred-deployment-factory/blob/weaver/docs/BENCHMARKS.md#diagnostic-traces).
Its opt-in collector reuses this directory's sanitization pipeline and stores
rotated OTLP JSONL on a PVC. Its explicit application VALUES overlay selects `observability.tracer: diagnostic`
and supplies the internal Collector endpoint, preserving credentials
and TLS configuration. In a pod, `127.0.0.1` means that pod, so the local endpoint
above cannot be used for k3d. Ordinary browser questions do not request diagnostic traces.
Use bench diagnostic mode to collect correlated turn measurements and spans.

### Collector configuration and optional Langfuse

The local collection recipe uses Docker on Linux with host networking and a
loopback-only OTLP/HTTP receiver. It pins **Collector contrib 0.165.0 and its image
digest** in [otel-collector.sh](otel-collector.sh); no Collector installation,
sudo, SQL, Fred restart or cluster action is performed by these commands.
Docker access and Python 3 are required. Choose a fresh directory owned by your
user with mode `0700`; the file is created as `0600` and the container runs as
your UID/GID. Ports are checked before startup (`FRED_OTEL_PORT`, default `4318`).
The container is temporary, has no restart policy, and only mounts the config
read-only and the private output directory for writing.

```bash
# Run from developer_tools/benchmarks, before an authorized instrumented run:
export TRACE_DIR="$HOME/.local/share/fred/traces-$(date +%Y%m%d-%H%M%S)"
make traces-start TRACE_DIR="$TRACE_DIR"
# Point the concerned producers to http://127.0.0.1:4318/v1/traces.
# After the run: flush the PRODUCER SDKs first (or gracefully stop those producers).
make traces-flush TRACE_DIR="$TRACE_DIR"
# traces-flush is a graceful Collector STOP: it drains batches and closes the file.
# traces-stop is equivalent; neither command flushes a still-running upstream SDK.
make traces-retrieve TRACE_DIR="$TRACE_DIR"
# Optional exclusive copy; refuses to overwrite COPY_TO:
make traces-retrieve TRACE_DIR="$TRACE_DIR" TRACE_OUTPUT=/private/COPY_TO.otlp.jsonl
make report DIR=/private/scenario-results TRACES="$TRACE_DIR/traces.otlp.jsonl" \
  OUTPUT=/private/scenario-results/report-with-traces.html
```

The file has a 1 s batch delay and 1 s buffered-write interval. Waiting alone is
not a completion guarantee: close the producers' SDK queues, then stop the
Collector. Shutdown is capped at 15 s; a forced stop returns failure and does not
claim complete delivery. File-only collection works without Langfuse credentials.
A new collection requires a new output directory. Retrieval is refused while
this recipe's Collector is running. `make report` never starts collection.

To add Langfuse, set these **before** `traces-start`; the optional
[overlay](otel-collector-langfuse.yaml) is then merged with the same receiver:

```bash
export FRED_LANGFUSE_OTLP_ENDPOINT='https://YOUR_LANGFUSE/api/public/otel/v1/traces'
# Supply the complete Basic header from your secret manager; do not paste keys in history.
export FRED_LANGFUSE_AUTHORIZATION  # value: Basic base64(public-key:secret-key)
make traces-start TRACE_DIR="$TRACE_DIR"
```

This forwards the original spans over HTTP/protobuf; trace IDs, span IDs and
parents remain identical. The Collector copies data for the mutating file branch,
so each destination receives identical span identities. Fred diagnostic producers
export technical fields only, even when this optional destination is configured. No Langfuse SDK/provider is installed in the Collector. This is OTLP
compatibility, not validation against a real Langfuse deployment. The endpoint
above is the native v3-compatible path (self-hosted Langfuse >= 3.22); a deployment
using Langfuse v4 realtime ingestion additionally needs its documented
`x-langfuse-ingestion-version: 4` header in the overlay. The script does not infer
or upgrade the remote deployment. Docker administrators can inspect container
environment variables; use a trusted local Docker daemon.

The Langfuse branch has an asynchronous queue of 128 requests with 2 consumers,
3 s request timeouts and at most 5 s of retries per request. A slow/unavailable
Langfuse destination can lose spans when the queue fills; it does not delay the
file exporter. Neither branch provides durable delivery after a crash. Avoid
unbounded collection: stop after the intended run; the local file has no rotation
so that the report consumes one complete file. The container is limited to
256 MiB; overload can lose telemetry and does not imply zero execution duration.

[otel-collector.yaml](otel-collector.yaml) filters **before any file write**. It
replaces span names with an allowlisted `fred.operation` (otherwise
`runtime.operation`), admits only closed category/peer/outcome/cache/method
values, numeric HTTP statuses and finite durations from 0 to 24 h. Resource
attributes retain only a closed `service.name`; an unknown name becomes
`unknown`. Scope names/versions/attributes, resource/scope schema URLs, events,
links, tracestate, status messages and all arbitrary attributes are removed.
A resource rebuild also removes `entity_refs`, which this version's OTTL cannot
address. IDs, parent relations, times and numeric OTLP kind/status/counters are
retained. Transform errors fail closed. Collector payload diagnostics are
suppressed to prevent a second sensitive file/log channel. The report's own
projection remains defense in depth for imports from other sources.

Migration from the earlier file-only example: replace direct `otelcol-contrib`
startup with `traces-start` (or supply the exact pinned config/environment), use
an entirely fresh private directory, and direct **all** Python/Rust exporters to
its OTLP endpoint. Move destination credentials to the optional Collector branch;
never point a producer at the file branch's old arbitrary-attribute recipe. Old
exports are not retroactively sanitized. Standalone Langfuse remains a separate runtime backend; diagnostic mode does not
export its identity, content or observation metadata.

The reproducible synthetic test uses Docker, `uv` and pinned protobuf dependencies.
It creates a fresh private directory, chooses free loopback ports, starts a fake
Langfuse receiver, sends nested spans with malicious sentinels in every supported
text channel (including entity references), tests unavailable-destination behavior,
compares IDs/parents and stops every test service. To also test the real Python
adapter, provide an already prepared runtime Python environment:

```bash
FRED_OTEL_TEST_PYTHON="$PWD/../../libs/fred-runtime/.venv/bin/python" \
  make traces-test TRACE_DIR="$HOME/.local/share/fred/otel-synthetic-$(date +%Y%m%d-%H%M%S)"
```

Without `FRED_OTEL_TEST_PYTHON`, only the protocol fixtures run. This test makes
no Fred conversation, k3d change or real Langfuse request. Its generated
`multidestination/synthetic-scenario.jsonl` is deliberately synthetic and must
remain separate from real results; the fixture omits campaign closure so the
report correctly labels it incomplete.

Sources for the pinned behavior: [file exporter](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/v0.165.0/exporter/fileexporter),
[transform processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/v0.165.0/processor/transformprocessor),
[resource rebuilding](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/v0.165.0/processor/groupbyattrsprocessor/attribute_groups.go),
[HTTP exporter](https://github.com/open-telemetry/opentelemetry-collector/tree/v0.165.0/exporter/otlphttpexporter),
[Langfuse OTLP](https://langfuse.com/integrations/native/opentelemetry) and
[OTLP JSON](https://opentelemetry.io/docs/specs/otlp/#json-protobuf-encoding).

The importer accepts `resourceSpans[].scopeSpans[].spans` exports, either one JSON
object or multiple JSONL objects; IDs are hexadecimal, timestamps are integer
nanoseconds (decimal strings or numbers). It discovers `traces.otlp.jsonl` beside
the scenario files, or accepts `report -traces FILE` / `make report TRACES=FILE`.
Files ending in `.otlp.jsonl` are excluded from the scenario scanner. A differently
named JSONL export must be passed with `-traces` so it is excluded as well. There
is no heuristic matching by timestamps, session or identity: joins require an
exact `traceId`. Parent links require exact `parentSpanId`, including the client
observation root. Missing parents, cycles, unknown categories and client/parent interval
discrepancies remain visible. A child outside its parent can reflect clock skew
or asynchronous work; it is not removed merely for that reason. Repeated identical spans are deduplicated;
conflicting duplicates and duplicate scenario trace IDs are rejected.

`fred.category` accepts `runtime`, `control_plane`, `auth`, `keycloak`, `llm`,
`mcp`, `tool` and `persistence`. A generic tool span is never inferred to be MCP.
`service.name` and `peer.service` accept fixed labels `fred-agents`, `fred-runtime`,
`control-plane`, `keycloak`, `llm`, `mcp` and `persistence`; other labels are shown
as unknown. `kind=3` and a known peer identify an instrumented client call; a
parent link alone is a span relationship, not necessarily network traffic.
LLM client spans measure the full instrumented model invocation, including any
wrappers/retries; they attest a logical dependency, not a pure network duration.
Span status distinguishes unset, OK and error. Fixed operation names identify the
instrumented boundary; arbitrary names never enter HTML, even from an external
unfiltered file. `first_chunk_ms` appears only when a finite nonnegative numeric
LLM measurement fits the span; zero is measured, absence is unknown, and a value
beyond the span raises a warning. ReAct streaming currently supplies this metric;
it is not inferred for graph model calls or from the client first-text timestamp.

The component table includes every selected run and level, plus totals per run
when more than one level is selected.
It reports observed/eligible turns and p50/p95/max from each category's union of
intervals, clipped to that turn's observed client window. Unlike the successful
client latency metrics, it includes failed turns with a measurable window.
No sample means **unknown**, never zero. The trace-presence count also includes
turns without a usable client end; those turns remain outside duration aggregates. Nested or parallel categories are not
additive; time outside attributed intervals is **unattributed**, not CPU time.
Coverage counts do not prove a complete trace or distinguish every sampling,
instrumentation and export gap. Incomplete EOF windows are marked. Initial
Keycloak login and refresh client timings are shown separately at campaign scope,
while refresh actually performed in a turn appears in its timeline and metrics.

Use **Explorer** on any turn, then previous/next, to inspect the client timeline,
server spans and attested parent relationships. A bounded SVG groups observed
client/peer dependencies by component; a client span and its server child count
as one call, and generic internal tool parentage creates no network edge.
LLM invocations use dashed arrows. Detailed span parentage remains in a collapsible
section. Rendering caps detail at 300 rows
and 300 links; all imported spans still contribute to the statistics. Import
limits are 128 MiB, 200,000 spans total and 2,000 spans per turn, in addition to
the scenario limits. JSON and HTML outputs remain exclusive and private.

## Reproduce the local setup from Git

The deployment and setup entry point is the factory's
[benchmark guide](https://github.com/fred-agent/fred-deployment-factory/blob/weaver/docs/BENCHMARKS.md).
Its `VALUES` files configure the mock and Fred connection. Follow that guide
before running this client; no manual SQL is required.

Build Weaver's images from a revision containing the current Python SDK contract:
`RuntimeModels` accepts the resolver's `default` and `reasoning_default_on` fields.
The normal `fred-agents` image build includes `libs/fred-sdk`, so the API and worker
use the same correction without a separate image patch. For an existing organization,
the same [organization configuration](../../apps/control-plane/README.md#configure-organization-models)
adds the mock source at startup; its Owner then refreshes and permits the model. Initialization receipts and existing
organization defaults are preserved. A successful setup is not a benchmark run;
start load only with the explicitly selected scenario parameters below.

## Conversation scenario with factory identities

Run from `developer_tools/benchmarks`. Prepare the identities, shared team/space,
agent and mock configuration outside the load window. The selected agent may use any model configured in Fred. This advanced recipe
uses several factory-created accounts for concurrency tests; the single-user
recipe above uses an existing bearer token. Both run the same conversation engine
and produce the same report format. Setup and rights remain outside the load window.

The factory produces a private JSON file (mode `0600`, or stricter):

```json
{"schema_version":1,"issuer":"http://localhost:8080/realms/app","client_id":"fred-bench-local","client_secret":"REDACTED","users":[{"label":"user-0001","username":"bench-example-0001","password":"REDACTED"}]}
```

`-credential-file` enables multiple identities and token renewal. When supplied,
it takes precedence over `AGENTIC_TOKEN`. Without it, `AGENTIC_TOKEN` supplies one
identity (shared across conversations). Never pass passwords/client secrets on the
command line. The client accepts only regular
private files up to 4 MiB. The issuer must use HTTP(S), one `/realms/<name>` path,
and a local test host: `localhost`, `*.localhost`, loopback IPv4/IPv6, `keycloak`
or `app-keycloak`. Arrange name resolution to the intended test Keycloak first.
Userinfo, query, fragment, escapes and redirects are rejected. Login uses the
issuer's `/protocol/openid-connect/token` direct grant endpoint; no Keycloak
configuration is modified. The dedicated test client must allow this grant.

All required users log in before any load, with `-auth-concurrency=8` by default
(maximum 64). Insufficient accounts, duplicate subjects or a failed login stop
before execution. Tokens remain in memory; refresh has an expiration margin,
one cancellable gate per identity, and atomic refresh-token rotation. Shared
conversations use the same gate. Failed refresh stops that identity; an agent
POST returning 401 is never replayed. JWT `sub` is decoded solely for attribution
and Swift's `runtime_context.user_id`; this is not JWT validation or authority.

Before load, a read-only preflight checks current terms and performs one
Control Plane preparation per identity for access, model/routing and binding.
The same team/space and instance configuration applies to the whole run.
Weaver still prepares every measured turn. Swift prepares only during preflight,
outside turn timing. Each Swift conversation also registers its locally generated
session ID, selected instance and title in Control Plane before its first turn,
using the same identity as execution. Registration is included in load elapsed,
not turn or execution latency. A failed registration stops that conversation
without execution or POST retry; only HTTP 201 establishes ownership. Its CP origin is derived from `-url`; both targets use
`-control-plane-path=/control-plane/v1` unless explicitly changed. No rights,
team membership, invitations or terms acceptance are created by a scenario run.
Errors use fixed categories such as `terms_acceptance_required`, `http_403`,
`preflight_route_or_team_mismatch` or `auth_http_401`, never server response text.

For disposable accounts whose usernames start with `bench-`, a separate command
checks terms or explicitly accepts the current version. It requires the public
Control Plane origin even for Swift. No agent, session or load request is made:

```bash
mkdir -p results
# Set CREDS, TARGET and ORIGIN to the chosen local test installation first.
GOTOOLCHAIN=go1.24.0 go run . \
  -prepare-only -target="$TARGET" \
  -fred-origin="$ORIGIN" -control-plane-path=/control-plane/v1 \
  -credential-file="$CREDS" -accept-test-terms=current \
  -raw-report=results/identity-preparation.jsonl
```

Omit `-accept-test-terms=current` for a read-only check. Each invocation requires
a new report path. Already accepted or disabled terms cause no POST. Weaver
sends the observed version; Swift's API accepts the current version without a
version precondition, so a reread detects changes but cannot promise atomic
version acceptance during a deployment. `accepted_unverified` records a POST
that succeeded but whose follow-up verification failed. Stop deployment changes
during preparation; inspect partial results before retrying. The client never
creates accounts or calls a grants API. Swift's existing first-acceptance handler
also joins configured default teams; explicit terms acceptance therefore retains
that normal backend side effect. The preparation stops at its first failed identity.

Start with an explicitly authorized one-conversation run, then reuse the same
explicit concurrency steps on each independently running target:

```bash
# Weaver; all quoted variables are operator-supplied, never written to reports.
GOTOOLCHAIN=go1.24.0 go run . \
  -scenario=conversation -target=weaver -protocol=sse \
  -credential-file="$CREDS" -fred-origin="$WEAVER_ORIGIN" \
  -space-id="$SPACE_ID" -agent-instance-id="$WEAVER_INSTANCE_ID" \
  -concurrency-steps=1 -identity-mode=per-conversation \
  -requests-per-client=10 -timeout=30s \
  -raw-report=results/weaver-scenario.jsonl \
  -json-report=results/weaver-scenario-summary.json

# Swift; SWIFT_STREAM_URL includes the actual public /agents/execute/stream path.
GOTOOLCHAIN=go1.24.0 go run . \
  -scenario=conversation -target=swift -protocol=sse \
  -credential-file="$CREDS" -url="$SWIFT_STREAM_URL" \
  -sse-team-id="$TEAM_ID" -agent-instance-id="$SWIFT_INSTANCE_ID" \
  -concurrency-steps=1 -identity-mode=per-conversation \
  -requests-per-client=10 -timeout=30s \
  -raw-report=results/swift-scenario.jsonl \
  -json-report=results/swift-scenario-summary.json
```

`-concurrency-steps=1,10,50` explicitly selects sequential levels; there is no
automatic escalation, duration mode or ramp. Each level uses the common `runLoad`
engine and fresh conversations. Each conversation performs ten sequential turns
by default, with no intentional pause. `per-conversation` assigns one distinct
authenticated user to each conversation at a level; `shared` is the one-user,
N-conversation reference. Users are reused across levels, conversations are not.
Bounds are 32 levels, 10,000 clients per level and 100 turns per conversation.
Do not use legacy `-clients`, `-requests`, `-ramp-duration`, `-session` or identity
overrides here. Bootstrap, WebSocket, query tokens and TLS bypass are unsupported.

Every turn sends its question unchanged. The client checks the Fred SSE protocol:
one final answer, nonempty text, bounded content, and matching streamed/final text
when both are supplied. These checks do not assess answer quality or prove what
history the model received. Provider-specific answer or timing rules do not belong
in this client.

After every load window joins all clients, the client reads owned conversation
history and compares the ordered user and final assistant texts with SHA-256
digests kept in memory from the executed turns. It also verifies session IDs,
exchange pairing and ranks. Weaver resolves `SessionDetails.messages_url`;
Swift uses its existing runtime `/agents/sessions/<id>/messages` endpoint.
Unsupported history is recorded as `unsupported`, never `verified`. Read/shape
or consistency failures are separate from performance errors. There is no
per-turn history GET in this scenario. Only afterwards are created sessions
cleaned up by default; `-delete-session=false` retains them. Weaver validates
deletion acceptance without polling a purge. Swift deletes its owned Control
Plane row through the team session API, which governs runtime erasure and any
configured deletion window; HTTP 204 acknowledges deletion, not physical purge
completion. It never directly deletes runtime history. A created row is cleaned
up even if registration validation or execution subsequently fails; collisions
are never reused or deleted. Retained Swift sessions have the metadata needed
for the UI sidebar. Cleanup is bounded independently of canceled load, and
failures remain visible. No pre-existing session can be supplied.

### Scenario reports

Scenario raw output is required, created exclusively with mode `0600`, written
progressively and synced after each record. Parent directories must already
exist. Existing raw or summary files are refused. Records have kinds `run`,
`auth`, `onboarding`, `preflight`, `turn`, `history`, `step` and `summary`.
The run/summary schema is `fred.bench.scenario.v1`; each turn uses
`fred.bench.scenario.turn.v1`. Legacy exports below keep their existing versions.
Graceful cancellation drains attempted turns, writes their results and closes
the report; already synced rows survive later failure. A failed writer cancels
the load and exits nonzero. Sync can exert client backpressure and is part of
the actual measured client behavior, not server execution time.

Each attempted turn records its level, concurrency, first/following status,
campaign-scoped pseudonyms for identity and conversation, outcome, performance
outcome and integrity outcome. No credentials, usernames, JWT subjects, prompts, answer text, endpoint URLs or backend session IDs are exported.
The same conversation pseudonym joins turn and post-history records. Auth login
and refresh have their own timed records and aggregate statistics. Turn start
includes refresh waiting; optional `auth` describes a refresh actually performed
by that turn, not a fabricated refresh for every waiter. Preparation, execution
request start, first actual text, final and clean EOF remain distinct timestamps.
Logical text-fragment count and maximum useful silence (initial wait, inter-text
gap and EOF tail) are client observations, never tokenizer or token metrics.
Text retained for verification is limited to 128 KiB; JSON history to 4 MiB.

Per-level summaries distinguish planned, attempted, not started, successful and
failed turns. A failed conversation stops; others continue. Performance errors,
stream integrity errors, post-history errors/unsupported status and cleanup errors
are separate counts. p50/p95/max and sample counts are given separately for
first and following successful turns: preparation, execution-to-text/final/EOF,
total-to-final/EOF and silence. Percentiles use nearest rank; a zero sample count
means unmeasured, not zero latency. Failed or invalid-stream turns are excluded;
post-history failure preserves the separately recorded turn measurements.
Load elapsed includes session opening and export backpressure, and excludes
initial login/preflight, post-history and cleanup. Total per-turn latency includes
refresh and Weaver preparation; execution latency begins after preparation.
Compare like phases: Swift has no per-turn preparation samples. An incomplete
run, missing history verification or cleanup failure cannot report `OK`, and no
successful observed turn means `FAILED`. No throughput/capacity claim is made.

## Weaver managed SSE

Requires a user JWT already obtained outside this tool, read access to the space,
a usable managed instance and model, and accepted platform terms where required.
The public Fred origin must serve both Control Plane and the runtime under their
approved paths. The JWT is sent only as a bearer header; there is no fake-token
fallback, refresh, account creation, or per-client identity provisioning.

Usage example, **not an executed campaign** (replace the placeholders only for a
separately authorized run):

```bash
AGENTIC_TOKEN="$TOKEN" GOTOOLCHAIN=go1.24.0 make run ARGS='\
  -target=weaver -protocol=sse \
  -fred-origin=https://fred.example.invalid \
  -control-plane-path=/control-plane/v1 \
  -space-id=<SPACE_UUID> -agent-instance-id=<INSTANCE_UUID> \
  -clients=1 -requests-per-client=2 -ramp-duration=0s \
  -message="Réponds simplement : test réussi" -timeout=30s \
  -delete-session=false \
  -json-report=results/weaver-summary.json \
  -raw-report=results/weaver-turns.jsonl'
```

`-fred-origin` is an HTTP(S) origin without a path, userinfo, query or fragment.
`-control-plane-path` defaults to `/control-plane/v1`. Space/instance identifiers
must be UUIDs. Every client registers a fresh UUID conversation after reading
`configuration_revision` from the public GET agent-instance endpoint. Registration
sends `session_id`, `agent_instance_id`, `agent_configuration_revision` and title.
The returned binding must match; a configuration change is a failure, not an
implicit retry against a different revision. A creation response must be `201`;
`200` cannot silently reuse another conversation.

Each turn POSTs `prepare-execution?session_id=...`. The client checks revision,
space, instance, SSE support, `model_error`, inference selection and the announced
execution path before sending a request. Preparation is informative, **not runtime
admission**. Execution sends `agent_instance_id`, `input`, `session_id` and only
`runtime_context.space_id`; user identity comes from the JWT. Routing follows
`runtimeExecutionUrl.ts`: a canonical origin-relative path with a nonempty mount
ending in `/agents/execute/stream`, no absolute URL, query, fragment, escaping,
duplicate slash or dot segment. All HTTP redirects are refused, even same-origin.
The common SDK event decoder and SSE transport require final **and** normal EOF.

After a successful stream, GET SessionDetails resolves `messages_url`, then GET
that same-origin canonical `/agents/sessions/<session_id>/messages` route reads
the JSON array before the next turn. Only the row count is retained. This is the
minimal history hookup: no content export, pagination, retry/polling or full
history consistency check under load. The runtime contract commits history
before EOF; this legacy count-only read does not verify complete user/assistant
turns. The opt-in scenario above performs that check after load. No durable
history route, invalid JSON or a
failed history read fails this benchmark turn and stops the conversation, with
execution observations preserved separately. JSON responses are bounded to 4 MiB.

Conversations are cleaned up by default (`-delete-session=true`) **after** all
reads and turns, or after an error, with an independent `-timeout` budget per
conversation. Only conversations whose creation returned `201` are eligible.
`-delete-session=false` retains them for inspection in Fred (default title:
`Benchmark`). `-session=<UUID>` reuses an operator conversation with **one client
only**, verifies its binding and never deletes or re-registers it. A lost create
response can leave a conversation retained because ownership was not confirmed;
there is no speculative retry or deletion. Cleanup validates the deletion receipt:
queued/running means accepted, completed means completed, blocked/retrying or an
invalid/failed response counts as a cleanup error. No purge completion is polled.
Errors print a count, return exit status 1, set aggregate `cleanup_errors` and
make an otherwise OK summary DEGRADED; successful turn measurements stay intact.

Weaver supports only persistent managed SSE (`-requests-per-client>0`). It refuses
WebSocket/total-request modes and explicitly supplied Swift-only flags, including
`-url`, `-agent`, agent bootstrap, `-sse-user-id`, `-sse-team-id`, `-session-url`,
`-prepare-sessions`, `-prepare-concurrency`, query/empty auth, TLS bypass,
WebSocket read/debug options and legacy document/search context selections.
Even explicitly passing a default/false value for these options is rejected.
No HITL resume, model choice, attachments or full UI workflow is implemented.
Concurrent clients share the supplied JWT; they are not distinct users.

## Swift managed SSE

From `developer_tools/benchmarks`, with an externally supplied user JWT:

```bash
AGENTIC_TOKEN="$TOKEN" GOTOOLCHAIN=go1.24.0 make run ARGS='\
  -target=swift -protocol=sse \
  -url=http://127.0.0.1:8000/fred/agents/v2/agents/execute/stream \
  -agent-instance-id=<AGENT_INSTANCE_UUID> \
  -sse-team-id=<TEAM_ID> \
  -message="Réponds simplement : test réussi" \
  -clients=1 -requests-per-client=1 -ramp-duration=0s \
  -timeout=30s \
  -json-report=results/summary.json \
  -raw-report=results/turns.jsonl'
```

This historical Swift benchmark does **not** call UI prepare-execution or read
history. It is not equivalent to the full UI journey; raw records explicitly
state `preparation_mode: "not_performed"`.

Managed mode sends `agent_instance_id` and `runtime_context.team_id`, never
`agent_id`. `-agent` is ignored in this mode. Historical direct SSE instead uses
`-agent=<template-id>` without `-agent-instance-id`. `-sse-user-id` still defaults
to `bench`; it is a runtime-context hint, **not a distinct authenticated user**.

With `-requests-per-client>0`, each client owns a stable session and performs
sequential turns without an intentional pause. `-create-session=true` (default)
generates the SSE session ID locally; Swift SSE has no benchmark HTTP session
create/delete call. `-session=<id>` explicitly reuses the supplied session across
clients; this legacy option does not provide conversation isolation. For one
conversation per client, omit it and keep `-create-session=true`.

`-clients=N -requests-per-client=10 -ramp-duration=0s` expresses N concurrent
conversations of ten turns under the **same token**. It is a foundation for the
reference workload, not the full scenario of N different users in one team.
No capacity at 500 clients, or any other level, has been measured in this lot.

SSE success requires a complete `final` event **and clean HTTP body EOF**.
`execution_error`, the legacy bare `error`, and `execution_interrupted` fail the
turn. `node_error` is a nonterminal warning. Malformed events, missing final,
incomplete data frames, broken HTTP bodies, non-2xx responses, timeout and
cancellation cannot succeed. The reader continues after final (and terminal
errors) to observe EOF; timeout bounds that drain. The first terminal/protocol
error is retained if later reading also fails. Redirects are rejected.

## Preserved WebSocket usage

```bash
AGENTIC_TOKEN="$TOKEN" GOTOOLCHAIN=go1.24.0 make run ARGS='\
  -url=ws://localhost:8000/agentic/v1/chatbot/query/ws \
  -agent-uuid=<EXISTING_AGENT_UUID> \
  -clients=1 -requests-per-client=2 -ramp-duration=0s \
  -create-session=true -prepare-sessions=true -delete-session=true \
  -read-limit-bytes=8388608'
```

`-protocol=ws` remains the default. A persistent client reuses one connection
and session. HTTP session preparation/cleanup and agent bootstrap flags remain:

- `-agent=<id>` selects a configured agent. `-agent-uuid` takes precedence and
  bypasses agent creation.
- `-ensure-v2-definition-ref=v2.react.basic` or
  `-ensure-v2-profile-id=rag_expert`, with `-ensure-agent-name`, creates a temporary
  agent; `-delete-created-agent=true` removes it afterwards.
- `-document-library-ids=a,b`, `-document-uids=a,b`, `-search-policy=hybrid`,
  `-search-rag-scope=corpus_only` and optional `-include-session-scope` /
  `-include-corpus-scope` retain their runtime-context mapping.
- `-session-url`, `-agent-create-url`, `-prepare-concurrency`, `-insecure` and
  `-read-limit-bytes` retain their transport/lifecycle uses.
- `-requests-per-client=0 -requests=K` retains total-request scheduling: K
  independent exchanges across up to `-clients` workers. WebSocket opens a
  connection/session per exchange; SSE retains its historical lack of an implicit
  stable session in this mode. The ramp applies only to persistent-client mode.

All Swift modes use `AGENTIC_TOKEN`, overridden by explicit `-token`. Query-token
compatibility (`-token-in-query` or a token already in the URL) remains. The
historical `fake-token` fallback for auth-disabled local development is retained;
it does not authenticate against a secured runtime. Defaults remain 150 clients,
10 turns per client, a 10-second ramp and a 90-second timeout. Set small explicit
values for a separately authorized smoke run.

A failed turn stops that persistent conversation; other clients continue.
SIGINT/SIGTERM cancels active requests, session preparation and ramp waits.
Preparation stops scheduling new creates; known created sessions are cleaned up
with an independent, shared `-timeout` budget when deletion is enabled. Unstarted turns are not
fabricated. WebSocket `final` ends an exchange on the reusable connection; there
is no per-turn stream-close measurement for WebSocket. `-debug-events` now emits
WebSocket receipt notifications only, never response payloads.

## Reports and raw format

Neither report is written unless its flag is supplied. `results/` is Git-ignored.
`-json-report=<path>` retains the existing `v1` aggregate schema: planned request
count, observed successes/errors, elapsed time, throughput and latency percentiles
in integer milliseconds. Its `target` field still means the endpoint URL, with
credentials, query and fragment removed. Its latency is still **start to final**,
not start to EOF. WebSocket total-request latency includes session creation and
dial; Swift persistent mode excludes setup, while Weaver includes its per-turn
preparation. Elapsed campaign time includes
preparation/cleanup, but excludes report writing. Failed turns are excluded from
latency statistics. The stricter SSE completion check can reduce successes, and
waiting for EOF can reduce throughput compared with the former final-only reader.
An interrupted run with unsent turns is no longer reported `OK`.

`-raw-report=<new-path>` writes UTF-8 JSON Lines, one object per attempted turn,
including failures. The file is created with mode `0600`; an existing path is
refused, never overwritten. Before truncating an existing summary, the writer
compares its file identity with the raw destination and refuses collisions,
including symbolic-link and hard-link aliases. Write failures return a nonzero exit status. Records
are collected in memory and exported after the run/cleanup, including graceful
cancellation; a killed process has no guaranteed raw export. Order across clients
is completion order; within a client/conversation it is turn order.

Swift records keep schema `fred.bench.turn.v1`:

| Field | Meaning |
| --- | --- |
| `schema_version` | Exactly `fred.bench.turn.v1`; incompatible changes need a new version. |
| `target`, `protocol` | Actual adaptation (`swift` or `weaver`), and `sse` or `ws`; no endpoint URL. |
| `preparation_mode` | Additive field: `not_performed` for historical Swift, `per_turn` for Weaver. This describes the path, not a successful preparation. |
| `campaign_id` | Automatically generated ID shared by this run's records. |
| `client_id` | One-based logical worker number, not an authenticated user ID. |
| `conversation_id` | Campaign-scoped SHA-256 pseudonym of the session ID; generated local identity if no session exists. No backend ID is exported. |
| `turn` | One-based attempt number within that client's conversation. |
| `started_at` | Client-side execution start in RFC3339Nano, not a server admission/execution timestamp. Includes opening/setup in total-request mode. |
| `first_text_at` | First nonempty assistant text observed: Swift `assistant_delta.delta` or `final.content`; WebSocket `stream.content` or `final.content`. |
| `final_at` | First complete final event received, even if a later failure makes the turn unsuccessful. |
| `stream_closed_at` | Clean SSE HTTP-body EOF observed, even if final is missing. Absent on forced close, transport error or WebSocket. |
| `outcome` | `success`, `error`, `timeout` or `canceled`. |
| `error` | Fixed category on failure; omitted on success. |

Optional timestamps are **omitted**, never zero-filled. Technical status, tool,
reasoning, title and warning events are not first text. A final carrying the
first answer text can set `first_text_at` and `final_at` to the same instant.
Subtract timestamps to obtain first-text, final and EOF latencies; all are client
observations, not server instrumentation. A setup failure records one failed
attempt with no invented text/final/EOF observation.

Error categories are `http_status`, `execution_error`, `execution_interrupted`,
`invalid_event`, `incomplete_stream`, `event_too_large`, `transport_error`,
`timeout` and `canceled`. No arbitrary server error messages, prompts, response
text, headers, tokens or backend conversation IDs enter the raw format. Summary
error samples also use these safe categories. No per-user authentication or
cross-campaign identity correlation is claimed.

### Weaver timing and raw v2

Weaver records use `fred.bench.turn.v2`: `started_at` is the **turn attempt start**,
before preparation, not an execution/admission timestamp. Opening (instance GET,
registration or operator-session GET) is outside successful per-turn latency. An
opening failure produces one failed attempt with its setup start and no fabricated
preparation/execution observations. Unstarted later turns are never exported.

| Weaver observation | Meaning |
| --- | --- |
| `preparation.started_at`, `.finished_at`, optional `.error` | Per-turn preparation request plus client validation, including rejected preparation. |
| `execution_started_at` | Client starts the SSE request after validated preparation; absent if none was sent. Not proof of server admission. |
| `first_text_at`, `final_at`, `stream_closed_at` | Same event/EOF semantics as Swift; all absent on preparation refusal. |
| `history.started_at`, `.finished_at`, optional `.error` | Session metadata and messages reads after successful stream completion. |
| `history_messages` | Number of rows returned, only after successful history reading; not a count of validated turns. |

Subtract preparation timestamps for preparation latency; subtract
`execution_started_at` from text/final/EOF for execution-request observations.
The Weaver summary latency remains start-to-final, including preparation but
excluding history and cleanup. Success requires final, EOF and the history read;
history failure retains the observed execution timestamps but excludes that turn
from successful latency statistics. Campaign elapsed/throughput includes setup,
history and cleanup. Swift latency semantics are unchanged: comparing the two
summaries does not compare equivalent UI paths. Neither format measures admission.
The aggregate schema remains `v1`, with optional Weaver `space_id` and
`cleanup_errors`; its `target` remains a sanitized URL (Fred origin for Weaver).

Weaver adds bounded error categories `http_<status>` for Control Plane/history
requests, `invalid_binding`, `invalid_session`, `session_not_created`,
`unsupported_transport`, `model_unavailable`, `invalid_execution_url`,
`history_unavailable`, `invalid_response` and `invalid_history`. Execution keeps
the shared SSE categories (`http_status`, etc.). No upstream error text is exported.

## Code boundary and local validation

- `main.go`: existing CLI flags, target validation and run/report wiring.
- `engine.go`: one load engine, concurrency, sequential turns, cancellation,
  common observations and isolated collection. It consumes `Open(ctx, client)`
  and a conversation exposing `Execute(ctx)`, `ID()` and `Close()`.
- `swift.go`: Swift sessions and request construction; `ws_bench.go` retains
  Swift WebSocket wire and HTTP lifecycle helpers.
- `weaver.go`: public contracts, per-conversation lifecycle, per-turn preparation,
  execution and minimal history reads; no scheduling loop.
- `sse_bench.go`: reusable HTTP/SSE framing and completion handling, plus the
  shared SDK runtime event decoder used by Swift and Weaver.
- `reports.go`: aggregate compatibility and explicit raw export.
- `report_html.go`, `report_traces.go`, `report.html.tmpl`: offline scenario/OTLP projection and self-contained interactive report.
- `trace.go`: optional W3C turn correlation, no SDK/exporter.
- `auth.go`: private factory input, bounded login and per-identity refresh.
- `scenario.go`, `scenario_reports.go`: opt-in levels using the common engine,
  post-window checks, progressive private records and phase summaries.
- `oracle.go`: bounded stream and persisted-history verification.
- `prepare.go`, `onboarding.go`: explicit preparation command and read-only
  preflight through the existing Control Plane terms/access APIs.

Checks (Go 1.22.2 is installed on the development machine; use the toolchain
override without changing `go.mod`):

```bash
GOTOOLCHAIN=go1.24.0 go test -race ./...
GOTOOLCHAIN=go1.24.0 go vet ./...
git diff --check
```

Local validation runs the commands above (including the existing Swift
Swift regressions), gofmt on changed Go files and `git diff --check`. Tests use
`httptest` and doubles only: opening and two turns, distinct client conversations,
request payload/order, revision/placement errors, 401/403/409, model availability,
URL/redirect refusal, preparation/stream cancellation and timeout, final then EOF,
truncation/terminal errors, history reads, retention/cleanup receipts, CLI wiring,
raw Weaver success/failure privacy and explicit Swift absence of preparation.
Scenario fixtures also cover initial multi-identity login, local issuer policy,
singleflight rotating refresh and sticky failures, both targets with shared or
distinct users, context corruption, history consistency, one failing conversation
without POST replay, 100 logical mock fragments, raw durability during graceful
cancellation, exclusive outputs and real CLI wiring. Terms tests cover explicit
acceptance, disabled/already accepted versions, version changes, safe failures,
synthetic-only preparation and its lack of load requests. All services are
isolated `httptest` doubles, not the running Keycloak, mock or Fred installation.
No real Fred endpoint, k3d, deployment, load campaign or performance comparison
was exercised by these checks. `report_ui_test.cjs` runs via Go tests when Node is
available and exercises filters, turn navigation, coverage and the generated
template using an offline DOM double. Import checks cover exact joins, interval
unions, missing/invalid spans, cycles, duplicates and private attribute exclusion.
