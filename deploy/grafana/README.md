# Fred Grafana dashboards

Import [`fred-agent-runtime.json`](fred-agent-runtime.json) through Grafana's
**Dashboards → New → Import** page and select the Prometheus data source that
scrapes the Fred agent runtimes. The dashboard does not require a particular
data-source UID or a live OpenSearch connection. Select one or more values in
the **Fred service** filter to narrow the panels to specific runtimes.

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
