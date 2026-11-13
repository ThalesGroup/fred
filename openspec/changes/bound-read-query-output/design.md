# Design

## Context

See proposal.md for motivation. `TabularQueryRequest.max_rows` currently defaults to null; `query_read` maps null to `default_max_rows=200`, clamps at `max_rows=1000`, wraps SQL with LIMIT and materializes a DataFrame. `RawSQLResponse` exposes rows and a message reserved for empty success. Helm values mirror both limits. MCP and generated HTTP consumers must retain their structured result contract.

## Goals / Non-Goals

Goals: preserve structured, complete rows while limiting model-facing data; distinguish omission from explicit null; bound worker memory when a row limit is disabled.

Non-goals: exact counts of all matching database rows, removing SQL-authored LIMIT, adding pagination, changing authorization or engine admission/time/memory settings, or guaranteeing a model-authored final warning.

## Decisions

1. Keep `max_rows` nullable and inspect field presence at the HTTP boundary: omitted uses configured `default_max_rows=500`; explicit null disables the tool-added limit; positive integers have no server ceiling; zero, negatives and the string `"none"` are invalid. Preserve this distinction through MCP invocation and serialization. FastMCP's OpenAPI director drops explicit null body fields, so the existing middleware records the explicit-null read_query argument in invocation-local context and the internal transport restores that field only on the tabular query route, resetting context after every call. Tool schemas explain JSON null / Python None. An authored SQL LIMIT always remains effective.
2. Replace deployment `query.max_rows` with positive `query.max_output_chars=50000`. Measure Unicode characters in the compact JSON `rows` array, including keys, escaped content, separators and array delimiters, using the actual row serialization rules. Metadata and message are outside this budget. Retain the longest ordered prefix fitting the budget; never skip an oversized row to include later rows. Exact equality fits.
3. Replace full DataFrame materialization with incremental fetching inside the existing DuckDB worker and abort lifecycle. Normalize values with the existing serialization semantics before budgeting. Retain only fitting rows. For finite limits, count up to that limit without accumulating omitted rows so a completed result below the limit can report its exact count. For unlimited reads, stop after observing the first row that exceeds the budget and do not scan or count the rest. DuckDB 1.5.4 execute eagerly materializes results; fetching chunks alone is insufficient. For unlimited requests, wrap SQL in a lossless execution LIMIT of floor((max_output_chars - 1) / 3) + 1. Even empty JSON objects require 3R+1 characters for R rows, so this extra row guarantees character overflow before any potentially fitting data is lost. This budget-derived internal bound is not a fixed semantic row ceiling. Keep finite requests bounded by their requested row limit for accurate counts. Fetch one native vector per batch to preserve existing DataFrame normalization; avoid blocking serialization on the async event loop. No extra COUNT query.
4. All model-facing tool messages are English, including empty success (developer clarification). Extend the response's existing `message`, emitted after `rows`, with success explanations. When character truncation occurs below a finite row limit, say `X of the Y rows matching the query were returned.` When the finite row limit is reached, say `X of the N requested rows were returned. Additional rows may match the query.` Without character truncation, a reached limit says `N rows were returned. The requested row limit was reached; additional rows may match the query.` With unlimited rows and character truncation, report X returned rows and that further rows were omitted, without a fabricated total. Character warnings append `The data volume was limited to avoid saturating the model context. Use more targeted queries to retrieve additional relevant data.` A first oversized row yields zero rows with a truncation explanation and advice to select fewer columns or shorten large fields. True empty results retain their existing success message.
5. Carry the tool-owned message through MCP and supported trace rendering after the data. Do not depend on the LLM generating the message. Update tool descriptions and packaged guidance without broad prompt changes. Preserve JSON validity and normal success status.

## Risks / Trade-offs

- Unlimited requested rows could otherwise exhaust memory: incremental consumption stops on character overflow and retains execution/admission budgets. A single huge value can still require allocation by the driver; verify that failure remains bounded by existing worker safeguards.
- Finite limits can request very large counts: counting discarded rows still costs time; keep cancellation and timeouts effective and do not promise exhaustive counts after an interrupted job.
- JSON character counts differ from tokens and bytes: test escaping, Unicode and typed/null values against real HTTP and MCP serialization. Do not present the budget as an exact token limit.
- SQL LIMIT and tool row limits are distinct: completeness is relative to submitted SQL. Reaching a finite tool limit uses cautious wording, even if exactly that many rows exist.
- Multiple replicas: no shared mutable state or coordination is introduced; configuration is local to each receiving pod. Document consistent values during rollout.

## Migration Plan

Update Knowledge Flow config, Helm values and generated schemas together. Document replacement of the retired `query.max_rows` key and the changed explicit-null semantics, regenerate HTTP clients from source, and check MCP argument-presence preservation. Existing deployment overlays must remove the old key; do not silently retain a hidden row ceiling. Add the required English migration note and apply repository release version policy. Roll back application and chart together to restore old semantics.
