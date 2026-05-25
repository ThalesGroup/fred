# Pull Request

> **Read this before you type anything.**
>
> Opening a PR is the _last_ step, not the first. If you designed this alone,
> implemented it without sharing the plan, and are now hoping the review will
> validate the approach — stop. Close this tab. Go read
> [`docs/swift/platform/DEVELOPER_CONTRACT.md`](../docs/swift/platform/DEVELOPER_CONTRACT.md)
> and come back when the steps below are already done.
>
> This is not process theater. Every question below exists because something
> went wrong when it was skipped. Fill them in honestly. A short honest answer
> beats a long evasive one every time.

---

## 1. What problem does this solve — and where is it tracked?

<!-- ID from docs/swift/data/id-legend.yaml (e.g. S1, CP-2, M1-F.3).
     If there is no ID, explain why this work exists at all. -->

**ID:** <!-- S1 / CP-2 / … / "no ID — mechanical fix because …" -->

**Problem in one sentence:**

**Backlog ref:** <!-- link to the [ ] checkbox in the relevant backlog file -->

---

## 2. Before you wrote a single line of code

This section cannot be skipped. If the answer to any question is "no" or
"I didn't", explain why — do not leave it blank.

**RFC written?**

<!-- For any design choice, schema change, new endpoint, or new component:
     paste the link to the RFC in docs/swift/rfc/.
     For a purely mechanical fix (one-function bug, typo, missing field
     already agreed on): write "not required — mechanical fix" and explain. -->

**Plan presented to the team before implementation?**

<!-- Did you share what you were going to build, which files you'd touch,
     which tests you'd add, which docs you'd update — and wait for a
     confirmation before starting? Yes / No + one line of context. -->

**Confirmation received?**

<!-- Who confirmed ("yes go ahead" / "ok" / "looks good")?
     If you were explicitly told "implement immediately", say so. -->

---

## 3. What you built

<!-- Be concrete. Not "updated the service" — say which function, which model,
     which endpoint, which component, and what it now does differently.
     Two or three sentences is enough. Ten vague words is not. -->

---

## 4. Proof of quality

**Tests added or updated:**

<!-- List exact test function names and the file they live in.
     If you added none, explain why none were needed. -->

| Test | File | What it covers |
| ---- | ---- | -------------- |
|      |      |                |

**`make code-quality` output (paste the last line or "all checks passed"):**

```

```

**Raw `basedpyright` output (required if a touched package keeps a non-empty baseline file):**

```

```

**`make test` output (paste the summary line — pass count, 0 failures):**

```

```

If you touched multiple packages, paste one block per package.

---

## 5. Docs updated

Work through this line by line. If an item does not apply, write "n/a" and say why.

| What changed                                                      | File updated |
| ----------------------------------------------------------------- | ------------ |
| Backlog `[ ]` item is now done                                    |              |
| New behaviour, API field, or contract change                      |              |
| Frozen contract touched (`execution.py`, `agent_app.py`, OpenAPI) |              |
| UX component implemented or visual status changed                 |              |
| Phase progress row exists for this area                           |              |
| WORKPLAN sprint item finished                                     |              |
| Code and a design doc now diverge                                 |              |

---

## 6. Close-out statement

<!--
Copy the exact block from the end of your implementation session.
If you don't have one, write it now — and wonder why you don't have it.
-->

```
## Task close-out
- Code:
- Tests:
- Docs updated:
- Backlog:
- Skipped steps:
```

---

## 7. Risk and rollback

**What breaks if this is wrong?**

**How do we roll back?**
