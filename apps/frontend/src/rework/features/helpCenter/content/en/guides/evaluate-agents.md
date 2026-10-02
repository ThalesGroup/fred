---
title: Evaluate an agent
order: 20
description: Measure an agent's quality instead of forming an impression of it.
icon: reviews
---

# Evaluate an agent

How do you know whether an agent answers well — and whether it improves when you
tune it? By measuring it, rather than relying on an impression formed over a
few questions.

> The standalone evaluator must be deployed, registered in Fred and enabled for
> your team. If it is missing from **Apps**, ask your administrator.

## 1. Create the evaluation

Select your team, open **Apps**, then open the registered evaluator application.
Create an **evaluation** there: a name and its cases. It is a reusable, versioned
definition — creating it runs nothing. Evaluations are no longer in team settings.

A good set of cases looks like what your colleagues will actually ask, including
the questions the agent **should not** be able to answer: that is how invented
answers are spotted.

## 2. Run it

Trigger a **run** against the agent. It goes through each case and measures the
answers.

## 3. Read and adjust

Each case comes back passed, failed or skipped. Go through the failures to
understand _why_: instructions too vague, corpus incomplete, question ambiguous.
Change one thing at a time, run again, compare.

It is this **measure → adjust → measure again** cycle that moves an agent
forward — and it is particularly worth it before sharing one widely, or after a
significant change.
