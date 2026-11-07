# Fred Prometheus metrics in Zabbix

Import [fred-prometheus-by-http.yaml](fred-prometheus-by-http.yaml) in Zabbix 7.0
under **Data collection > Templates > Import**. Link the template to one Zabbix
host per `/metrics` endpoint. Set `{$FRED.METRICS.URL}` on each host to a URL
reachable from its Zabbix server or proxy. The template needs no Zabbix agent.

The HTTP master item fetches the exposition once per minute. A dependent item
parses it once and indexes values by the exact metric name and label set. A
discovery rule creates a numeric item for every finite metric value and distinct
label set found in the response, including counters, gauges and histogram buckets,
counts and sums. Newly emitted series appear on the next scrape. A missing
series has no new value; Zabbix removes its item after the discovery lifetime.
The raw response has no history, while numeric items retain one day of history
and 30 days of trends by default. Adjust `{$FRED.METRICS.HISTORY}`,
`{$FRED.METRICS.TRENDS}` and `{$FRED.METRICS.NAME.MATCHES}` before linking many
high-cardinality exporters.

Zabbix 7.0 also limits one master item to 29,999 dependent items, so an
exporter above that size needs a narrower metric filter or separate endpoints.

Use a distinct host for each endpoint. The `fred` chart creates one metrics
Service per application with `metricsService.enabled` and sets the listening
address of that application's exporter itself: fred-agents on port 9000, the
Knowledge Flow API on 9111 and the Knowledge Flow worker on 9112. The Control
Plane does not expose `/metrics`. An agent pod serves KPI metrics on port 9000 by
default. A Knowledge Base pod serves KPI metrics on port 9000 and Temporal metrics
on port 9001 by default. These two exporters listen on `127.0.0.1` by default, so
the `agent-pod` and `knowledge-base` charts require `enabled: true` and an outward
address such as `0.0.0.0` under `observability.kpi.prometheus`, or
`observability.temporal.prometheus` for Temporal. Configure the URL to the
relevant pod or metrics Service. The `knowledge-base` chart also creates a metrics
Service. Avoid a load-balanced Service across replicas if per-process counters and
histograms need stable series. Each replica should have its own Zabbix host. The
`process_resident_memory_bytes` example below comes from `prometheus_client`, so
look for it on a Python KPI endpoint, not on the Temporal one.

This template collects raw samples, not PromQL expressions or Grafana panels.
It therefore covers metrics as they appear in each endpoint, including future
Fred KPI names, without a list maintained by hand. A Grafana JSON export is
useful for choosing a smaller set of graphs and alerts but is not required for
collection. To validate a host, check that the HTTP and parsed items are
supported, then inspect the discovery rule and a known numeric item such as
`process_resident_memory_bytes` in **Monitoring > Latest data**. The HTTP and
parsed item values are not stored.

Zabbix's [Prometheus check](https://www.zabbix.com/documentation/7.0/en/manual/config/items/itemtypes/http/prometheus)
and [Prometheus discovery](https://www.zabbix.com/documentation/7.0/en/manual/discovery/low_level_discovery/examples/prometheus)
describe the preprocessing used here.
