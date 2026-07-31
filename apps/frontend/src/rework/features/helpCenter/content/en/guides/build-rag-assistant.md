---
title: Build a document assistant
order: 10
description: From scratch to an agent that answers on your documents, citing its sources.
icon: school
---

# Build a document assistant

Goal: get an agent able to answer from **your** documents, citing its sources.
Four steps.

## 1. Prepare the team

[Create or join a team](/help/en/getting-started/join-create-team) to hold the
assistant and its documents. Everything you add afterwards belongs to it and
stays private to its members.

## 2. Build the corpus

On the [Resources](/help/en/features/resources) page, create a **library**, then
upload your documents into it. Wait for their status to reach **Ready**: only
indexed documents are usable.

Best practices:

- **Source quality**: prefer clean, up-to-date documents; drop duplicates and
  stale versions.
- **Structure**: well-structured documents (headings, sections) yield better
  citations than one massive, heterogeneous file.
- **Scope**: a corpus focused on one topic answers better than a catch-all.

## 3. Create the agent

On the [Agents](/help/en/features/agents) page, create an agent from a template
able to search documents. Attach the library built in step 2, and write an
**engagement prompt** that states its role and asks it to rely on the sources.

## 4. Test and iterate

Open a [conversation](/help/en/features/chat) and ask real questions. For each
answer, **check the cited sources**:

- Off-topic answers? Refine the engagement prompt or the corpus scope.
- Documents never cited? Check their ingestion status and see
  [Document issues](/help/en/troubleshooting/documents-issues).

Iterate until answers are reliable, then share the agent with your team.
