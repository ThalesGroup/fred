---
title: Commands
order: 45
description: Run one of the team's prompts from the input field, by typing /.
icon: bolt
---

# Commands

A **command** is a shortcut to one of the team's prompts. In a conversation,
type `/` followed by its name and the agent receives the prompt's text
directly, without going through the library.

It pays off on the requests you make over and over: a review, a summary, a
framed search.

## Give a prompt a command

On the team's **Prompts** page, any prompt can carry a command — one short
word, lowercase, no accents and no spaces: `summary`, `review`,
`internal-note`. The field sits just under the prompt's title.

> Assigning a command requires the **Editor** role, like creating a prompt.
> Every member of the team can then use it.

A command belongs to one team: two teams can each have their own `/summary`,
but inside a team it can only point at a single prompt. A prompt without a
command stays usable as usual from the library.

When you import a prompt whose command is already taken in the receiving team,
a suffix is added (`/summary-2`) so both stay reachable.

## Run a command

In an **empty** conversation input field, type `/`: the team's commands open
above it. Keep typing to filter them.

- **↓** and **↑** walk the list;
- **Tab** completes the command without sending it;
- **Enter** sends it;
- **Esc** closes the list and keeps what you typed.

The `/` only opens the list at the **start of an empty message**: writing `/`
in the middle of a sentence stays ordinary text.

You can add text after the command: it is appended to the end of the prompt.
`/summary in ten lines` sends the summary prompt followed by "in ten lines".

## What the conversation shows

Your message appears as the command you ran, not as the prompt's full text, so
the conversation stays readable. A button on that message opens the text that
was actually sent, if you want to check it.

To read or adapt a prompt before sending it, go through the library instead —
see [Prompts](/help/en/features/prompts) and
[Conversations](/help/en/features/chat).
