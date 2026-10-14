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

## The recommended language model

In the **General** section, **Recommended model** picks the language model
conversations with this agent start on. **Team default model** (the first
option) uses the team's default model and follows it when the team admin
changes it. Picking a specific model, even today's default, keeps that model
whatever happens to the default. Only the
models enabled for the team are offered. Members can still pick another model
in the conversation (see [Conversations](/help/en/features/chat)).

Reasoning is no longer set on the agent: it follows the chosen model.

## Let the creation assistant draft your agent

Writing good instructions (the "system prompt") takes practice. Once you have
chosen a template, the **Assistant** button at the top of the agent
form helps you get started, for a new agent or an existing one:

1. Describe in your own words what the agent should do: its role, its mission,
   who it talks to, its tone, what it must not do. A few sentences are enough.
2. Click **Suggest**. After a few seconds the assistant proposes a name, a
   role, a short description, instructions and the capabilities that look
   useful for this agent.
3. Read the proposals. Everything is ticked: untick what you do not want. If
   nothing fits, edit your description and ask again.
4. Click **Apply**: only the ticked items are filled in. Ticked capabilities
   replace the current selection.

If a ticked item would replace something you already wrote, the assistant asks
you to confirm first. Nothing is saved until you save the agent: you can still
change everything.

## What an agent can do beyond answering

The **Capabilities** tab decides what the agent is allowed to do: search the
team's documents, use an attachment, write a Word document, fill a PowerPoint
deck, produce a web page…

Two ways to choose, via the **Advanced** switch at the top of the tab:

- **Simple** (the default, and the recommended one) — you turn on **packs**: sets
  that naturally belong together. One click on the card turns on what is needed.
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

**Functions change the conversation interface.** The **Attachments** pack adds
a paperclip, document production opens a side panel, **Team documents** may
show a library selector. An over-equipped agent presents its users with controls its purpose
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

## Duplicate, copy, suspended, delete

- **Duplicate** — start from an existing agent to make a variant in the same
  team. Everything is carried over, including its files such as a PowerPoint
  template.
- **Copy to…** — give a copy of the agent to another team or to your personal
  space. See below.
- **Suspended** — a suspended agent stays visible but unusable. A function it
  depends on has been switched off, the team's access to it was withdrawn, or
  its configuration is no longer valid. See
  [Common problems](/help/en/troubleshooting/common-problems).
- **Delete** — deletion is permanent.

## Copy an agent to another team

The **⋮** menu of an agent card offers **Copy to…**. Pick one or more spaces:
your personal space and the teams where you are an **Editor**. You also need to
be an Editor of the agent's own team.

Each team gets its own agent, independent of the original: changing one does
not change the other. Every editor of the team can use and adjust it right
away. If the name is already taken, the copy is numbered, for example
`Analyst (copy 1)`.

**What is carried over**: the agent's name, description, instructions and
settings.

**What is reset**: choices that belong to the origin team — a library, a
folder or documents picked for the agent. The capability stays enabled, but it
now works on the new team's resources. An agent that read its team's wiki will
read the wiki of the team receiving the copy.

**What is recreated**: configuration files, such as a PowerPoint template, are
uploaded again in the new team, as if an editor had done it there. If the
template takes its images from folders the new team does not have, those image
fields stay empty: a message tells you which folders to create, then to upload
the template again.

**What is never copied**: conversations and the files the agent produced.

Before you confirm, the window flags the teams that cannot receive everything:

- **Agent template not enabled** — the team has no access to this agent's
  template. It cannot be picked.
- **Missing capabilities** — the team does not have every capability of the
  agent (hover the message for the list). You can still copy: the agent will
  work there without them, with its instructions intact. To get them, ask for
  them to be opened (see [Administration](/help/en/features/administration)).

## The agents marketplace

The **marketplace** (**Marketplace → Agents** in the sidebar) lists the agents
teams have chosen to share with the whole organization. Anyone can browse it,
search it, open an agent's card, like it and import a copy of it. The search
also looks at team names. To see only one team's agents, click its name at the
top of a card; remove the filter with the cross on the **Team** label under the
search.

### Who can publish

Every **Editor** of the team can publish, once the platform administrator has
enabled publishing for it (see
[Teams and permissions](/help/en/features/teams-and-permissions)). An Editor
finds **Publish to the marketplace** in the **⋮** menu of an agent card. The
action is greyed out, with the reason, when:

- the team is **private** — only public teams publish;
- the team has reached the **number of published agents** the platform
  administrator allows it;
- the agent relies on an agent type reserved to platform administrators.

Agents of your personal space are never published.

### What publishing shares

Publishing shares a **snapshot** of the agent: its name, description,
instructions and settings, plus a copy of its configuration files, such as a
PowerPoint template. Everyone in the organization can read that configuration,
so check it before you confirm: a window recalls it and asks you to tick
**I understand**.

Choices that belong to your team are **not** shared: libraries, folders and
documents picked for the agent are left out of the snapshot.

### Published, then Modified

Once published, the card shows **Published** at the bottom, with its likes and
imports. Your team keeps using and editing the agent as usual. After a change,
editors and the team admin see **Modified, not republished**: the
marketplace still shows the previous version. An Editor who saves a change
is offered to republish it straight away; **Ignore** keeps the previous
version listed.

### Removal from the marketplace

An Editor or the team admin can take an agent down with **Remove from the
marketplace** in the **⋮** menu. It stays in the team, unchanged.

The agent is also removed **automatically** when:

- it is deactivated, suspended or deleted;
- the team becomes private;
- the platform administrator turns publishing off for the team;
- a platform administrator removes it, possibly with a message.

After an automatic removal, the card shows **Removed from the marketplace**.
Click it to see why, when, and the administrator's message if there is one.
Editors and the team admin can **Hide** this notice for the whole team.
Publishing the agent again puts it back on the marketplace.

### Likes

Click the heart of a marketplace card to like an agent, even one of your own
team; click again to take your like back. The card shows the total. An agent's
card in detail also tells how many likes it received **since its last
update**, so you know whether the current version is the one people
appreciated. Likes and imports are kept when an agent is removed and later
published again.

### Import a copy

**Import** (on the card or in the agent's detail) copies the agent into your
personal space or into teams where you are an **Editor**. The team that
published it is not offered. Before you confirm, each team shows what the
agent would lose there, for instance a capability the team does not have; a
team without access to the agent type cannot be picked.

**Your copy is independent**: later updates made by the publishing team do
not reach it, and your changes do not reach them. If the name is already
taken, the copy is numbered, for example `Analyst (copy 1)`.

Once imported, the window lists, per team, what to set up again there:
libraries, documents and folders the agent should use, and anything a
capability asks you to redo.
