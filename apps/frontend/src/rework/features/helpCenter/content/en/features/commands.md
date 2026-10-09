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

For a **ReAct agent**, the menu also offers your personal prompt commands
alongside the team's commands and platform skills. Labels identify each source.
If two prompts share a command, select the desired row: completion remembers
that exact prompt. Typing a prompt command without selecting a row uses the
team's prompt first, then your personal prompt if the team has no match. In your
personal space, the menu lists your personal commands once. Deep agents retain
their current behavior.

- **↓** and **↑** walk the list;
- **Tab** completes the command without sending it;
- **Enter** sends it;
- **Esc** closes the list and keeps what you typed.

You can place one available prompt command and several platform skills
anywhere in a managed-chat message, in either order. Completion keeps your text before and after
each token. On send, the prompt expands in place and all selected skills are
requested together. ReAct additionally offers your personal prompt commands
in team chats and preloads each distinct requested skill once. Deep uses native
model-driven reads; requesting a skill alone does not guarantee its loading.

For example, `Before /summary after /verify-answer` keeps “Before” ahead of the
summary prompt, and “after /verify-answer” behind it.

## What the conversation shows

Your message appears as the command you ran, not as the prompt's full text, so
the conversation stays readable. A button on that message opens the text that
was actually sent, if you want to check it.

To read or adapt a prompt before sending it, go through the library instead —
see [Prompts](/help/en/features/prompts) and
[Conversations](/help/en/features/chat).

## Platform skills

For agents whose runtime provides skills, type `/`, choose a skill with
**↑/↓** and **Tab** or **Enter**, then optionally add your request. For example:

`/compte-rendu Summarize these meeting notes: we chose option A; Alex will draft the proposal.`

Tab, a click or Enter completes the name without sending. Once the skill is selected, press Enter again or use the send button. You can send `/compte-rendu` alone. The agent uses relevant
conversation content or asks for missing notes. `argument-hint` appears when
a skill suggests useful input; it never makes that input mandatory for sending.
The skill stays where you insert it in the text. Typing its exact slash name followed by a space (for example `/compte-rendu `) also selects it; pasting uses the same format. Copying a full message or selecting only the skill name preserves `/skill-name`. For a homonymous prompt command, explicitly choose the prompt in the menu to run it.
The catalog depends on the selected agent. The agent may also
choose relevant skills on an ordinary request and use several before answering.
A compact step shows the skill name and whether you, the agent or a child agent
requested it, including after reopening the conversation.

Loaded instructions remain in the conversation context and apply when relevant
to the current request. They grant no additional tools or permissions.

`/skill` is reserved. An older prompt with that command remains available in the
library and editable; rename its command to restore its command shortcut. It
cannot be newly assigned, imported or promoted with the reserved command.
