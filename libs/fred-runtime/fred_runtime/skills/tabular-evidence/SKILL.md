---
name: tabular-evidence
description: Analyze a mounted CSV with category and amount columns, reporting counts, totals, and the highest row.
argument-hint: "[absolute path to a CSV file under /inputs]"
---

# Tabular evidence

This skill requires the `code_sandbox` capability. If it is unavailable, explain that the analysis cannot run here.

1. Locate the requested CSV file under `/inputs/corpus` or `/inputs/attachments` and confirm it has `category` and `amount` columns.
2. Run `python /skills/tabular-evidence/analyze.py <absolute CSV path>` with `execute_code` in the sandbox.
3. Report the computed totals and the highest value, citing the source row number.
4. Do not claim that files outside the mounted input directory were inspected.
