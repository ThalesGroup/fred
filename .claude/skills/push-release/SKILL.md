---
name: push-release
description: Cut a Fred release on the current release branch — prepare user-facing notes and the operator migration guide, enforce the operational version minimum, then (after developer sign-off) tag code/vX.Y.Z + chart/vX.Y.Z and push. Stops for approval before any tag is placed.
---

# Push Release Skill

Cut a release on the **current release branch** (`swift`). A Fred release is
**two annotated Git tags on the same commit** — `code/vX.Y.Z` and `chart/vX.Y.Z` — each
driving its own CI workflow. This skill prepares the release notes, presents them, and
**waits for explicit developer approval before placing or pushing any tag.**

Ground truth for the mechanics: `docs/swift/RELEASE-STRATEGY.md`. Read it if anything below
is ambiguous.

## Guided interaction (Codex and Claude Code)

The integrator may simply ask: "Use $push-release to prepare the next release."
Run the tools yourself; do not hand them Python commands to execute. Use the root
Make targets below for preparation. Ask only for missing choices or unresolved
operational facts after inspecting the checkout and notes; reuse answers already
given. Propose the minimum eligible version instead of asking the integrator to
calculate it. Do not guess missing migration procedures to clear a coverage check.

Prepare one reviewable result before the final approval: the proposed version,
user-facing notes and the complete consolidated DevOps guide. Explain required
upgrade actions separately from optional activation and user re-ingestion. For an
all-none release, explicitly say that normal deployment needs no additional action.
Reconcile duplicate or conflicting instructions in source notes and regenerate;
do not hand-edit the generated guide or claim automatic generation resolves these
interactions. Step 5 remains the explicit approval gate before tags or publication.

## Hard rules

- **Never tag or push without explicit approval.** Step 5 is a mandatory stop. Presenting the
  updated `release.md` and getting a clear go-ahead is the whole point of this skill.
- **The two tags are a pair on one commit.** `code/vX.Y.Z` builds and pushes the Docker images;
  `chart/vX.Y.Z` packages and pushes the Helm chart. A bare `vX.Y.Z` (no prefix) publishes
  **nothing** — never tag that way.
- **UI notes are user-facing.** Write for someone using Fred, not building it. No `ports`,
  `adapters`, `vectors`, `map-reduce`, `SSE`, class names, or file paths in the summary/bullets.
  Describe what the user can now *do* or what stopped breaking. Match the voice of the existing
  entries in `apps/frontend/public/release.md`.
- **Notes are committed, then tagged.** The tag must point at a commit that already contains the
  new `release.md` entry, source migration notes and generated operator guide. Order: edit → commit → tag both → push.
- Tags are **annotated** (`git tag -a`), created on `HEAD` of the release branch. No promotion to
  `main` — tags live on the branch they were cut from.

## Step 1 — establish the branch and the last release

```bash
git symbolic-ref --short HEAD                  # must be attached to the intended release branch
git status --short                            # inspect before installation, fetch or edits
```

Stop on detached HEAD, an unintended topic branch or unrelated working-tree edits
(including untracked migration/release documents). Select the intended release
branch only after preserving those edits; never create release tags from a topic
checkout. Reuse explicit branch selection already given by the developer.

Once the checkout is suitable:

```bash
git fetch origin --tags
make release-plan                            # ancestry-based baseline and impact
```

Read `docs/swift/ops/MIGRATION-GUIDES.md`. Use the helper's reported baseline;
never choose a repository-wide maximum tag. If coverage is blocked, inspect the
reported range and add accurate migration declarations before proceeding. A legacy
audit must describe the reviewed changes; do not invent an acknowledgement just
to clear the check. No-op declarations remain necessary for internal changes even
when those changes are omitted from UI notes.

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

**One release window, one entry per subject (mandatory).** Work on the same subject inside a
single release window — the feature commit plus every fix, follow-up and polish commit that
landed on it before the tag — is written as **one bullet describing the shipped behaviour**. Do
not list the intermediate bug fixes: users never saw the broken intermediate state, so a "fixed
X" bullet for a defect that only ever existed between two of our own commits describes a
regression they never lived through. The same holds for a feature released earlier whose
follow-ups land now: those *are* real fixes and stay in **Bug Fixes**, because users did see the
broken behaviour.

Test: would a user upgrading from the previous tag ever have hit this bug? Yes → **Bug Fixes**.
No, it only existed mid-window → fold it into the feature's own bullet and say nothing about it.

Skip purely internal commits from the notes (Docker build fixes, lockfile relocks, code-quality
passes, schema regen) — they ship, but they are not release-note material. When in doubt about
whether a change is user-visible, keep it out of the summary and ask.

## Step 3 — decide the version

Use the migration helper's maximum impact and minimum version: none -> patch,
minor -> minor, major -> major. Optional feature activation requiring operations
counts as minor even when default-off upgrades need none. Validate a requested
version through `plan --version X.Y.Z`; do not accept a version below the minimum.
A deliberately larger version must be explicit at sign-off. For release candidates,
compare to the preceding stable tag and preserve the eligible core on promotion.

## Step 4 — write the release notes

Prepend a new entry to the top of **`apps/frontend/public/release.md`** (the only canonical
copy — `frontend/dist/release.md` is a build artifact, never edit it). Use today's date from the
session context. Follow the exact shape of the existing entries:

```markdown
**vX.Y.Z** — YYYY-MM-DD

- **Summary**

  <2–3 sentences, ~60 words max. User-focused, lead with what the user can now do.>

- **Features**

  - <one capability per bullet, phrased as user benefit, with (#issue) refs at the end>

- **Bug Fixes**

  - <what used to go wrong, from the user's seat, with (#issue) refs>
```

Writing guidance, distilled from the existing notes:

- **Keep it short.** One line per bullet, one benefit. Trim caveats and mechanism — the developer
  has said the notes must stay concise. If a bullet needs a second clause to breathe, it's too long.
- **The Summary is the shortest part of the entry, not a digest of it.** Two or three sentences,
  ~60 words. Name the two or three things that matter and stop — the bullets carry the detail, so
  a Summary that walks every section is redundant by construction. Do not restate a bullet's
  mechanism, figures or caveats there; the developer will ask for it shorter, every time.
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

### Prepare the operator guide

Add a new migration note for the release-preparation contribution itself (normally
none with its rationale). Reconcile ordering and conflicting operations across all
in-range notes. If necessary set `after` dependencies or add a correction note;
never rewrite a note already published in an earlier release. Do not request private
customer values. Fred chart values are the production reference; configuration_prod.yaml
is local Docker Compose only.

```bash
make release-guide RELEASE_VERSION=X.Y.Z
```

Review `docs/swift/ops/releases/vX.Y.Z/migration.md` and the source notes. Keep
operator steps out of the UI document; fix sources and regenerate if the guide
needs changes. Resolve all coverage blockers before requesting tag approval.

## Step 5 — present and STOP for approval (mandatory)

Show the developer the **full new entry** verbatim, plus:

- the branch, the ancestry-based baseline, maximum migration impact and proposed version,
- the generated operator guide, its ordered procedures and remaining deployment limitations,
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

uv run --project libs/fred-pod --locked --no-dev python scripts/migration_guides.py verify --worktree --version "$V"
git add apps/frontend/public/release.md "docs/swift/ops/releases/v$V/migration.md"
# Stage only the new/updated source notes reviewed above, by explicit path.
git add docs/swift/ops/migrations/<reviewed-note>.md
git commit -m "docs: release notes for v$V"

uv run --project libs/fred-pod --locked --no-dev python scripts/migration_guides.py verify --version "$V"

git tag -a "code/v$V"  -m "Release v$V"
git tag -a "chart/v$V" -m "Helm Charts Release $V"

uv run --project libs/fred-pod --locked --no-dev python scripts/migration_guides.py verify --version "$V" --require-tags
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

Do **not** touch `deploy/charts/fred/Chart.yaml` — the chart workflow injects `version`/`appVersion`
at build time; the value committed in the file is not used.

Wait for both full tag-triggered publication workflows to finish successfully,
including migration validation, before reporting publication complete. Verify
each GitHub release contains migration.md. A missing/stale
guide, insufficient version or missing paired tag blocks artifact publication.
