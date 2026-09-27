---
title: Common problems
order: 10
description: Sign-in, missing permissions, ignored document, suspended agent, interrupted answer.
icon: build
---

# Common problems

## I cannot sign in

Sign-in uses your organization account. Check your usual credentials. On an
expired session or a sign-in loop, refresh the page or reopen the tab. If it
persists, it is the access configuration: ask your administrator.

## I cannot see my team

It is probably **private** — it then appears only to its members — or it is
joined by being added. Either way, ask one of its members to add you. See
[Teams and permissions](/help/en/features/teams-and-permissions).

## I cannot do something

It is almost always a **role** question, and most often the same
misunderstanding: **Admin and Editor are two distinct permissions**, not two
rungs.

- Create or edit an agent, a prompt, a document → **Editor**. Being Admin is not
  enough.
- Manage members and settings → **Admin**. Being Editor is not enough.
- Run an evaluation campaign → **Analyst** or **Admin**.

Holding both sets of rights means holding both roles; a team Admin can grant
them. As for the platform administration pages, not seeing them is the expected
behaviour.

## A document is never used

In order of frequency:

1. **It sits outside a library.** A document dropped next to one is never read.
   Move it into a library.
2. **The library is not attached to the agent** you are questioning.
3. **It is still being prepared** — the _Processing_ tag is still there.
4. **It was excluded from search.** Include it again.

If preparation drags on or reports an error: be patient with a large document,
check the format is a common one, and upload it again if needed.

## An agent is visible but unusable

It is **suspended**. Three causes:

- A function it depends on was **switched off** for the team, or the team's
  access to it was **withdrawn**: only the platform can restore it (see
  [Administration](/help/en/features/administration)).
- One of its functions' **configuration** is no longer valid: untick the
  function on the agent, save, tick it again, save again.

A related case: a **duplicated** agent inherits the configuration but not the
files it references. A PowerPoint template, for instance, has to be uploaded
again on the copy.

## The answer stops or never arrives

Ask again: a network or processing hiccup is enough to interrupt an answer. If
the request is very broad, split it. An interruption that repeats across
**every** agent points to a platform incident; try again later.

## My attachment is refused

Check the format. Check too that the agent actually has the function that uses
attachments — without it, the file is ignored. For a document meant to last, use
the [resources](/help/en/features/resources).

## A conversation will not load

Refresh the page. If a single conversation stays unreachable while the others
work, it has probably been deleted — by you, or by the team's retention purge.
