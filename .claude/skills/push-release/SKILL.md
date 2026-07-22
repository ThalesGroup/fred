---
name: push-release
description: Cut a Fred release on the current release branch — write user-facing release notes for every change since the last tag, then (after developer sign-off) tag code/vX.Y.Z + chart/vX.Y.Z and push. Stops for approval before any tag is placed.
user-invocable: true
argument-hint: "[tag]"
---

# Push Release Skill

Cut a release on the **current release branch** (`swift`). A Fred release is
**two annotated Git tags on the same commit** — `code/vX.Y.Z` and `chart/vX.Y.Z` — each
driving its own CI workflow. This skill prepares the release notes, presents them, and
**waits for explicit developer approval before placing or pushing any tag.**

Ground truth for the mechanics: `docs/swift/RELEASE-STRATEGY.md`. Read it if anything below
is ambiguous.

## Hard rules

- **Never tag or push without explicit approval.** Step 5 is a mandatory stop. Presenting the
  updated `release.md` and getting a clear go-ahead is the whole point of this skill.
- **The two tags are a pair on one commit.** `code/vX.Y.Z` builds and pushes the Docker images;
  `chart/vX.Y.Z` packages and pushes the Helm chart. A bare `vX.Y.Z` (no prefix) publishes
  **nothing** — never tag that way.
- **Notes are user-facing.** Write for someone using Fred, not building it. No `ports`,
  `adapters`, `vectors`, `map-reduce`, `SSE`, class names, or file paths in the summary/bullets.
  Describe what the user can now *do* or what stopped breaking. Match the voice of the existing
  entries in `apps/frontend/public/release.md`.
- **Notes are committed, then tagged.** The tag must point at a commit that already contains the
  new `release.md` entry. Order: edit → commit → tag both → push.
- Tags are **annotated** (`git tag -a`), created on `HEAD` of the release branch. No promotion to
  `main` — tags live on the branch they were cut from.

## Step 1 — establish the branch and the last release

```bash
git rev-parse --abbrev-ref HEAD                 # the release branch (swift/eagle/…)
git tag -l 'code/*' | sort -V | tail -1         # last code tag, e.g. code/v2.1.10
git status --short                              # working tree should be clean (untracked .claude/worktrees/ is fine)
```

If the working tree has uncommitted **tracked** changes, stop and ask — a release should be cut
from a known-good tree, not with unrelated edits in flight.

## Step 2 — collect every change since the last tag

```bash
LAST=code/v2.1.10                               # substitute the tag from Step 1
git rev-list --count "$LAST"..HEAD              # 0 → nothing to release; stop
git log --oneline "$LAST"..HEAD
```

For **each** commit, read the full message body — the subject line is not enough to write a good
user-facing note:

```bash
git show -s --format='%H%n%s%n%n%b' <sha>
```

Squashed PRs bury several sub-changes in one body (see the PPT-filler and document-access commits
for the pattern). Mine the body for the user-visible ones. Group findings into the standard
sections: **Features**, **Improvements**, **Bug Fixes**, **Security**, and — only when an operator
must act on upgrade — **Deployment note**.

Skip purely internal commits from the notes (Docker build fixes, lockfile relocks, code-quality
passes, schema regen) — they ship, but they are not release-note material. When in doubt about
whether a change is user-visible, keep it out of the summary and ask.

## Step 3 — decide the version

Default: **bump the patch** (`v2.1.10 → v2.1.11`). The whole 2.1.x line has shipped features under
patch bumps — do not reach for a minor/major bump on your own. If `$ARGUMENTS` gives a version, use
it. Otherwise propose the next patch and let the developer override at the Step 5 gate.

Bump minor/major **only** when the developer says so, or when there's a genuine breaking change or a
milestone the developer has called out — never infer it from the commit types alone.

## Step 4 — write the release notes

Prepend a new entry to the top of **`apps/frontend/public/release.md`** (the only canonical
copy — `frontend/dist/release.md` is a build artifact, never edit it). Use today's date from the
session context. Follow the exact shape of the existing entries:

```markdown
**vX.Y.Z** — YYYY-MM-DD

- **Summary**

  <2–5 sentences, user-focused. Lead with what the user can now do. Plain language.>

- **Features**

  - <one capability per bullet, phrased as user benefit, with (#issue) refs at the end>

- **Bug Fixes**

  - <what used to go wrong, from the user's seat, with (#issue) refs>
```

Writing guidance, distilled from the existing notes:

- **Keep it short.** One line per bullet, one benefit. Trim caveats and mechanism — the developer
  has said the notes must stay concise. If a bullet needs a second clause to breathe, it's too long.
- **Summary first, benefit first.** "Agents can now browse your document library and summarize any
  file on demand" — not "adds DocumentTreePort and a summarize adapter".
- Keep the section set that applies; omit empty sections. Order: Summary → Features → Improvements →
  Security → Bug Fixes → Deployment note (match neighbours).
- Keep `(#1234)` issue/PR refs — they are part of the house style. Library version bumps
  (`fred-core 3.4.7`) are fine **inside a bullet** when they matter to an operator, but never in the
  Summary.
- A **Deployment note** is required when the upgrade needs a config change, a new required value, or
  a migration. Say plainly whether existing deployments need to do anything ("additive only, no
  action needed" is a valid and useful note).

## Step 5 — present and STOP for approval (mandatory)

Show the developer the **full new entry** verbatim, plus:

- the branch, the last tag, and the proposed new version,
- the two tags that will be created (`code/vX.Y.Z`, `chart/vX.Y.Z`) and what each publishes,
- the commit + push commands you will run.

Then ask for an explicit go / no-go, and for confirmation of the version number. **Do not proceed
to Step 6 without a clear yes.** If the developer edits the wording or the version, apply it and
re-present.

The developer may also edit `release.md` **directly in their editor** while reviewing — expect it.
Re-read the file before any further edit and keep their changes; never revert them.

## Step 6 — commit, tag, push (only after approval)

```bash
BRANCH=$(git rev-parse --abbrev-ref HEAD)
V=X.Y.Z                                          # approved version

git add apps/frontend/public/release.md
git commit -m "docs: release notes for v$V"

git tag -a "code/v$V"  -m "Release v$V"
git tag -a "chart/v$V" -m "Helm Charts Release $V"

git push origin "$BRANCH" "code/v$V" "chart/v$V"
```

Both tags land on the release-notes commit. Push the branch and the two tags **by name** —
**never `git push --tags`**: it pushes every local tag missing on the remote, and GitHub
**silently skips push events when more than three tags arrive in one push**, so neither release
workflow fires (this bit the v2.1.11 cut — ~17 stale local tags rode along and both workflows
stayed silent). It also litters the remote with stale local tags.

Tag-title convention (deliberate — do not "normalize"): the **code** tag reads `Release vX.Y.Z`
(with the `v`), the **chart** tag reads `Helm Charts Release X.Y.Z` (no `v`). Same version on both.

## Step 7 — confirm the release is building (mandatory)

Verify that **both tag-triggered runs actually started** — do not report success on the push
alone:

```bash
gh run list --limit 8
```

You must see two runs whose ref column shows the **tag names**:

- `code/vX.Y.Z` → `.github/workflows/Build-and-push-docker.yml` (images to
  `ghcr.io/thalesgroup/fred-agent/*`).
- `chart/vX.Y.Z` → `.github/workflows/Package-and-push-charts.yml` (chart to
  `oci://ghcr.io/thalesgroup/fred-helm/fred`).

Beware the decoy: the branch push also fires "Build and Push Docker Images" with ref `swift` —
that is **not** the release build. Tag runs can lag the push by ~30–60 s; re-check before
concluding they are missing.

**Recovery — tag workflows never fired.** Neither workflow has `workflow_dispatch`, so the only
re-trigger is to delete the two tags on the remote and re-push them (the local tag objects and
the commit are untouched — this only re-fires the push events):

```bash
git push origin :refs/tags/"code/v$V" :refs/tags/"chart/v$V"
git push origin "code/v$V"
git push origin "chart/v$V"
```

Then re-run `gh run list` and confirm both tag runs appear.

Do **not** touch `deploy/charts/fred/Chart.yaml` — the chart workflow injects `version`/`appVersion`
at build time; the value committed in the file is not used.
