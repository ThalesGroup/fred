---
title: Agent capabilities
order: 50
description: What an agent can do beyond chatting, chosen simply through "packs".
icon: extension
---

# Agent capabilities

A **capability** is something your agent can do on top of chatting with you:
search your team's resources for information, summarize a document, write a
Word file, fill in a PowerPoint deck… When you create (or edit) an agent, the
**Capabilities** tab is where you choose what that agent is allowed to do.

## Two ways to choose: Simple and Advanced

At the top of the tab, an **"Advanced"** toggle switches between two views:

- **Simple** (default, recommended): you pick **packs** — sets of capabilities
  that naturally go together. A single switch turns on everything you need,
  with no technical questions to answer.
- **Advanced**: you turn on and fine-tune each capability one by one, with its
  detailed options.

> **Our advice.** If you're not comfortable with the idea of the "tools" an
> agent uses on its own, **stay in Simple mode**. It covers everyday needs and
> spares you fine-grained settings that only matter for advanced use. You can
> always change your choice later.

## Capability packs (Simple mode)

Packs are grouped into **sections** by what they bring:

- **Data and knowledge**
  - **Access to team resources**: the agent can search and use your team's
    shared documents to answer. See the guide
    [Build an assistant on your resources](/help/en/guides/build-rag-assistant).
  - **Attachments in a conversation**: the agent can use the files you drop into
    a conversation — without reaching the rest of the team's resources.
- **Document production**
  - **Generate a Word document**: the agent writes a downloadable text
    document. See the guide
    [Producing documents](/help/en/guides/generate-documents).
  - **Fill in a PowerPoint document**: from a `.pptx` template, the agent fills
    in a finished presentation.
- **Intelligence and orchestration**
  - **Reasoning**: the agent takes time to think step by step before answering,
    for more complex questions.
- **Actions and integration**: empty for now — more capabilities will land here.

Turning on a pack automatically enables every capability it contains that is
**available to your team** (see just below). You don't have to switch each item
on by hand.

## See it at a glance: the three states

Each pack can be **expanded** ("Included capabilities") to see the individual
capabilities it bundles. Next to the title, a **row of small dots** already
tells you the overall state without expanding. Each capability can be in one of
**three states**:

- 🟢 **Active** (solid green dot): the capability is on for this agent. All
  good.
- ⚪ **Available, but not active** (empty grey circle): your team has access to
  it, but it isn't on for this agent — for instance because no one turned it on,
  or it was removed in Advanced mode. You can turn it on if you need it.
- 🔴 **Not allowed by the administrator** (red dot): the platform administrator
  hasn't opened this capability for your team. It can't be used, even if the
  pack is on.

When a pack contains at least one capability in that last state, a red
**"Missing capabilities"** note appears on the pack's row. It isn't blocking:
the pack works with the available capabilities, and the missing one(s) are
simply skipped. If you need it, ask your administrator to enable it for the
team.

## The administrator's role

It's the **platform administrator** who decides which capabilities are open to
your team, from the [Admin console](/help/en/features/admin). That's why some
capabilities may show up in red (not allowed): it's not a mistake on your side.

Finally, if a capability already used by an agent is **disabled** by the
administrator, that agent is **suspended** until it's restored (see
[Agents](/help/en/features/agents)).
