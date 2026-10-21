---
schema: 1
title: "New admin-gated capability: create an Excel file"
impact: none
configuration: none
configuration_reason: "Adds the spreadsheet capability package to the fred-agents image; no configuration key, chart value or secret changes."
no_action_reason: "The capability ships inside the fred-agents image and is registered at pod boot; it stays closed until a platform administrator opens it for a team in the application, so no operator action is needed."
---
## Applicability

Existing Fred deployments upgrading to this release. Only the fred-agents image
changes: it gains the `fred-capability-spreadsheet` package and its pure-Python
dependencies `openpyxl` and `et-xmlfile`. Third-party agent pods are unaffected.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator action is required. The new
`spreadsheet` capability is admin-gated: a platform administrator opens it per
team in the application, then agent authors enable the "Create an Excel file"
pack in the agent form. Generated files are stored in the existing agent
workspace storage, like PowerPoint outputs.

## Validation

The fred-agents boot log lists the `spreadsheet` capability. After opening it
for a team and enabling it on an agent, asking that agent for an Excel file
shows a download chip for an `.xlsx` that opens in Excel or LibreOffice.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.
Agents that selected the capability lose the tool after rollback; files
already generated stay in workspace storage.

## Limitations

The workbook is limited to 10 sheets, 5,000 rows per sheet and 50,000 cells.
There is no in-chat preview.
