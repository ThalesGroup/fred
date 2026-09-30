---
title: Resources
order: 30
description: Upload the team's documents, organize them, understand how an agent reads them.
icon: folder
---

# Resources

**Resources** are your team's documents. They are what lets an agent talk about
_your_ content and show you the passages it relies on.

> Uploading, renaming or deleting a document requires the **Editor** role. Any
> member can browse them and question an agent that uses them.

## The team corpus

The **Resources** page holds the **team corpus**: the document base shared
between its members.

Documents go into **libraries**, like folders. Create a library first, then
upload your documents into it.

> **A document uploaded outside a library will never be used by an agent.** It
> is the first point to check when a document seems ignored.

Common formats work: PDF, text, Word, OpenDocument, PowerPoint, Excel, CSV,
Markdown, images and audio files. An unusual format may be refused; convert it
to a common one.

## A document of the same name already exists

If the target library already holds a document of the same name, Fred says so
**before** sending anything, and lets you choose:

- **Replace**: the existing document keeps its place and its links, only its
  content changes. Everything that cited it keeps working, and now points at the
  new version.
- **Skip**: your file is left out of the import, and the document already there
  is untouched.

You can answer once for every file concerned, or file by file. The same name in
**another** library is not a duplicate: those are two independent documents.

> If someone uploads that name while your import is under way, the question is
> simply put to you again in the follow-up panel: **Replace** or **Skip**. Your
> file is not lost, it is waiting on your answer.

## Following your imports

The dialog closes as soon as you confirm: you get Fred back straight away and
the transfer carries on behind it. A **panel** opens on the right of the page
and follows every file. You can fold it back into a button, reopen it, and widen
it by dragging its left edge.

Every file goes through four stages. The panel shows them as four markers
that tick off one by one, and names the one under way:

1. **Sending the file** — your browser is transferring it. For as long as this
   lasts, nothing has reached Fred yet.
2. **Preparing the document** — Fred has received the file and is filing it.
3. **Extracting the content** — Fred reads the document. This is almost always
   the longest stage: a large or scanned PDF can stay here for several minutes.
4. **Indexing** — Fred files away what it read so it can find it again.

**It is the end of the last stage, not the end of the transfer, that makes the
document usable by an agent.**

Once a file is through, its row reads **Ingestion complete** and then leaves on
its own after a few seconds: the document is in the table and there is nothing
left to follow. Only files that failed, or that are waiting on an answer, stay.

> None of these stages announces a percentage: Fred does not know how long it
> has left, and would rather not invent it. A stage that takes a while is not a
> stage that is stuck.

### If a file fails

It stays in the panel with the reason, and a **Try again** button for as long as
your browser still has the file at hand. If you reloaded the page in between,
the panel asks you to pick it again: a browser cannot reopen a file on its own.

### Cancelling a transfer

Files go a few at a time. The ones still waiting their turn can be cancelled
with one click; the ones already on their way belong to Fred and go through.

### If you close the tab mid-import

What already reached Fred carries on without you. The rest never left: on your
return, the panel **names the files that did not arrive** and offers to let you
pick them again. Only those are sent, to the same library.

## After the upload

On each document's row, a **Processing** tag shows for as long as the analysis
lasts and clears by itself: there is nothing for you to do. A marker may also
appear there when an import is waiting on your decision — one click opens the
panel, which is where the answer is given. Each document also shows where it
came from: **Uploaded**, **Generated** by an agent, or **Shared**.

## Managing documents

From the corpus: **rename**, **preview**, **delete**, or **exclude from search**
— the agent then stops taking it into account without the document disappearing,
and you can include it again.

Each team has a **storage allowance**, whose usage the page shows. Near the
limit, an upload can be refused: tidy up, or ask a team Admin for an increase.

## How an agent reads your documents

This behaviour explains the shape of the answers. The choice is not yours: the
agent decides from your request.

- **Search** — finds the most relevant passages and answers from them. Fast, and
  the right reflex for "what do we know about X?". It only surfaces what it
  judges relevant, so **it can miss things**.
- **Verbatim reading** — reads the exact text, in order, when you want a
  passage's precise wording.
- **Extraction** — goes through the whole document and lists everything that
  matches, omitting nothing. The slowest, the most exhaustive.
- **Summary** — a short overview, deliberately not exhaustive.

> **If nothing may be missed, say so**: "list _every_ deadline". The agent then
> uses extraction rather than search.

A document never used? See
[Common problems](/help/en/troubleshooting/common-problems).
