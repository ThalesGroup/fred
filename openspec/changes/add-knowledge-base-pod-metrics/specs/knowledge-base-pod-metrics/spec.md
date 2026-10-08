## Purpose

Defines the operational metrics every Knowledge Base pod exposes, independently
of the language or SDK it is written with, so platform operators can monitor any
Knowledge Base like a native Fred component.

## ADDED Requirements

### Requirement: Metrics exposition endpoint

A Knowledge Base pod SHALL serve its operational metrics over HTTP in the
OpenMetrics text exposition format (Prometheus text format accepted), at the
path `/metrics`. The endpoint SHALL be read-only and SHALL require no
authentication. It SHALL be configured under the pod configuration key
`observability.kpi.prometheus` with fields `enabled` (default `true`), `address`
(default `127.0.0.1`) and `port` (default `9000`). With `enabled: false` the pod
SHALL open no metrics port. Measuring SHALL never cause a run to fail: if the
implementation cannot produce metrics, the pod SHALL log a warning once and
serve runs normally. An enabled endpoint that cannot be opened (its port taken)
is a deployment error and SHALL stop the pod at startup, naming the address.

#### Scenario: Default configuration
- **WHEN** a pod starts with no `observability` block
- **THEN** `/metrics` is served on `127.0.0.1:9000` only, unreachable from outside the pod

#### Scenario: Bound outward
- **WHEN** the pod configuration sets `observability.kpi.prometheus.address: 0.0.0.0`
- **THEN** a scraper reaching the pod on port 9000 reads the series defined below

#### Scenario: Disabled
- **WHEN** `observability.kpi.prometheus.enabled` is `false`
- **THEN** no metrics port is open and runs are served unchanged

#### Scenario: Port already taken
- **WHEN** the configured metrics port is already bound on the pod
- **THEN** the pod exits at startup before serving any run

### Requirement: Workflow engine metrics endpoint

A pod whose runs are served through Fred's workflow engine SHALL expose the
engine's own metrics on a separate endpoint configured under
`observability.temporal.prometheus` (`enabled`, `address` default `127.0.0.1`,
`port` default `9001`). Every series on it SHALL carry the `service` and
`knowledge_base` labels defined below.

#### Scenario: Engine series joinable with pod series
- **WHEN** both endpoints are scraped after a run
- **THEN** engine series such as task schedule-to-start latency carry the same `service` and `knowledge_base` values as the pod's `fred_kb_*` series

### Requirement: Pod operational identity from deployment configuration

A Knowledge Base pod SHALL read its operational identity from the required
configuration key `app.runtime_id`, the key agent pods already use. Its value
SHALL be a lowercase slug matching `^[a-z][a-z0-9]*(-[a-z0-9]+)*$`, chosen by
whoever deploys the pod (chart values or `configuration.yaml`), never fixed in
the image's code. A pod whose configuration omits it or holds an invalid value
SHALL refuse to start, naming the key. The same value SHALL appear as the
`service` label on every series the pod exposes and as the `service` field of
every log record it writes, so a metric and a log line join on one value.

#### Scenario: Identity chosen at deployment
- **WHEN** the chart values set `configuration.app.runtime_id: webdav-kb`
- **THEN** every `fred_kb_*` series and every engine series carries `service="webdav-kb"`, and every log record carries `"service": "webdav-kb"`

#### Scenario: Identity missing
- **WHEN** a pod starts with a configuration lacking `app.runtime_id`
- **THEN** it exits before serving any run, with an error naming `app.runtime_id`

### Requirement: Definition identity label

Every `fred_kb_*` series SHALL carry, besides `service`, the label
`knowledge_base`, set to the id of the Knowledge Base definition the pod
serves. The pod SHALL export
`fred_kb_info{service, knowledge_base, version, sdk, sdk_version}` with value
`1`, where `version` is the definition's version, `sdk` names the SDK
implementation (`fred-sdk-python` for the reference one) and `sdk_version` is
that implementation's own version.

#### Scenario: Pod identifies itself
- **WHEN** the pod has started and before any run
- **THEN** `fred_kb_info` is present with its runtime id, the definition id and version, `sdk="fred-sdk-python"` and the SDK version

### Requirement: Structured logs

A pod SHALL write its log records to standard output, one JSON object per
line, from its first record — including those emitted while its configuration
loads — each with at least `ts` (Unix time), `level`, `logger`, `msg`,
`service` (the runtime id) and `knowledge_base` (the definition id). The
configuration key `observability.logs.format` SHALL accept `json` (default)
and `text`; `text` is for local work and SHALL still carry the runtime id on
every line. Log records SHALL follow the same exclusions as other Fred logs:
no secret, no token, no document content.

#### Scenario: Configuration loading is logged as the pod
- **WHEN** the pod logs while loading its configuration, then starts
- **THEN** those lines are JSON objects carrying the runtime id, like every later line

#### Scenario: Configuration that cannot load
- **WHEN** the configuration cannot be loaded, so the pod has no identity
- **THEN** the records emitted so far are written as text on standard error before the pod exits

#### Scenario: Log line joins its metric
- **WHEN** a run fails and the pod logs the failure in the default format
- **THEN** the line is a JSON object whose `service` equals the `service` label of the `fred_kb_runs_total{outcome="error"}` series it incremented

### Requirement: Structurally excluded labels

No series SHALL carry a label identifying a team, a Knowledge Base instance, a
library, a run, a workflow, a user, a document, a source path or an issue
subject. These are Stream 2 and Stream 3 concerns (see
`docs/swift/platform/OBSERVABILITY-AND-AUDIT.md`). Label values SHALL come from
the closed sets defined in this specification, except `service`,
`knowledge_base`, `version`, `sdk`, `sdk_version`, `exception_type` and the
bounded issue `code`. Every series in the tables below also carries `service`;
the tables omit it for brevity.

#### Scenario: Two instances of one definition
- **WHEN** two teams run instances of the same definition on one pod
- **THEN** their runs are counted in the same series, distinguishable by no label

### Requirement: Run series

The pod SHALL measure every run attempt with these series:

| Series | Type | Labels |
|---|---|---|
| `fred_kb_runs_in_progress` | gauge | `knowledge_base` |
| `fred_kb_runs_total` | counter | `knowledge_base`, `outcome`, `reconciliation` |
| `fred_kb_run_duration_seconds` | histogram | `knowledge_base`, `outcome` |
| `fred_kb_last_run_timestamp_seconds` | gauge (Unix time) | `knowledge_base`, `outcome` |
| `fred_kb_run_errors_total` | counter | `knowledge_base`, `stage`, `exception_type` |

`outcome` SHALL be one of `succeeded`, `failed`, `cancelled` (as reported by
the handler), `error` (the handler or the SDK raised) or `interrupted` (the
worker stopped or Fred withdrew the run). `reconciliation` SHALL be the run's
reported reconciliation (`complete`, `partial` or `up_to_date`, see *Run
reconciliation*) when the handler reported, `none` otherwise. `stage` SHALL be
`context` (fetching the run context), `declare` (declaring the library
synchronized) or `handler`. `exception_type` SHALL be the raised error's type
name, without its message. Each attempt SHALL be counted exactly once, and its
duration SHALL span from the start of the context fetch to the attempt's end.

#### Scenario: Handler reports a partial success
- **WHEN** a handler returns outcome `succeeded` with an incomplete reconciliation
- **THEN** `fred_kb_runs_total{outcome="succeeded",reconciliation="partial"}` increases by one

#### Scenario: Nothing to do
- **WHEN** a handler reports that its library already matched the source
- **THEN** `fred_kb_runs_total{outcome="succeeded",reconciliation="up_to_date"}` increases by one

#### Scenario: Handler raises
- **WHEN** the handler raises
- **THEN** `fred_kb_runs_total{outcome="error",reconciliation="none"}` and `fred_kb_run_errors_total{stage="handler"}` each increase by one and the error still propagates to the workflow engine

#### Scenario: Worker stopped mid-run
- **WHEN** a run is cancelled by the worker shutting down
- **THEN** it is counted with `outcome="interrupted"` and not in `fred_kb_run_errors_total`

### Requirement: Run reconciliation

Every reported run result SHALL state how much of its source it reconciled,
as exactly one of:
- `complete` — the run observed the source exhaustively and authoritatively;
  an item absent from it was really removed.
- `partial` — a valid but bounded pass (paging cut short, a filter, a budget,
  or an incremental pass); an absence proves nothing, only explicit deletions
  may be acted on.
- `up_to_date` — the run established, without enumerating the source, that the
  library already matches a previously complete state (an unchanged revision
  or version); it wrote and removed nothing.

A result reporting `up_to_date` SHALL be refused unless its outcome is
`succeeded` and it reports no created, updated or removed item and no error.

#### Scenario: Unchanged source
- **WHEN** a Git handler finds its recorded revision equal to the branch head
- **THEN** it reports `up_to_date` and writes nothing

#### Scenario: Up to date with writes is refused
- **WHEN** a result reports `up_to_date` together with one updated item
- **THEN** the result is rejected as invalid

### Requirement: Item and issue series

From each reported run result the pod SHALL add:

| Series | Type | Labels |
|---|---|---|
| `fred_kb_items_total` | counter | `knowledge_base`, `change` |
| `fred_kb_issues_total` | counter | `knowledge_base`, `severity`, `code` |

`change` SHALL be one of `discovered`, `created`, `updated`, `removed`,
`unchanged`, incremented by the reported count. `severity` SHALL be `warning`
or `error`; `code` SHALL be the issue's stable code. A pod SHALL keep at most
100 distinct codes per process and count any further code as `other`.

#### Scenario: Codes past the bound
- **WHEN** a pod has seen 100 distinct issue codes and a run reports a new one
- **THEN** that issue is counted under `code="other"`

### Requirement: Calls to Fred

The pod SHALL measure every HTTP call it makes to Fred:

| Series | Type | Labels |
|---|---|---|
| `fred_kb_requests_total` | counter | `knowledge_base`, `target`, `operation`, `status` |
| `fred_kb_request_duration_seconds` | histogram | `knowledge_base`, `target`, `operation` |

`target` SHALL be `control_plane` or `knowledge_flow`. `operation` SHALL be
`run_context` (control plane) or one of `declare_synchronized`, `publish`,
`task_status`, `list`, `retract`, `source_version_get`, `source_version_put`
(knowledge flow). The declaration's publication to the control plane is not
measured: it runs as a one-shot deployment hook that no scraper reaches, and its
exit status and logs are its outcome. `status` SHALL be the HTTP status class
(`2xx`, `4xx`, `5xx`, …), `transport_error` when no answer arrived because of
the network, or `error` otherwise. Durations SHALL include failed calls and
any credential acquisition the call needed, so an unreachable identity
provider reads as `transport_error` on the call it delayed.

#### Scenario: Knowledge Flow unavailable
- **WHEN** a document publish gets a 503
- **THEN** `fred_kb_requests_total{target="knowledge_flow",operation="publish",status="5xx"}` increases by one

#### Scenario: Network failure
- **WHEN** a call fails before any answer because the connection is refused
- **THEN** it is counted with `status="transport_error"` and its duration is observed

### Requirement: Ingestion wait series

When the pod waits for a published document's ingestion, it SHALL observe
`fred_kb_ingestion_wait_seconds{knowledge_base, state}` (histogram), where
`state` is the terminal ingestion state `succeeded`, `failed` or `cancelled`,
or `timeout` when the wait ended first. A wait ended by Fred refusing the
status request is not observed here; that refusal is counted by
`fred_kb_requests_total` under its `4xx` status.

#### Scenario: Ingestion fails
- **WHEN** a written document's ingestion ends in `failed` after 12 seconds
- **THEN** one observation of about 12 seconds is added to `fred_kb_ingestion_wait_seconds{state="failed"}`

### Requirement: No authoring code required

Every series in this specification SHALL be produced by the SDK
implementation itself. An author whose code consists only of a handler and the
SDK's document operations SHALL obtain all of them without writing any metrics
code. The endpoint SHALL also serve any additional series the author registers
with the implementation language's standard metrics library; such series
SHALL NOT use the `fred_kb_` prefix.

#### Scenario: Handler-only Knowledge Base
- **WHEN** a Knowledge Base consisting only of a handler serves one run that publishes documents
- **THEN** run, item, request and ingestion-wait series are all present on `/metrics`

### Requirement: Contract stability

Series names, label names and the closed label value sets in this
specification SHALL form a public contract shared by every SDK
implementation. Removing or renaming any of them, or changing a series type,
SHALL be a breaking change announced through a migration note. Adding a series
or a value to a closed set SHALL be backward compatible.

#### Scenario: Two implementations side by side
- **WHEN** a Python-built pod and a pod built with another SDK serve definitions on one platform
- **THEN** one dashboard query over `fred_kb_runs_total` covers both without relabelling
