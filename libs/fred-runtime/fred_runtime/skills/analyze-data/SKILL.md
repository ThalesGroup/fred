---
name: analyze-data
description: Analyze supplied tables or accessible datasets with explicit metric definitions, missing-data checks and conclusions supported by computed results.
argument-hint: "[data or document] [question or metric]"
license: Apache-2.0
metadata:
  author: Fred contributors
  provenance: Original Fred procedure; references record consulted documentation.
---

# Grounded data analysis

1. Identify the question, data source, population, period and unit of analysis
   from the request and conversation. Define the metric and comparison before
   calculating. Ask for missing data or a decision that blocks a useful result;
   state a reasonable non-blocking assumption so the user can correct it.

2. Read the actual data with the tools available for this request. For Fred's
   tabular tools, follow their capability instructions for discovery, schema
   inspection and scoped read-only queries; those instructions own SQL access.
   Choose the tool from its declared schema rather than inventing a function
   named after this skill. If no reader or query tool is available, work only
   from data visible in the conversation. Small complete tables can support
   transparent manual arithmetic; for larger or inaccessible sources, request
   a usable excerpt or access and explain which computation remains unverified.

3. Check the fields needed for the question: row meaning, duplicate keys,
   missing or non-finite values, units and currencies, date coverage and any
   sample or result limits. Keep missing values distinct from zero. State any
   exclusion or conversion that affects the answer. For joins, check whether
   repeated keys multiply rows before trusting totals. Aggregate near the data
   when possible; use bounded samples for inspection rather than retrieving a
   whole large dataset into the conversation.

4. Calculate the requested metric at the stated grain. Distinguish counts of
   rows from counts of observed values. For an overall rate, divide the sum of
   its numerators by the sum of its matching denominators; average subgroup
   percentages only when that weighting is the requested metric. Treat a zero
   denominator as undefined. Check period lengths, coverage and units before
   comparing groups or dates. Label estimates and partial results; use tool
   results or show the arithmetic, never invent a computed value.

5. Validate the result against independent checks useful for this question:
   reconcile subgroup totals, inspect unexpected ranges, and spot-check a
   representative case. Separate observations from explanations. A difference
   or correlation alone does not establish a cause. Describe uncertainty from
   small samples, missing data or changing populations; do not manufacture
   statistical significance, confidence intervals or forecasts.

6. Answer the question directly in the user's requested language. Give the
   result with its units and period, the source's human-readable name, the
   metric definition and material limitations. Include a compact results table
   or an appropriate supported chart when helpful. Keep internal table aliases
   and irrelevant raw records out of the answer. If the evidence cannot answer
   the question, identify the missing input and the next useful check.

For source and licensing details, see [the provenance notes](references/sources.md).
