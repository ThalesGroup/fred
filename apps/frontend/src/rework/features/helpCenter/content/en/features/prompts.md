---
title: Prompts
order: 40
description: Create, organize and reuse text from your spaces.
icon: chat
---

# Prompts

A **prompt** is reusable text: a standard question, an instruction or a frame
for an answer. The **Prompts** page shows the library of the space you have
opened: **organization, team, project or personal space**. Each prompt belongs
to that space.

If you belong to several organizations, select the organization on Home before
opening its prompt library or your personal space.

The space's permissions determine what you can do. Read access lets you view,
copy and favorite prompts. The **Editor** role in that space also lets you
create, edit, duplicate and delete prompts, and manage their categories.
A technical Admin role alone gives no access to their content.

## Create, read, reuse

In the library, choose to create a prompt and fill in:

- **The title**, intended for readers, which you can edit later.
- **The logical name (command)**, required and unique within this space. Use 1 to 64
  lowercase unaccented letters, digits, hyphens or `_` characters, without
  spaces or `/`. For example, `summary` gives the command `/summary`.
  This name cannot be changed after creation; `skill` is reserved.
- **The content**, the complete text to reuse. It cannot be empty.
- An optional **description**, **category** and **tags**.

Click a card to read the complete text and copy it. The card's menu offers
management actions according to your permissions. Editing the title changes
neither the prompt's identity nor its command. Fields you leave untouched
remain unchanged.

**Duplicate** creates an independent prompt in the same space. Choose a new,
available command name; the title, content, description, category and tags
are copied. No command suffix is added automatically. Changes to the copy
do not affect the original.

## Categories and tags

**Categories** belong to the space. You can create and rename them, then assign
a prompt to a category or leave it **No category**. Before deleting a category
that is in use, reassign its prompts or remove their category. There is no
manual reordering, and no categories or sample prompts are created automatically.

**Tags** are optional labels: up to 20 per prompt, each at most 64 characters.
Library search matches the title, command name, description and tags. It combines
with category and favorites filters. Category numbers count their prompts;
they are not usage counters.

## Favorites

Click the **star** to add or remove a favorite. This choice belongs to your
account and changes neither the prompt's content nor its permissions. The
**Favorites** filter is available in the library and in a conversation's
prompt panel.

Revoking your access does not delete your favorites, but they do not let you
continue reading an inaccessible prompt. Deleting the prompt removes its
associated favorites.

## Where to use them

The pickers do not all offer the same library:

| Journey                                      | Available prompts and effect                                                                                                                            |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Prompts** page                             | Library of the open space, in any of the four space kinds, according to your permissions.                                                               |
| Home search                                  | Readable prompts from your spaces; a result opens its detail in its original space.                                                                     |
| Conversation prompt panel and `/` menu       | The conversation's space and, when available, your personal space in the same organization. In a personal conversation, that library appears only once. |
| Agent instruction field offering the library | Prompts from that agent's space only.                                                                                                                   |

In a **conversation**, selecting a prompt in the panel inserts its text into
the draft: you can adapt it before sending without changing the saved prompt.
A `/name` **command** resolves the current text when you send. See
[Conversations](/help/en/features/chat) and [Commands](/help/en/features/commands).

In an **agent's configuration**, selecting a prompt fills the field with a copy
of its text, which you save with the agent. This is not a live reference:
subsequently editing or deleting the library prompt does not update those
instructions. See [Agents](/help/en/features/agents).

The marketplace is a separate journey. Its publications are not added to the
conversation or instruction pickers described here.

## Ownership and an author's departure

The author records the prompt's provenance; it grants no special permission.
In a collective space, editors can edit and delete prompts even after their
creator leaves. Revoking access neither deletes prompts nor transfers them
to someone else.

Personal spaces remain private. Departure grants no new access to the library,
no exceptional recovery and no automatic transfer. Explicit publication of a
prompt does not grant access to the rest of that space.
