---
title: Capabilities
order: 15
description: What each capability does, what it does not do, and when it is useful.
icon: extension
---

# Capabilities

A **capability** is something an agent can do beyond answering: search the
team's documents, fill a presentation, produce a web page. They are enabled in
an agent's **Capabilities** tab (see [Agents](/help/en/features/agents)).

This page describes each one: what it does, its limits, and a case where it is
useful.

> **The list the interface shows is the authoritative one.** It depends on the
> deployment and on what the administrator opened to your team: a capability
> described here may not appear, and a deployment may offer others.

## Data and knowledge

### Access to team resources

**What it does** — the agent consults the team's corpus: it searches for the
useful passages and cites them, reads a document verbatim, or extracts a piece
of information exhaustively. The three ways of reading are detailed on
[Resources](/help/en/features/resources).

**Its limits** — the agent only sees the libraries attached to its settings,
and a document uploaded outside a library stays invisible. Search returns the
passages it judges relevant: it is fast, but not exhaustive. The agent chooses
how to read, according to the request.

**An example** — "What do our procedures say about incident response time?" The
agent searches the corpus and answers, citing the passages it relies on.

This capability groups several functions, which the **Advanced** view separates:

| Function                 | What it does                                         | Worth knowing                                                          |
| ------------------------ | ---------------------------------------------------- | ---------------------------------------------------------------------- |
| Search team resources    | Finds the relevant passages and cites them           | May show a library or document selector in the conversation            |
| Use tabular files        | Uses the data of a CSV or Excel file from the corpus | The file must be uploaded into a library; this is not a reporting tool |
| Summarize a document     | Produces a document's summary                        | Asks for your confirmation before each summary; adjustable length      |
| Compare documents        | Finds the passages closest to a given passage        | Works on the corpus, never on an attachment                            |
| Read a document verbatim | Returns the exact text, page by page                 | The pages returned have a limited length                               |
| Extract information      | Goes through the whole document, omitting nothing    | The slowest and most expensive; confirmation asked by default          |

### Access to the team wiki

> **Beta.** The wiki carries a **Beta** badge in the team navigation: it is a
> proposal, not yet a settled feature. Its design may still change based on how
> it is used — feedback is welcome.

**What it does** — the agent reads the team's wiki pages and follows the rules
written there. Depending on the chosen mode, it can also **propose** pages and
edits. Enabling this capability for a team is also what gives its members a
wiki.

**Its limits** — no mode lets the agent delete, rename or move a page. A
proposal is always submitted to you before it is written. The wiki holds rules
and notes written by the team; it does not replace the document corpus.

**An example** — a team records its naming conventions in its wiki; the agent
in charge of writing minutes applies them without being reminded every time.

### Attachments in a conversation

**What it does** — adds a button to the conversation that attaches a file (PDF,
image, text) to a message. The agent can then summarize it, read it verbatim or
extract information from it.

**Its limits** — an attachment belongs to the conversation: it does not enter
the team's corpus and cannot be reused elsewhere. If this is the only capability
enabled, the agent works **only** on attachments and never queries the corpus.

**An example** — you receive a contract by email, attach it to a conversation
and ask the agent to list its deadlines.

## Document production

### Generate a Word document

**What it does** — the agent writes a document in a side panel opened beside
the conversation. The document is reworked over the exchanges, you can edit it
yourself, then download it as Word or Markdown.

**Its limits** — this is a text document: headings, paragraphs, lists. There is
no corporate template, no complex layout, no fine typographic control.

**An example** — "Write a summary note from the three reports we have just gone
through."

### Fill in a PowerPoint document

**What it does** — the agent fills a PowerPoint template you uploaded onto the
agent. Each place to fill is a marker placed in a slide and described in that
slide's comments; a marker may expect text, or an image taken from a resource
folder.

**Its limits** — the agent fills a template, it does not design a presentation:
without an uploaded template the capability does not work. The template is
checked on upload and marker errors are reported to you. A duplicated agent
keeps the configuration but **not the template file**, which has to be uploaded
again.

**An example** — a five-slide monthly review template, which the agent fills
each month from the period's documents.

### Generate a web page (HTML/CSS)

**What it does** — the agent produces a web page or component, shown in a
preview beside the conversation. The preview downloads as HTML, PDF or an
image.

**Its limits** — HTML and CSS only: no JavaScript, so nothing interactive. The
preview is read-only and the page produced stays modest in size; beyond that,
the agent has to trim it. This is not a publishing tool: nothing is put online.

**An example** — "Present these indicators as a one-page dashboard I can export
to PDF."

## Intelligence and orchestration

### Reasoning

**What it does** — opens a mode, in the conversation options, where the agent
takes the time to break the problem down before answering.

**Its limits** — this mode depends on the model in use and is not offered with
all of them. Answers are slower and more expensive. It adds little to a simple
lookup, more to a multi-step analysis.

**An example** — comparing two offers across a dozen criteria and justifying a
ranking.

## Actions and integration

This section of the **Capabilities** tab is meant for capabilities acting on
systems outside the platform. It is empty today.

## Outside the packs

The **Simple** view presents packs: coherent sets, enabled with a single
toggle. The **Advanced** view may reveal capabilities belonging to no pack —
notably administration capabilities reserved for operations agents. They follow
the same rule as the others: your team only sees them if the administrator
opened them to it.
