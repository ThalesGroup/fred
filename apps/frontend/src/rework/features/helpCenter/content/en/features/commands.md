---
title: Commands
order: 45
description: Run a prompt from the input field, by typing /.
icon: bolt
---

# Commands

A **command** is a shortcut to a prompt from the conversation's space or your
personal space in the same organization. In a conversation, type `/` followed
by its name: when you send, the agent receives the prompt's
text directly, without going through the library.

It pays off on the requests you make over and over: a review, a summary, a
framed search.

## Give a prompt a command

At creation, each prompt receives a required **command name**, unique within
its space: 1 to 64 lowercase unaccented letters, digits, hyphens or `_`
characters, without spaces or `/`. For example: `summary`, `review`,
`internal-note`.

The command name is immutable. Space editors can still edit the title and
content. To make a variant with a different command, duplicate the prompt
and choose a new, available name. No suffix is added automatically when a
name is taken.

The library supports organization, team, project and personal spaces, but
the `/` menu does not combine all those libraries: it offers the conversation's
space and, when available, your personal space in the same organization.
Marketplace publications are not added. Two spaces can each have a `/summary`;
within one space, that name identifies only one prompt. See
[Prompts](/help/en/features/prompts).

## Run a command

In a conversation's input field, type `/`: the list of commands opens above
it. You can do this anywhere in your message, even when the field already
contains text: start the command after a space or on a new line.

Keep typing to search. The list keeps the commands whose name contains what
you type, in upper or lower case, and puts first the ones whose name starts
with it.

The list comes in three parts, each under its own title:

1. **Team "space name"**: the commands of the conversation's space;
2. **Personal space**: your commands in the same organization, when that space
   is accessible;
3. **Platform skills**: the skills the agent can use.

A part with nothing to offer does not appear. In your personal space, your
commands are listed once, under **Personal space**. If the commands cannot be
loaded, the list says so: type `/` again to retry.

If the conversation's space and you have a command with the same name, it
appears in both parts: pick the row you want, and that exact prompt is the one that runs. If
you type the name without picking a row, the conversation's space comes first,
then your personal space if it has none.

- **↓** and **↑** walk the list;
- **Enter**, **Tab** or a click add the command to your message, without
  sending anything;
- once the command is added, **Enter** sends the message;
- **Esc** closes the list and keeps what you typed.

So it takes two presses of Enter to run a command picked from the list: the
first adds it, the second sends. In between, you can complete your message.

The added command shows as a small label in your message. Click it to read the
prompt's text again before sending. The label holds as long as the command
stands on its own, with a space or a line break on each side: if you type a
character right against it, it becomes ordinary text again.

You can place several prompt commands and several platform skills anywhere in
a message, in the order you like; the list keeps offering your commands after
the first one. The text written before, between and after is kept. On send,
each prompt's text takes the place of its own command and all the chosen
skills are requested together. Each command has its own label, and you can use
the same command more than once.

For example, `First /summary then /tone please /verify-answer` sends "First",
the summary prompt, "then", the tone prompt, and "please /verify-answer", in
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

To adapt a prompt before sending it, go through the library instead: see
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

`/skill` is reserved and cannot be chosen as a prompt command name, either
when creating or duplicating a prompt.
