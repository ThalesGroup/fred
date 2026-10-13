---
title: Commands
order: 45
description: Run a prompt from the input field, by typing /.
icon: bolt
---

# Commands

A **command** is a shortcut to a prompt, yours or a team's. In a conversation,
type `/` followed by its name: when you send, the agent receives the prompt's
text directly, without going through the library.

It pays off on the requests you make over and over: a review, a summary, a
framed search.

## Give a prompt a command

On the **Prompts** page, any prompt can carry a command — one short word,
lowercase, no accents and no spaces: `summary`, `review`, `internal-note`. The
field sits just under the prompt's title.

> In your personal space, you can give a command to any of your prompts: it
> follows you into all your conversations. In a team, it requires the
> **Editor** role, like creating a prompt; every member of the team can then
> use it.

A command belongs to one space: two teams can each have their own `/summary`,
and you can have yours, but inside one team or inside your personal space it
can only point at a single prompt. A prompt without a command stays usable as
usual from the library.

When you import a prompt whose command is already taken in the receiving
space, a suffix is added (`/summary-2`) so both stay reachable.

## Run a command

In a conversation's input field, type `/`: the list of commands opens above
it. You can do this anywhere in your message, even when the field already
contains text: start the command after a space or on a new line.

Keep typing to search. The list keeps the commands whose name contains what
you type, in upper or lower case, and puts first the ones whose name starts
with it.

The list comes in three parts, each under its own title:

1. **Team "name of the team"**: the commands of the conversation's team;
2. **Personal space**: your own commands, offered whatever the agent;
3. **Platform skills**: the skills the agent can use.

A part with nothing to offer does not appear. In your personal space, your
commands are listed once, under **Personal space**.

If the team and you have a command with the same name, it appears in both
parts: pick the row you want, and that exact prompt is the one that runs. If
you type the name without picking a row, the team's command comes first, then
yours if the team has none.

- **↓** and **↑** walk the list;
- **Enter**, **Tab** or a click add the command to your message, without
  sending anything;
- once the command is added, **Enter** sends the message;
- **Esc** closes the list and keeps what you typed.

So it takes two presses of Enter to run a command picked from the list: the
first adds it, the second sends. In between, you can complete your message.

The added command shows as a small label in your message. Click it to read the
prompt's text again before sending.

You can place several prompt commands and several platform skills anywhere in
a message, in the order you like; the list keeps offering your commands after
the first one. The text written before, between and after is kept. On send,
each prompt's text takes the place of its own command and all the chosen
skills are requested together. Each command has its own label, and you can use
the same command more than once.

For example, `First /summary then /tone please /verify-answer` sends “First”,
the summary prompt, “then”, the tone prompt, and “please /verify-answer”, in
that order.

A message can hold up to 16 prompt commands. If one of them can no longer be
used, for example because its prompt was deleted, nothing is sent: a message
tells you which command to remove or choose again, and what you wrote stays in
the field.

## What the conversation shows

Your message appears as you typed it, with a label for each command instead of
the prompts' full text, so the conversation stays readable. Click a label to
open the text that was actually sent for that command, if you want to check
it. Copying the message gives the line you typed.

To adapt a prompt before sending it, go through the library instead — see
[Prompts](/help/en/features/prompts) and
[Conversations](/help/en/features/chat).

## Platform skills

Some agents come with skills: ready-made procedures provided by the platform.
When the agent offers some, they appear in the list under **Platform skills**.
Type `/`, choose a skill with **↑/↓** then **Enter**, **Tab** or a click, and
add a request if you wish. For example:

`/meeting-minutes Summarize these meeting notes: we chose option A; Alex will draft the proposal.`

As with a command, choosing a skill adds it to your message without sending
anything: press Enter again or use the send button. You can send
`/meeting-minutes` alone: the agent uses what the conversation already
contains or asks you for the missing notes. Some skills show, after their
name, a hint of what is useful to give them; it is never mandatory.

The skill stays where you insert it in the text. Typing its exact name with a
slash, then a space (for example `/meeting-minutes `), also selects it;
pasting uses the same format. Copying the whole message or selecting only the
skill's name keeps `/skill-name`. If a prompt has the same name as a skill,
pick the row you want in the list: their icon tells them apart.

The skills offered depend on the chosen agent. Depending on the agent, the
instructions of a requested skill are read before answering, or only if the
agent finds it useful. The agent may also decide by itself to use one or
several skills on an ordinary request. A line in the details of its answer
then shows the skill's name and who asked for it: you, the agent or an agent
it handed part of the work to. It stays visible when you reopen the
conversation.

A skill's instructions remain valid for the rest of the conversation and apply
when the request calls for them. They give the agent no additional tool or
permission.

`/skill` is reserved. An older prompt with that command remains available in the
library and editable; rename its command to restore its command shortcut. It
cannot be newly assigned, imported or promoted with the reserved command.
