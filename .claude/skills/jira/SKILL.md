---
name: jira
description: Work with the Fred team's Jira Service Management help desk (project PRISM) through the `acli` CLI — triage a ticket, list your tickets, read descriptions and comments, download attached screenshots, post an internal analysis note, move a ticket's status.
user-invocable: true
argument-hint: <ticket key or question, e.g. "first pass on PRISM-68" / "my open tickets">
---

# Jira help desk (PRISM)

The team's bug / feature / support intake is **Jira Service Management**, driven from the
`acli` CLI. This skill exists so you do not have to rediscover `acli`'s shape — and its
three blind spots — on every session.

`PRISM` is the help desk (types: `Bug`, `Service Request`, `Improvement`, `Task`). `PM` is
a different, team-managed project — not the help desk.

If `acli` is missing, unauthenticated, or `jira.py` asks for a token, read `SETUP.md`.
Otherwise skip it.

## Rules

1. **Sign your analysis.** An internal note you post starts with a first line naming the
   agent: `**Claude Code first analysis**` (Codex → `**Codex first analysis**`). A reader
   must never mistake it for a human teammate's conclusion.
2. **Never post a public comment without the developer approving the exact text.** Public
   means the reporter gets an email. Show them the draft, wait for a yes, then post.
3. Do not transition, close or assign a ticket unless the developer asks — except the
   status moves in "Ticket status" and the PO handoff in the feature workflow below.

## Three things `acli` cannot do — use the helper script

`scripts/jira.py` (stdlib-only Python, run from the repo root or by absolute path).

### 1. Read a ticket properly

`acli jira workitem view PRISM-68` prints key, type, summary, status and assignee — **and
silently drops the description**, which is Atlassian Document Format (a JSON tree), not
text. A ticket looks empty when it is not. Use instead:

```bash
python3 .claude/skills/jira/scripts/jira.py show PRISM-68
```

which renders metadata, the ADF description, the attachment list and every comment as
Markdown, marking each comment `[internal]` or not.

### 2. Download attachments (screenshots)

`acli jira workitem attachment` can only `list` and `delete` — **there is no download
command**, which is why a screenshot on a ticket is otherwise unreachable.

```bash
python3 .claude/skills/jira/scripts/jira.py attachments PRISM-68 --list   # no token needed
python3 .claude/skills/jira/scripts/jira.py attachments PRISM-68          # download to a temp dir
python3 .claude/skills/jira/scripts/jira.py attachments PRISM-68 --out ./shots --name capture
```

It prints the local path of each file — then `Read` that path to actually look at the image.

### 3. Post an internal note

`acli jira workitem comment create` always uses the project default visibility. Internal
vs. public is the comment property `sd.public.comment`, reachable only over REST — `acli
comment visibility` is Jira roles/groups, a different mechanism, and not wired into
`create` anyway.

```bash
# Internal note — team-only, the reporter never sees it. This is the default.
python3 .claude/skills/jira/scripts/jira.py comment PRISM-68 -F analysis.md
python3 .claude/skills/jira/scripts/jira.py comment PRISM-68 -b "Reproduced on swift@a1b35c4."

# Check what will be sent without posting anything
python3 .claude/skills/jira/scripts/jira.py comment PRISM-68 -F analysis.md --dry-run

# Customer-visible reply — needs --yes on top of --public, and rule 2 above
python3 .claude/skills/jira/scripts/jira.py comment PRISM-68 -F reply.md --public --yes
```

The body is **Markdown**, converted to ADF: headings, bold, inline code, links (`[text](url)`
and bare `https://…` URLs), nested lists, quotes, rules and fenced code blocks all survive.
Jira never auto-links text posted over REST, so a URL is only clickable if the converter
marks it. Write the analysis to a file and pass `-F`; `-b` is for one-liners.

## Workflow — first pass on a ticket

Always start the same way: `jira.py show <KEY>`, then `jira.py attachments <KEY>` and
`Read` the images if it lists any. Move the ticket to "Analysis in progress" (below). Then
branch on the type.

### Ticket status

Keep the status in step with the work: the reporter watches it, and the team filters on it.

| When                                                                     | Move to                |
| ------------------------------------------------------------------------ | ---------------------- |
| You start investigating                                                  | `Analysis in progress` |
| A public reply asking the reporter a question is posted                  | `Waiting for customer` |
| Cause found, GitHub issue created, and the public reply is posted        | `Resolved`             |
| Fix deployed on the reporter's environment                               | `Closed`               |

```bash
acli jira workitem transition --key PRISM-68 --status "Analysis in progress" --yes
```

- Move only after the step is actually done. `Waiting for customer` and `Resolved` follow a
  public reply, so they wait for the developer's approval of that reply (rule 2).
- `Closed` usually comes days later, when a release reaches the reporter's environment. Do
  not close a ticket because a fix merged. Close it only when the developer says the fix is
  deployed there.
- These statuses exist on `Bug`, `Improvement`, `Service Request` and `Platform Incident`.
  `Task` and `Sub-task` use a different workflow (`Work in progress`, `Completed`, …), so
  ask before moving one.
- If a transition fails (a required field, or a status unreachable from the current one),
  report the error to the developer rather than trying another route.

### Bug

Try to **reproduce** it, and locate the cause in this repo (`git log`, `grep`, run it).

**Reproduced / cause found:**

1. Internal note: what happens, root cause, where in the code, how confident you are.
2. Open a GitHub bug so the fix is tracked, and link the ticket back:
   ```bash
   gh issue create --title "…" --body "Reported in PRISM-68 — <one-line repro>…"
   ```
3. Draft a public reply for the developer to approve (rule 2): thank the reporter, give a
   workaround if one exists, and include the GitHub issue link so they can follow the fix.
   The reporter is usually an end user, so keep the reply non-technical.
4. Once the reply is posted, move the ticket to `Resolved`.

**Not reproduced / need more information:**

1. Internal note: what you tried, what you ruled out, what is still unexplained — so the
   next person does not redo it.
2. Draft a public reply asking for exactly the missing pieces (version, steps, file,
   screenshot). Approval first, as always.
3. Once the reply is posted, move the ticket to `Waiting for customer`.

### Feature / improvement

The question is not *how* to build it — it is **how big is it**. Estimate the effort, the
rough delay, and the impact on existing code and contracts. Keep the internal note short:
a few lines and a size, not a design.

Then hand it to the PO:

```bash
acli jira workitem assign --key PRISM-68 --assignee 5f74d957ac3a2d006fd7b5ab   # Arnaud BARTHOLOME
```

## Common recipes (plain `acli`)

Always prefer `--csv` over the default table: the table is padded, truncated and
ANSI-coloured, which wastes context and mangles long summaries.

```bash
# My open tickets
acli jira workitem search --csv --fields "key,status,issuetype,summary" \
  --jql "project = PRISM AND assignee = currentUser() AND statusCategory != Done ORDER BY updated DESC"

# Everything untriaged
acli jira workitem search --csv --fields "key,issuetype,summary" --limit 50 \
  --jql "project = PRISM AND assignee IS EMPTY AND statusCategory != Done ORDER BY created DESC"

# Raw JSON when you need every field
acli jira workitem view PRISM-68 --fields "*all" --json
```

`acli jira workitem` also has: `create`, `edit`, `link`, `clone`, `transition`, `watcher`,
`archive`.

## Gotchas

- **`search` needs one of `--limit`, `--paginate` or `--count`** — it errors otherwise.
- **`search --fields` rejects fields `view` accepts** (e.g. `created` is "not allowed" in
  search). Keep search fields to `key,issuetype,status,priority,assignee,summary`; get the
  rest from `view`.
- **`acli jira workitem comment list --json` reports `visibility: public` for every
  comment**, including internal notes — it is Jira role visibility, not the JSM flag. The
  real flag is `jsdPublic`, visible only via `view --fields comment --json` (or `jira.py
  show`, which labels it).
- **Pasted screenshots live in the description as ADF `media` nodes**, whose `alt` is the
  attachment filename — that is how you map an inline image to a downloadable attachment.
  `jira.py show` renders them as `[attachment: <filename>]`.
- **Reporters are portal customers** (`accountType: "customer"`), not Atlassian users, so
  they do not resolve like teammates in JQL. Someone can hold both accounts — assign to the
  `atlassian` one, which is why the PO above is an account ID.
- **`customfield_*` on a PRISM ticket is mostly JSM plumbing** — SLA timers, request type,
  request language, organizations. Ignore it when triaging.
- Attachment `content` URLs in the API point at an internal Atlassian host; the script
  rewrites them onto the site domain (`https://<site>/rest/api/3/attachment/content/<id>`).
