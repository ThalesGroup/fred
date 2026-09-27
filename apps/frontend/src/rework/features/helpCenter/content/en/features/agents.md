---
title: Agents
order: 10
description: Create an agent from a template, instruct it, give it functions.
icon: smart_toy
---

# Agents

An **agent** is an AI assistant configured for a specific purpose. Your team's
**Agents** page gathers them.

> Creating or editing an agent requires the **Editor** role. **Admin** alone
> does not allow it: the two roles are independent, not rungs on one ladder (see
> [Teams and permissions](/help/en/features/teams-and-permissions)).

## From a template to your agent

You start from a **template** the platform provides — for example one able to
search documents. You get your own agent, belonging to your team, which you tune
freely. You always talk to an agent of your own team.

## The four settings

- **Instructions** — the substantive brief: its role, its tone, its limits. This
  is the decisive setting; the others complete it.
- **Attached prompts** — prompts from the library that complete those
  instructions (see [Prompts](/help/en/features/prompts)).
- **Resources** — the document libraries the agent may consult. With nothing
  attached, it sees no document at all.
- **Functions** — what it can do beyond answering.

## What an agent can do beyond answering

The **Capabilities** tab decides what the agent is allowed to do: search the
team's documents, use an attachment, write a Word document, fill a PowerPoint
deck, produce a web page, take the time to reason step by step…

Two ways to choose, via the **Advanced** switch at the top of the tab:

- **Simple** (the default, and the recommended one) — you tick **packs**: sets
  that naturally belong together. One toggle turns on what is needed.
- **Advanced** — you enable each function one by one, with its options.

Simple mode covers ordinary needs. Advanced mode remains available at any
time.

> Expand a pack (**Included capabilities**) to see its detail. What each
> capability does, its limits and an example of use are on the
> [Capabilities](/help/en/features/capabilities) page. **The list the interface
> shows is the authoritative one**: it moves with the platform, and not every
> deployment opens the same capabilities.

### Enable only what the agent needs

Turning on every pack "just in case" is a common reflex, and it is the setting
that produces the least reliable agents.

**The agent chooses on its own among what you give it.** On every message it
decides which function to use. The longer the list, the more likely it takes
the wrong route, and the slower the answer. An agent holding the three
functions its mission needs is more predictable than one holding twelve.

**Some functions are expensive.** Exhaustive extraction, for instance, reads
the whole document: it is slow and asks for confirmation before every use. On
an agent that does not need it, it only ever gets triggered by mistake.

**Functions change the conversation interface.** Attachments add a button,
document production opens a side panel, resource access may show a library
selector. An over-equipped agent presents its users with controls its purpose
does not call for.

There is also a robustness point: an agent is **suspended** as soon as one of
the functions it depends on is withdrawn from the team. The fewer it depends
on, the less exposed it is.

The method that works starts from the use case: state in one sentence what the
agent must be able to do, enable strictly what that requires, then add more if
a gap shows up in practice. Adding a capability is always simpler than
diagnosing an agent that has too many.

### The three states of a function

Next to each pack's name, a row of dots gives the overall state:

- **Enabled** (filled dot) — active on this agent.
- **Available, not enabled** (empty circle) — your team may use it, but it is
  not active here. You can turn it on.
- **Not allowed** (red dot) — the platform has not opened it to your team. The
  pack still works with the rest; ask for it to be opened if you need it (see
  [Administration](/help/en/features/administration)).

## Duplicate, suspended, delete

- **Duplicate** — start from an existing agent to make a variant. The
  configuration is copied, but **not the files it references**: a PowerPoint
  template, for instance, has to be uploaded again on the copy.
- **Suspended** — a suspended agent stays visible but unusable. A function it
  depends on has been switched off, the team's access to it was withdrawn, or
  its configuration is no longer valid. See
  [Common problems](/help/en/troubleshooting/common-problems).
- **Delete** — deletion is permanent.
