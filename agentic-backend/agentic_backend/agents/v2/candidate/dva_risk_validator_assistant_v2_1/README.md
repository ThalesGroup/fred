# DVA Risk Validator Assistant v2.1

This package provides two standalone candidate V2 agents:

- `DVARiskValidatorGraph` (`candidate.dva_risk_validator.graph.v2_1`)
- `DVARiskValidatorQA` (`candidate.dva_risk_validator.qa.v2_1`)

Both definitions expose chat options with `default=True` for:

- `chat_options.attach_files`
- `chat_options.libraries_selection`
- `chat_options.documents_selection`
- `chat_options.search_rag_scoping`

## Graph Agent

`DVARiskValidatorGraph` validates DVA risk treatment evidence, enforces blocker
rules, produces inferred recommendations, and publishes:

- `result.md`
- `risk_index.json`

```mermaid
flowchart TD
  START([Start]) --> route_or_start
  route_or_start --> ask_max_risk_count
  ask_max_risk_count --> locate_risk_table
  ask_max_risk_count --> ask_max_risk_count
  locate_risk_table --> extract_source_risks
  locate_risk_table --> maybe_ask_risk_section
  maybe_ask_risk_section --> extract_source_risks
  extract_source_risks --> enrich_to_requested_count
  enrich_to_requested_count --> retrieve_coverage_evidence
  retrieve_coverage_evidence --> validate_treatment
  validate_treatment --> recommend_strategy
  recommend_strategy --> recommend_actions_mitigations
  recommend_actions_mitigations --> build_report
  build_report --> publish_outputs
  publish_outputs --> persist_session_scope
  persist_session_scope --> finalize
```

## QA Agent

`DVARiskValidatorQA` is a dedicated standalone ReAct definition for grounded
follow-up questions over:

- original DVA context
- generated graph report
- generated risk index

```mermaid
flowchart TD
  user[User question] --> retrieve[knowledge.search]
  retrieve --> grounded[Grounded answer drafting]
  grounded --> sources[Append Sources section]
```

## Session Scope Merge

Graph completion uses `merge_session_scope(...)` to preserve existing selected
libraries/documents and append generated artifact `document_uid` values while
setting `include_session_scope=True`.
