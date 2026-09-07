---
title: Chat issues
order: 20
description: Interrupted answer, unavailable agent, rejected attachment.
icon: forum
---

# Chat issues

## The answer stops or doesn't arrive

- **Re-ask** the question: a network or processing hiccup can interrupt an
  answer.
- **Simplify** an overly broad request into several targeted questions.
- If the interruption repeats across all agents, it may be a platform-side
  incident — wait, then retry.

## An agent is unavailable or suspended

A **suspended** agent stays visible but unusable. Common causes:

- A capability the agent depends on was **removed or disabled**: only the
  **platform administrator** can re-enable it, from the Admin console (see
  [Capabilities](/help/en/features/capabilities)).
- The team's **access** to that capability was **revoked**: same fix, the
  platform administrator restores access from the Admin console.
- The capability's **configuration** is **invalid**: untick the capability on
  the agent, save, then re-tick it and save again.

## My attachment is rejected

- Check the file's **format** and **size** (see
  [Slowness and limits](/help/en/troubleshooting/limits)).
- For a document meant to last and be queried, go through
  [resources](/help/en/features/resources) rather than an attachment.

## A conversation won't load

Refresh the page. If one specific conversation stays inaccessible while others
work, it may have been deleted (by you or by the team's
[retention](/help/en/features/teams) purge).
