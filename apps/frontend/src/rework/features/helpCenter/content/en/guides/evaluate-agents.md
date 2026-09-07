---
title: Evaluate an agent
order: 50
description: Measure an agent's quality across evaluation campaigns.
icon: reviews
---

# Evaluate an agent

How do you know an agent answers well — and whether it improves when you adjust
its configuration? **Evaluations** give a measured answer rather than an
impression.

## Create an evaluation

From the [team settings](/help/en/features/teams), **Evaluations** section,
create an **evaluation**: give it a name and its cases. This is a reusable,
versioned definition — creating it does not run anything yet.

## Run it against an agent

Once the evaluation exists, trigger a **run** against the target agent. The
run executes each case and measures the agent's answers.

## Read the results

Once the run finishes, it shows each case's pass/failed/skipped result. Go
through them to spot the cases where the agent falls short and understand why.

## Iterate

Use the results to adjust the agent — system prompt, attached prompts,
document corpus — then trigger another run to check that quality is improving.
This **measure → adjust → re-measure** cycle is what moves an agent forward.

> Evaluation is especially useful before sharing an agent widely, or after a
> significant change to its configuration.
