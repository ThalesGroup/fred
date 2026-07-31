---
title: Document resources
order: 40
description: Upload, organize, and index the documents your agents can query.
icon: folder
---

# Document resources

**Resources** are your team's documents. Once indexed, they become queryable by
agents, which can then answer based on them and **cite their sources**.

## Spaces

The **Resources** page distinguishes several spaces:

- **Team corpus**: the team's knowledge base, indexed for AI search and shared
  between members.
- **My space**: your private files within this team — drafts, templates — that
  only you see.
- **Team space** and **Agents**: files attached to the team or produced by
  agents.

## Libraries and upload

In the team corpus, documents are filed into **libraries** (folders). Create a
library first, then add documents inside it.

> A file left at the top level, outside a library, is **not indexed**: agents
> won't find it.

Common formats are supported: PDF, text documents, presentations (PPT),
spreadsheets (Excel/CSV), Markdown.

## Ingestion and statuses

After upload, each document goes through an **ingestion** phase (analysis and
indexing). Its status evolves: **Pending**, **Processing**, **Ready**, or
**Error** on failure. Only **Ready** documents are usable by agents.

Each document also shows its **origin** — **Uploaded** (imported by a member),
**Generated** (produced by an agent), or **Shared**.

![TODO: screenshot — the team corpus with statuses and origin](assets/resources-corpus.png)

## Managing documents

- **Rename** a document or a library.
- **Exclude from search** so a document is no longer taken into account by
  agents, without deleting it.
- **Preview** a document in the built-in viewer.
- **Delete** a document or a library (deleting a library also removes its
  content from the index).

## Storage

Each team has a **storage quota**. The page shows consumption and statistics by
file type (PDF, text, PPT, Excel, other). If you exceed it, trim the corpus or
contact an administrator.

A document ingested but never cited? See
[Document issues](/help/en/troubleshooting/documents-issues).
