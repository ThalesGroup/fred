---
title: Where data lives
order: 20
description: The different data stores and what they hold.
icon: database
---

# Where data lives

The platform spreads data across several **stores**, each suited to a type of
information:

- **A file store** keeps your original documents (the files you upload and those
  produced by agents).
- **A vector store** holds the search **index**: the representation of documents
  that lets agents retrieve relevant passages and cite their sources.
- **A metadata database** tracks teams, agents, prompts, sessions, and documents
  — the "who, what, where" that structures the platform.
- **The identity provider and the permission service** manage accounts and
  access rights respectively.

This separation explains some administration operations, such as the **corpus
audit**, which checks consistency between the file store, the vector index, and
the metadata (see [Admin console](/help/en/features/admin)).

> The exact details (technologies, hosting) depend on your deployment's
> configuration.
