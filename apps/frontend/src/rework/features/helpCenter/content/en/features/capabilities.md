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

### Documents

**What it does** - the agent reads and searches the documents you give it.
Two packs choose where it looks; turn on one or both:

- **Attachments** - users can attach files to the conversation (a paperclip
  appears in the chat). The agent reads them, summarizes them and answers
  questions about them.
- **Team documents** - the agent searches the team's documents and cites the
  useful passages. You can restrict it to specific folders.

With either pack, the agent can also read a document word for word or extract
information from it without omitting anything. The ways of reading are
detailed on [Resources](/help/en/features/resources).

**Its limits** - the search in team documents sees only the libraries attached
to the agent. An attachment stays in its conversation and is never added to
the team's documents. Search returns the passages it judges relevant: it is
fast, but not exhaustive. Comparing documents only works on team documents, so
it comes with the **Team documents** pack.

The **Documents only** conversation mode uses whichever document sources the agent allows, including attachments. See [Conversations](/help/en/features/chat#choosing-the-answer-sources).

**Examples** - with **Attachments** only, attach a contract and ask the agent
to list its deadlines. With **Team documents**, ask what the team's procedures
say about incident response.

This capability groups several functions, which the **Advanced** view separates:

| Function                 | What it does                                                         | Worth knowing                                                                                         |
| ------------------------ | -------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| Documents                | Searches the attachments, the team documents, or both                | May show a paperclip and a library or document selector in the conversation                           |
| Use tabular files        | Queries tabular files from libraries and attached CSV or Excel files | New CSV and Excel attachments are SQL-queryable; older Excel attachments may have only a text preview |
| Summarize a document     | Produces a document's summary                                        | Asks for your confirmation before each summary; adjustable length                                     |
| Compare documents        | Finds the passages closest to a given passage                        | Works on team documents, never on an attachment                                                       |
| Read a document verbatim | Returns the exact text, page by page                                 | The pages returned have a limited length                                                              |
| Extract information      | Goes through the whole document, omitting nothing                    | The slowest and most expensive; confirmation asked by default                                         |

Use tabular analysis to read the complete tables of attached CSV and Excel
files; the document reading tools are meant for text attachments.

In **Simple**, turning off one pack keeps what the other one still uses;
turning off both removes the **Documents** capability. In **Advanced**, the
**Documents** card starts with the **Attachments** and **Team documents**
switches: turning off both turns the card off. Existing agents keep
their settings until you change them.

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
checked on upload and marker errors are reported to you. An agent duplicated or
copied to another team takes its own copy of the template.

**An example** — a five-slide monthly review template, which the agent fills
each month from the period's documents.

### Generate a presentation

**What it does** — the agent builds a PowerPoint presentation from your
request, on your company template or, without one, on a built-in template. It
picks, for each slide, the template slide that fits the content best and fills
it; numbers become editable charts in the template's colours. The deck appears in a preview beside the conversation and downloads as
`.pptx`. The info button next to the download shows **What was built**: each
slide, its kind, and what was shortened, left out or continued on another
slide.

**How to set it up** — upload a `.pptx` template on the agent and save. The
template is then read in the background: meanwhile the agent shows
**Preparing** and is not available yet; it becomes available on its own when
the reading is done, and you can close the window in the meantime. Then
**Review slides** shows each slide found, with its name and kind: rename a
slide, change its kind, or set it aside. Nothing is mandatory.
To prepare a template the agent understands well, see
[Prepare your PowerPoint template](/help/en/guides/prepare-powerpoint-template).

**Use a vision model** — when a model that can read images is available, it
looks at each template slide to name it and understand what it is for. You
can choose which model does this, or keep the agent's own. Without such a
model, the switch is locked and slides are named by rules, which works but
names them less precisely.

**Enforce variety** — limits how many times the same slide comes back in a
presentation. **By slide name** (the default): each template slide is used at
most the chosen number of times. **By identified slide type**: each type
(bullet lists, for instance) comes back at most that many times, even on
different slides. With **1**, every slide is different; with **2** (the
default), a slide may come back once. The limit counts within each section:
sections built alike (one per country, for instance) may reuse the same slides.
When the template holds too few slides
for the presentation asked, the agent does its best. On the first presentation
of a conversation, the agent is asked to revise the slides that repeat too
much. Switch off: no limit. A change applies from the next presentation,
without reading the template again.

**Its limits** — the agent only uses slides the template holds: it does not
draw new ones. When the content does not fit any slide (too many items, for
instance), it splits or shortens it. If reading the template fails, the agent
stays unavailable: the form shows why, with a **Re-run analysis** button.

**An example** — "Prepare a ten-slide presentation of our quarterly results for
the executive committee."

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

**What it does** — a mode where the agent takes the time to break the problem
down before answering. It is not a capability you enable on the agent: it
follows the chosen language model and is set in the conversation (see
[Conversations](/help/en/features/chat#choosing-the-model-and-reasoning)).

**Its limits** — it is only offered with the models the administrator enabled
it for. Answers are slower and more expensive. It adds little to a simple
lookup, more to a multi-step analysis.

**An example** — comparing two offers across a dozen criteria and justifying a
ranking.

## Outside the packs

The **Simple** view presents packs: coherent sets, enabled with one
click on their card. The **Advanced** view may reveal capabilities belonging to no pack —
notably administration capabilities reserved for operations agents. They follow
the same rule as the others: your team only sees them if the administrator
opened them to it.

Some agents, such as guided workflow agents, come with their capabilities and
offer no packs. The form lists them under **Included with this agent**: they
stay on, and you set their options there, for example to bind the agent to
specific libraries.
