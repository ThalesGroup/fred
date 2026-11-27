# Migration guide - v3.18.0

Upgrade from: `code/v3.17.0`
Operational impact: **minor** (minimum version: `3.18.0`).

Review these procedures together in the listed dependency order before deployment. Customer-specific values remain in their private repositories; Fred chart values are the production reference. Configuration files named configuration_prod.yaml are for local development only.

No-operation declarations describe ordinary deployment only. Conditional activation steps still require preparation. Validate combined upgrade and rollback in staging before production.

## Identify conversation traces and contact their owners

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.18.0/docs/swift/ops/migrations/conversation-trace-owner-outreach.md)

Trace detail fields are additive and come from existing data. Normal deployment requires no database migration, backfill, or special deployment order.

See the source note for applicability, validation and rollback.

## Supply the current UTC date to agent model calls

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.18.0/docs/swift/ops/migrations/current-date-agent-context.md)

### Applicability

Existing deployments upgrading agent pods with the new fred-runtime.

### Prerequisites

No additional prerequisites beyond the normal deployment procedure.

### Configuration

No configuration changes are required.

### Upgrade

Deploy updated agent pods normally. Existing agent instances receive the date
without a prompt or data migration. The `{today}` prompt token is retired;
stored prompts containing it remain unchanged and send that text literally to
the model. Authors relying on its substitution can revise those prompts, but
no edit is required for an agent to know the current date. External pods using
older images keep their previous behavior until updated.

### Validation

Ask an existing ReAct agent without `{today}` what today's date is. It should
answer with the current UTC calendar date, without a time. Repeat with an
agent whose stored prompt still contains `{today}`: the agent should know the
same date, while the stored prompt remains unchanged. Check a Graph agent
using `NodeContext.invoke_model` or `invoke_structured_model` if deployed.

### Rollback

Use the normal rollback procedure; no stored data was migrated. Older pods
resume their prior `{today}` substitution behavior.

### Limitations

The runtime supplies the UTC date, not the user's local date or current time.
Graph nodes calling `context.model` directly are outside this guarantee.

## Prevent repeated dialog scroll measurements from crashing chat

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.18.0/docs/swift/ops/migrations/fix-dialog-scroll-update-loop.md)

Existing data and APIs are unchanged; the fix takes effect with a normal deployment.

See the source note for applicability, validation and rollback.

## Prepare Fred v3.18.0 release inputs

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.18.0/docs/swift/ops/migrations/prepare-v3.18.0-release.md)

Release preparation adds no migration or configuration step; the other in-range notes describe the database migrations and optional actions.

See the source note for applicability, validation and rollback.

## Improve Resources table and file browser usability

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.18.0/docs/swift/ops/migrations/resources-explorer-usability.md)

### Applicability

Existing Fred deployments upgrading to this release.

### Prerequisites

The Control Plane database must be available for its Alembic migration.

### Configuration

No configuration changes are required.

### Upgrade

Apply the Control Plane migration adding `users_preferences.resources_tree_open`
before serving the updated frontend. Then deploy the updated backend and frontend.
Existing preference rows receive `false`, so the file browser starts closed.

### Validation

Open Resources with an existing account. The file browser starts closed, opens
from the table toolbar, and restores that choice after signing in on another
browser. Hover a long name and drag a labeled column boundary.
In the right-hand table, Shift-click a second row to select the visible range,
including any folders between the two rows.

### Rollback

Rollback the application normally. The older code ignores the added column;
retain it unless a full database rollback is required. A full rollback drops
the visibility choice.

### Limitations

Tree width and expanded folders remain browser-local and are not restored on
another device.

## Improve the router error page

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.18.0/docs/swift/ops/migrations/router-error-page.md)

Existing data and APIs are unchanged; the new page appears with a normal frontend deployment.

See the source note for applicability, validation and rollback.

## New admin-gated capability: generate and revise an Excel file

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.18.0/docs/swift/ops/migrations/3208-spreadsheet-capability.md)

### Applicability

Existing Fred deployments upgrading to this release. The fred-agents image
gains the `fred-capability-spreadsheet` package; its only new runtime
dependency is XlsxWriter, already present through python-pptx. The frontend
gains the spreadsheet preview panel. Third-party agent pods are unaffected.

### Prerequisites

- The fred-agents migration hook (`python -m fred_runtime migrate`) must run,
  as for any release: it now also creates the table `cap_spreadsheet_workbook`
  under its own version table `cap_spreadsheet_alembic_version`. The table
  holds the last workbook delivered per conversation and agent (a few KB to at
  most 4 MB per row), the base of later targeted changes.

### Configuration

No configuration changes are required. Deep agents keep workbook creation on
the parent; delegated children return data for the parent to publish.

### Upgrade

1. Deploy normally; the migration hook creates `cap_spreadsheet_workbook`
   before the pods roll. No existing data is migrated.
2. Optional activation: the new `spreadsheet` capability is admin-gated. A
   platform administrator opens it per team in the application, then agent
   authors enable the "Generate an Excel file" pack in the agent form. Generated
   files are stored in the existing agent workspace storage, like PowerPoint outputs.

### Validation

- `SELECT version_num FROM cap_spreadsheet_alembic_version;` returns
  `s5p1r2e3a4d5`.
- The fred-agents boot log lists the `spreadsheet` capability. After opening it
  for a team and enabling it on an agent, asking that agent for an Excel file
  shows a file card: its preview opens beside the conversation, and the `.xlsx`
  it downloads opens in Excel or LibreOffice. Asking "add a column ..." then
  produces `<name>-v2.xlsx`, marked as the latest version.

### Rollback

Use the normal rollback procedure. The older image does not read
`cap_spreadsheet_workbook`; the table and its version row can stay in place and
are reused on the next upgrade. Agents that selected the capability lose the
tool after rollback; files already generated stay in workspace storage.

### Limitations

The workbook is limited to 10 sheets, 5,000 rows per sheet, 50,000 cells and
5,000 model-written formula cells. The in-chat preview shows the first 500 rows
of each sheet. Each file is stored with a small `.preview.json` beside it in
the agent workspace; each request writes a new file. Only the last workbook of
a conversation can be revised. Deleting a conversation does not yet delete the
files it produced nor its stored workbook row.
