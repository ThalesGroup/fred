---
schema: 1
title: "New admin-gated capability: generate and revise an Excel file"
impact: minor
configuration: none
configuration_reason: "Adds the spreadsheet capability package to the fred-agents image; no configuration key, chart value or secret changes."
---
## Applicability

Existing Fred deployments upgrading to this release. The fred-agents image
gains the `fred-capability-spreadsheet` package; its only new runtime
dependency is XlsxWriter, already present through python-pptx. The frontend
gains the spreadsheet preview panel. Third-party agent pods are unaffected.

## Prerequisites

- The fred-agents migration hook (`python -m fred_runtime migrate`) must run,
  as for any release: it now also creates the table `cap_spreadsheet_workbook`
  under its own version table `cap_spreadsheet_alembic_version`. The table
  holds the last workbook delivered per conversation and agent (a few KB to at
  most 4 MB per row), the base of later targeted changes.

## Configuration

No configuration changes are required.

## Upgrade

1. Deploy normally; the migration hook creates `cap_spreadsheet_workbook`
   before the pods roll. No existing data is migrated.
2. The new `spreadsheet` capability is admin-gated: a platform administrator
   opens it per team in the application, then agent authors enable the
   "Generate an Excel file" pack in the agent form. Generated files are stored
   in the existing agent workspace storage, like PowerPoint outputs.

## Validation

- `SELECT version_num FROM cap_spreadsheet_alembic_version;` returns
  `s5p1r2e3a4d5`.
- The fred-agents boot log lists the `spreadsheet` capability. After opening it
  for a team and enabling it on an agent, asking that agent for an Excel file
  shows a file card: its preview opens beside the conversation, and the `.xlsx`
  it downloads opens in Excel or LibreOffice. Asking "add a column ..." then
  produces `<name>-v2.xlsx`, marked as the latest version.

## Rollback

Use the normal rollback procedure. The older image does not read
`cap_spreadsheet_workbook`; the table and its version row can stay in place and
are reused on the next upgrade. Agents that selected the capability lose the
tool after rollback; files already generated stay in workspace storage.

## Limitations

The workbook is limited to 10 sheets, 5,000 rows per sheet, 50,000 cells and
5,000 model-written formula cells. The in-chat preview shows the first 500 rows
of each sheet. Each file is stored with a small `.preview.json` beside it in
the agent workspace; each request writes a new file. Only the last workbook of
a conversation can be revised. Deleting a conversation does not yet delete the
files it produced nor its stored workbook row.
