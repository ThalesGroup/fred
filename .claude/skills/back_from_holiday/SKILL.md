---
name: back_from_holiday
description: Catch-up digest after time off — everything merged since a given departure date, grouped by features / bug fixes / maintenance, with a dev vs devops split and a short "needs your attention" list. Read-only.
user-invocable: true
argument-hint: "<departure date — 2026-07-28, \"3 weeks ago\", or \"2026-07-28..2026-08-13\">"
---

# Back From Holiday Skill

You were away. This skill produces a **condensed** digest of what landed on the integration
branch while you were gone — not a commit dump. One line per change, grouped by intent, so a
developer can rebuild context in five minutes.

## Hard rules

- **Read-only.** No commits, no merges, no branch switching, no `gh issue close`, no file edits.
  `git fetch` is the only mutating command allowed (it only updates remote refs).
- **The departure date is mandatory.** Without it there is no window — never guess it from the
  reflog, the last commit date, or the developer's last authored commit. If `$ARGUMENTS` is
  empty, **ask for it** (Step 0), wait for the answer, then continue at Step 1.
- **Condense, don't transcribe. A digest nobody reads is a failed digest.** Hard budget:
  **~25 bullets total, one screen**, whatever the size of the window — 85 landed changes still
  produce ~25 lines. Per category, keep the ~6 highest-impact bullets and close with
  `+ N autres (voir git log)`. One line per change, ~15 words. Collapse all dependency bumps
  into a single line. When in doubt, cut: the developer can always ask for the detail on one
  item, but will never read a 90-line wall.
- **Rank by impact, not by date.** Within a category, the change that alters how the product
  behaves comes first; internal refactors last. Chronological order is the lazy order and it
  buries the important things in the middle.
- **Write for a human returning from leave**: what changed and why it matters to them. Keep the
  issue/PR number (`#2350`) — it is the clickable anchor — but no SHAs, no file paths in bullets.
- Answer in the language the developer used to invoke the skill.

## Step 0 — no date given? ask for it

If `$ARGUMENTS` is empty or holds nothing git can parse as a date, ask the developer — with
`AskUserQuestion`, header `Départ`, question *« Tu es parti à partir de quelle date ? »* — and
offer the usual windows plus free text for an exact date:

| Option        | Maps to             |
| ------------- | ------------------- |
| 1 semaine     | `--since="1 week ago"`  |
| 2 semaines    | `--since="2 weeks ago"` |
| 3 semaines    | `--since="3 weeks ago"` |
| *(Other)*     | the exact date typed, e.g. `2026-07-28` or `2026-07-28..2026-08-13` |

Do not run any `git log` before you have an answer — a digest over the wrong window is worse
than no digest. Once answered, continue at Step 1 with that value.

## Step 1 — anchor the window

Parse `$ARGUMENTS`:
- `2026-07-28` → window is `2026-07-28` → now
- `3 weeks ago` → pass verbatim to `--since` (git parses it)
- `2026-07-28..2026-08-13` → explicit `--since` / `--until`

Then pick the integration branch and refresh refs:

```bash
git fetch --all --prune --tags
git rev-parse --verify origin/swift >/dev/null 2>&1 && echo swift || echo main   # target branch
```

`swift` is this repo's integration/release branch (see `docs/swift/RELEASE-STRATEGY.md`); fall
back to `origin/main` only if `origin/swift` does not exist. State the resolved window and branch
in the output header — an off-by-one window silently hides a week of work.

## Step 2 — collect what actually landed

Use `--first-parent`: it yields exactly one entry per landed change (squash-merged PR **or**
merge commit) and skips the intermediate commits of each feature branch.

```bash
SINCE="2026-07-28"; BR=origin/swift                       # substitute from Step 1
git log --first-parent "$BR" --since="$SINCE" --date=short \
        --pretty=format:'%h|%ad|%an|%s' | cat
git log --first-parent "$BR" --since="$SINCE" --oneline | wc -l   # total, for the header
```

For each change, get the touched paths (drives the dev/devops split in Step 4):

```bash
git log --first-parent "$BR" --since="$SINCE" --name-only \
        --pretty=format:'@@%h|%s' | cat
```

Subjects here are terse and squashed PRs bury several sub-changes in the body. For any entry
whose subject does not make the user-visible impact obvious, read the body before writing its
bullet:

```bash
git show -s --format='%s%n%n%b' <sha>
```

Do this for the non-obvious ones only — not for all of them.

## Step 3 — classify by intent

From the conventional prefix, falling back to the body when there is none:

| Prefix                                   | Category            |
| ---------------------------------------- | ------------------- |
| `feat`                                    | 🚀 Features          |
| `fix`                                     | 🐛 Corrections       |
| `perf`                                    | ⚡ Performance        |
| `refactor`, `chore`, `style`, `test`      | 🧹 Maintenance       |
| `docs`                                    | 📚 Documentation     |
| `chore(deps)`, dependabot                 | 📦 Dépendances (one collapsed line) |
| no prefix                                 | classify from the body; if genuinely unclear, put it under Maintenance rather than inventing a category |

Do not create categories that would be empty — omit them.

## Step 4 — dev / devops split

Split **only if the window contains at least one devops-touching change**; with none, emit a
single flat set of categories (the developer asked for this split "si nécessaire", not always).

A change is **devops** when its touched paths are predominantly under:

- `deploy/charts/`, `deploy/docker-compose/`, `deploy/local/`
- `.github/workflows/`, `.pre-commit-config.yaml`, `.devcontainer/`
- `Dockerfile*`, root `Makefile`, `scripts/`
- chart `values*.yaml`, `configuration_*.yaml`

Everything under `apps/`, `libs/`, `docs/` is **dev**. A change touching both goes under dev with
a `(+ ops)` marker — it needs a deployment-side action but the substance is code.

**Alembic** (`**/alembic/versions/`) stays under dev but always also gets a line in Step 5:
a new migration means the schema moved under you.

## Step 5 — "needs your attention"

Short list, only what is actually true for this window. Skip any line that yields nothing.

```bash
# releases cut while away (code/ and chart/ are a pair per release — count releases, not tags)
git for-each-ref --sort=creatordate --format='%(creatordate:short) %(refname:short)' refs/tags \
  | awk -v d="$SINCE" '$1 >= d' | grep 'code/'
# new migrations → schema changed
git log --first-parent "$BR" --since="$SINCE" --name-only --pretty=format: \
  | grep 'alembic/versions/' | sort -u
# rules / contracts that moved while you were away
git log --first-parent "$BR" --since="$SINCE" --name-only --pretty=format: \
  | grep -E 'CLAUDE\.md|CONVENTIONS\.md|CONTRACT\.md' | sort -u
# your own branch drift
git rev-parse --abbrev-ref HEAD
git log --oneline HEAD.."$BR" | wc -l    # commits you are behind
```

If `gh` is available, add what is waiting **on the developer personally** — this is usually the
most actionable part of the digest:

```bash
ME=$(gh api user -q .login)
gh pr list --state open --author "$ME" --json number,title,reviewDecision,updatedAt
gh pr list --state open --search "review-requested:$ME" --json number,title,author
gh issue list --state open --assignee "$ME" --json number,title,milestone
```

## Output format

Whole block ≈ 25 lines. If it does not fit on one screen, it is too long — cut, don't scroll.

```
## Retour de congé — <YYYY-MM-DD> → <YYYY-MM-DD> (<N> changements sur <branche>)

### 💻 Dev
**🚀 Features**
- #2354 — Nom d'affichage des modèles pilotable depuis models_catalog.yaml — <auteur>
**🐛 Corrections**
- #2350 — Le budget de tour ReAct compte désormais la taille, plus seulement le nombre de messages — <auteur>
**🧹 Maintenance**
- ...
**📦 Dépendances** — 4 bumps (pypdf, mermaid, …)

### 🛠️ DevOps            ← omis si rien de devops sur la période
- #2053 — Montage des extraVolumes dans le hook de migration du chart — <auteur>

### ⚠️ À regarder en priorité
- 10 releases pendant ton absence : v2.1.25 → v2.1.34   ← une seule ligne, jamais la liste des tags
- 1 nouvelle migration Alembic (session_history) → schéma modifié
- CLAUDE.md modifié le 2026-08-01 (règle RFC vs doc)
- Ta branche feat/2360-quota-precheck a 37 commits de retard sur swift
- 2 PR à toi ouvertes, 1 review qui t'attend (#2361)
```

Close with the standard `## Task close-out` block from `CLAUDE.md`
(`Code: none — read-only digest`).
