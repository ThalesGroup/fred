# fred-capability-word-template

Capability `word_template`: the agent fills and writes any Word (`.docx`)
template from the conversation, keeping its layout, styles and fixed text.
The engine knows no kind of template; each use case lives in the agent's own
system prompt.

A session's document is never edited in place: it is its base (a library
template or a Word file attached in the chat) plus the replayed log of
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
| `config` | Template library configuration and its save path (stores each new template, reads its parts) |
| `tools` | The model's tools (see below) |
| `middleware` | ReAct middleware: prompt overlay per model call, template analysis on first use, checks of each model step |
| `prompt` | Prompt fragments: principles, template choice, attachments, analysis, progress |
| `analysis` | One-call template analysis (role of each element, repeatable blocks), cached per sha256 of the base |
| `check` | Where the document stands: places still holding the template's own text |
| `documents` | The session's document for the tools: base, replayed log, trial of a batch before it applies |

Session and storage:

| Module | Role |
|---|---|
| `store` | SQL persistence (`cap_word_template_*`), own Alembic tree in `word_template_migrations/` |
| `session_document` | The session's current document (base + log), with a stored snapshot to skip the replay |
| `images` | Session images: chat images and pictures extracted from attached `.docx` files |

Frontend side panel:

| Module | Role |
|---|---|
| `router` | Session routes used by the frontend plugin |
| `content` | Structured, editable view of the current document ("Rédaction" tab); each place carries its address and operation |

## Tools

`read_template`, `edit_document`, `undo_last_edit`,
`remove_unused_template_parts`, `use_attached_document`, and
`select_template` when the library holds several templates. A batch that
changes the document's structure (removes content, adds a chapter, changes
fixed wording), removing the template's unused parts, undoing an earlier
turn's edit and switching the base to an attached file go through the
platform approval gate.

## Routes

Mounted under `/capabilities/word_template`, all under
`/sessions/{session_id}`; each one checks that the caller owns the session.

| Method | Path | Use |
|---|---|---|
| `GET` | `""` | Session state |
| `POST`, `DELETE` | `/attachments`, `/attachments/{attachment_id}` | Word files attached in the chat |
| `POST`, `GET`, `DELETE` | `/images`, `/images/{image_id}` | Session images |
| `GET` | `/document.docx` | Download the current document |
| `GET` | `/preview.pdf` | PDF preview (LibreOffice) |
| `GET` | `/content` | "Rédaction" view |
| `POST` | `/edits`, `/undo` | Collaborator edit, undo the last edit |

## Tables

`cap_word_template_sessions`, `_batches`, `_analyses`, `_snapshots`,
`_attachments`, `_images`. No foreign keys. Migrations: `make db-upgrade`,
`make db-check-heads`.

## Spec

The implementation contract is the OpenSpec change
[`openspec/changes/add-word-template-engine`](../../../openspec/changes/add-word-template-engine/).

## Registration

Installing this package *is* the registration: the fred-agents pod auto-discovers
the capability at boot via the `fred.capabilities` entry point declared in
`pyproject.toml` (`word_template = "fred_capability_word_template.capability:WordTemplateCapability"`).

## Tests

```
make code-quality
make test        # offline: fake store, fake assets, fake chat model
```
