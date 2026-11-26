# fred-capability-word-template

Capability `word_template`: the agent fills and writes a configured Word
(`.docx`) library template in chat, keeping its layout, styles and fixed text.
The engine knows no kind of template; each use case lives in the agent's own
system prompt.

A session's document is never edited in place: it is its library template
plus the replayed log of
operation batches. That log gives undo, authorship, and collaborator edits.

## Modules

Word engine (python-docx only, no Fred dependency):

| Module | Role |
|---|---|
| `docmap` | Map of a `.docx` with stable addresses (`P12`, `T3.R2.C4`, `H1.P2`, `X1.P3`), rendered as compact text and split into parts |
| `operations` | `set_text`, `replace_text`, `write`, `insert_after`, `repeat`, `remove`, `move`, validated as whole batches; `replay` of an operation log |
| `render` | The Markdown subset rendered into Word blocks with the template's own styles (lists, tables, images, `[À COMPLÉTER]` marker) |
| `inline` | Inline Markdown parser (`**bold**`, `*italic*`, `` `code` ``) |
| `toc` | Table of contents rebuilt from the headings after each batch (numbers, text, order); the download asks Word to update page numbers |

Agent side (what the model sees and does):

| Module | Role |
|---|---|
| `capability` | Manifest, `validate_config`, approval gates (`hitl_specs`), `tools()`, `middleware()` |
| `config` | Bounded library configuration and portable asset references |
| `tools` | The model's tools (see below) |
| `middleware` | ReAct middleware: prompt overlay per model call, checks of each model step |
| `prompt` | Prompt fragments: principles, template choice, analysis, progress |
| `analysis` | Analysis prompt, parsing and document roles used by durable preparation |
| `check` | Where the document stands: places still holding the template's own text |
| `documents` | The session's document for the tools: base, replayed log, trial of a batch before it applies |

Session and storage:

| Module | Role |
|---|---|
| `store` | SQL persistence (`cap_word_template_*`), own Alembic tree in `word_template_migrations/` |
| `session_document` | The session's current document (base + log), with a stored snapshot to skip the replay |
| `images` | Session images attached in the chat |

Frontend side panel:

| Module | Role |
|---|---|
| `router` | Session routes used by the frontend plugin |
| `content` | Structured, editable view of the current document ("Rédaction" tab); each place carries its address and operation |

## Template preparation

An agent editor can save up to eight Word templates. Organization Owners manage
an inherited library for each logical pod from capability settings. An agent's
own library replaces that inherited selection. Common replacements remain
candidates until prepared, so the previous effective original stays available.

Rust Control Plane owns upload receipts, membership, configuration revisions and
admission. The existing Temporal preparation workflow runs one durable activity
per original in the pod's preparation worker. Knowledge Flow completes the
analysis using a Control Plane-admitted organization text model. The capability
stores the prepared original and analysis under its preparation identifier; the
worker confirms readiness through Control Plane. No analysis starts during a
conversation. Failed preparations can be retried by saving the library again.

The session pins its chosen original and analysis. Replacing or removing the
library therefore leaves existing documents editable and downloadable. Copy and
marketplace export carry original files; installation prepares destination
originals under the destination authority. It never transfers private analysis
references.

Preparation cleanup uses the same write acknowledgement fence as PowerPoint.
An uncertain object write keeps cleanup unconfirmed until reconciled; this
implementation does not provide an automated reconciliation job.

## Tools

`read_template`, `edit_document`, `undo_last_edit`,
`remove_unused_template_parts`, and
`select_template` when the library holds several templates. A batch that
changes the document's structure (removes content, adds a chapter, changes
fixed wording), removing the template's unused parts, undoing an earlier
turn's edit go through the
platform approval gate.

## Routes

Mounted under `/capabilities/word_template`, all under
`/sessions/{session_id}`; each one checks that the caller owns the session.

| Method | Path | Use |
|---|---|---|
| `GET` | `""` | Session state |
| `POST`, `GET`, `DELETE` | `/images`, `/images/{image_id}` | Session images |
| `GET` | `/document.docx` | Download the current document |
| `GET` | `/preview.pdf` | PDF preview (LibreOffice) |
| `GET` | `/content` | "Rédaction" view |
| `POST` | `/edits`, `/undo` | Collaborator edit, undo the last edit |

## Persistence

`cap_word_template_sessions`, `_batches`, `_analyses`, `_snapshots` and `_images`
are owned by the Control Plane conversation root through cascading PostgreSQL
foreign keys. Analysis keys include the session identifier. Deletion of the
root removes these records and rejects late inserts. Prepared library originals
live separately in `_preparations` and capability object storage; retirement is
acknowledged through the preparation workflow.

This is a fresh Weaver installation, not a migration of Swift session data.
Apply the package Alembic tree with `make db-upgrade`; check its head with
`make db-check-heads`. See the repository's [Swift merge contract](../../../docs/SWIFT_WEAVER_MERGES.md).

## Registration

Installing this package *is* the registration: the fred-agents pod auto-discovers
the capability at boot via the `fred.capabilities` entry point declared in
`pyproject.toml` (`word_template = "fred_capability_word_template.capability:WordTemplateCapability"`).

## Tests

```
make code-quality
make test        # offline: fake store, fake assets, fake chat model
```
