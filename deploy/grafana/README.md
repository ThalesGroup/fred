# Fred Grafana dashboards

## Import a dashboard

In Grafana, open **Dashboards > New > Import**, upload the dashboard JSON linked
below, and select a Prometheus data source that meets the dashboard's requirements.

## Platform health

[`fred-platform-health.json`](fred-platform-health.json) uses Fred's
`agent_turn_completed_count`, `api_request_latency_ms_count`, and
`api_request_latency_ms_bucket` metrics. Use a source that scrapes the agent
runtimes, control plane, and Knowledge Flow to see all services.

The summary cards follow the selected time range. **Cluster** and **Namespace**
apply to all panels when the corresponding labels are available in Prometheus.
Keep **All** selected for labels your scrape pipeline does not supply.
**Chat runtime** applies to the chat metrics. The
**24h error rate** and **Error rate detail** controls default to **On** and
apply to both error-rate charts. They use dropdowns for Grafana 12.1
compatibility. Expand **HTTP route latency** to investigate a route spike.
The latency panels use 2xx and 3xx responses.

## Agent runtime

[`fred-agent-runtime.json`](fred-agent-runtime.json) uses a Prometheus data
source that scrapes the Fred agent runtimes. The dashboard does not require a
particular data-source UID or a live OpenSearch connection. Select one or more
values in the **Fred service** filter to narrow the panels to specific runtimes.

The recovery panels use `agent_tool_call_text_recovered_total`, emitted once per
valid Mistral tool-call proposal reconstructed by the ReAct or Deep middleware.
Its model label matches the model-call timer's configured model name when available;
the writer also adds its standard `service` and `actor_type` labels. A proposal
can still be blocked by approval or budget checks, so the count is not the
number of completed tool executions. The denominator panel uses
`llm_call_latency_ms_count`; “per 100 model calls” can exceed 100 if a response
contains several recovered calls.

The remaining panels use the existing model and tool latency histograms and
tool-failure counter. The recovery and failure panels show **No data** until
their first event has been scraped. If every panel is blank, check that the
selected Prometheus source scrapes the agent runtimes' metrics endpoints.
