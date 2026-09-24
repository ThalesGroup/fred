---
title: Limits and data
order: 20
description: Quotas, processing time, who sees your content, what happens to a deleted conversation.
icon: shield
---

# Limits and data

## Quotas and volumes

Each team has a **storage allowance** for its documents. Near the limit, an
upload can be refused: tidy the corpus, or ask a team Admin for an increase.
Usage is shown on the Resources page.

There is **no strict per-file cap**: the figure shown in the upload dialog is
informative. What is enforced is the team's overall allowance — a large file
simply weighs more in it. That allowance does not cover conversation
attachments.

## Why it is sometimes slow

- **Preparing a document** depends on its size.
- **A very open question**, or one over a large volume, can reach processing
  limits. Narrow it down.
- Slowness that is general and persistent, while your request is reasonable,
  most likely points to a platform incident.

## Who sees your content

Your content belongs to a **team** and is visible only to its members. Your
**personal space** is visible only to you — not even to a platform admin. A
platform role gives access to no team data: that takes a role _inside_ the team.

## What happens to a deleted conversation

It is **hidden immediately**, then permanently erased at the end of the
**retention** period the team sets. With no period set, erasure is immediate.

## Your documents and the language model

To produce an answer, the **relevant excerpts** of your documents are sent to the
language model configured for your team — which may be provided by an external
vendor. Which vendor depends on your deployment's model routing, and your
platform administrator is the one who knows the terms that apply where you are.

Access to the documents themselves stays within the team: that governs which of
your colleagues can read them.

## How far can the answers be trusted?

An agent's answers should not be relied on without checking. An agent runs on a
language model: it can be wrong, and word an error confidently. The cited
sources exist for that — **open them** for any answer that matters. An agent
citing no source consulted no document.

## Personal data and compliance

Your deployment's dedicated page is available at `/gdpr`. The exact terms depend
on the configuration: when in doubt, ask your platform administrator.
