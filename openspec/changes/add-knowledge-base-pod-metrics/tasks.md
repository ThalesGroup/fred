## 1. Shared pod identity

- [x] 1.1 Add the `app.runtime_id` model and its slug pattern to `fred-pod`, and make `fred-runtime`'s `PodAppConfig` reuse them; verify `fred-pod` and `fred-runtime` test suites pass unchanged
- [x] 1.2 Require `app` in the Knowledge Base `PodConfiguration`; verify a test that a configuration without `app.runtime_id`, or with `My KB`, fails to load naming the key

## 2. Metrics against the spec

- [x] 2.1 Add the `service` label to every `fred_kb_*` series and to the engine runtime's global tags, and `sdk` to `fred_kb_info` (D8); verify with the updated telemetry tests
- [x] 2.2 Add a contract test in `libs/fred-sdk/tests/test_knowledge_base_metrics_contract.py` that drives one run, one call per operation and one ingestion wait, then asserts every series name, type, label set and closed value set listed in the spec; verify with `uv run pytest tests/test_knowledge_base_metrics_contract.py`
- [x] 2.3 Review `telemetry.py`, `worker.py`, `documents.py` and `client.py` against each spec requirement (counted once per attempt, duration span, `interrupted` vs `error`, transport errors, no excluded label) and record any gap as a fix; verify by a short audit note in the PR description
- [x] 2.4 Check that author-registered series on the default registry are served on `/metrics`; verify with a test registering a custom counter
- [x] 2.5 Correct the `PodObservability` docstring to "nothing is reachable from outside unless bound outward" (D5); verify by review

## 3. Structured logs

- [x] 3.1 Replace the `basicConfig` call in the Knowledge Base entrypoint with a JSON-lines formatter carrying `ts`, `level`, `logger`, `msg`, `service`, `knowledge_base`, and a `text` format selected by `observability.logs.format`; verify with a test capturing stdout in both formats

## 4. Samples and docs

- [x] 4.1 Set `app.runtime_id` in `webdav-knowledge-base` (`config/configuration.yaml`, chart `values.yaml`) and in `fred-samples/knowledge-bases`; verify each pod starts locally
- [x] 4.2 Fix `KNOWLEDGE-BASE.md` §1 (two read-only ports) and add the missing *Operational metrics* section linking to the spec, with the PromQL for error rate, document throughput and ingestion latency and the matching log filter, without restating the series table; verify the anchor resolves
- [x] 4.3 Add a short *Metrics and logs* paragraph to the `fred-sdk` README Knowledge Base section: `app.runtime_id`, zero metrics code, how to add domain series, never team/instance labels; verify by review
- [x] 4.4 Update `docs/swift/ops/migrations/knowledge-base-pod-metrics.md`: breaking `app.runtime_id`, JSON logs, final series and labels; verify its Validation commands against a local pod

## 5. End-to-end check

- [ ] 5.1 Rebuild `webdav-knowledge-base` against this SDK, run one synchronization locally with metrics bound, and confirm `curl :9000/metrics` and `curl :9001/metrics` show the spec's series with `service` and `knowledge_base`, and that a log line's `service` matches; record the excerpt in the PR
- [x] 5.2 Run `openspec validate add-knowledge-base-pod-metrics --strict` and the `fred-pod`, `fred-sdk` and `fred-runtime` test suites; all pass
