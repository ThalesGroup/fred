---
schema: 1
title: "New admin-gated capability: generate an Excel file"
impact: none
configuration: none
configuration_reason: "Adds the spreadsheet capability package to the fred-agents image; no configuration key, chart value or secret changes."
no_action_reason: "The capability ships inside the fred-agents image and is registered at pod boot; it stays closed until a platform administrator opens it for a team in the application, so no operator action is needed."
---
## Applicability

Existing Fred deployments upgrading to this release. The fred-agents image
gains the `fred-capability-spreadsheet` package and its pure-Python
dependencies `openpyxl` and `et-xmlfile`; the frontend gains the spreadsheet
preview panel. Third-party agent pods are unaffected.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator action is required. The new
`spreadsheet` capability is admin-gated: a platform administrator opens it per
team in the application, then agent authors enable the "Generate an Excel file"
pack in the agent form. Generated files are stored in the existing agent
workspace storage, like PowerPoint outputs.

## Validation

The fred-agents boot log lists the `spreadsheet` capability. After opening it
for a team and enabling it on an agent, asking that agent for an Excel file
shows a file card: its preview opens beside the conversation, and the `.xlsx`
it downloads opens in Excel or LibreOffice.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.
Agents that selected the capability lose the tool after rollback; files
already generated stay in workspace storage.

## Limitations

The workbook is limited to 10 sheets, 5,000 rows per sheet and 50,000 cells.
The in-chat preview shows the first 500 rows of each sheet. Each file is
stored with a small `.preview.json` beside it in the agent workspace; each
request writes a new file. Deleting a conversation does not yet delete the
files it produced (same as PowerPoint outputs).
