# Forking Fred — The Right Way

This guide is for teams that deploy Fred under their own branding or with organisation-specific content (legal notices, agents, release notes). It defines the one rule that keeps your fork permanently merge-compatible with the open source `develop` branch.

---

## The cardinal rule

> **A fork must never modify a source code file.**
> Only files under `frontend/public/contrib/<your-brand>/` may be fork-specific.

If this rule is followed, every future `git merge develop` from the open source repository is conflict-free on all code files — forever. Conflicts become structurally impossible.

If this rule is broken, every merge becomes a manual conflict resolution exercise. Over time the fork drifts, the team stops merging, and the fork becomes an unmaintained dead-end.

---

## The `contrib/` mechanism

Fred's frontend resolves content files through a brand-aware cascade. Set your brand name once in `frontend/public/config.json`:

```json
{
  "frontend_basename": "/",
  "releaseBrand": "acme"
}
```

From that point on, every content-aware page tries your brand files first and falls back to the open source defaults:

### Legal pages (substitutive — your file replaces the default)

| Priority | Path tried | Wins when |
|---|---|---|
| 1 | `contrib/acme/gcu.fr.md` | User language is French |
| 2 | `contrib/acme/gcu.md` | Any language, brand fallback |
| 3 | `gcu.fr.md` | No brand file, French |
| 4 | `gcu.md` | Final fallback |

Same cascade applies to `gdpr.*.md`.

### Release notes (additive — your file is shown alongside the base)

| File | Shown as |
|---|---|
| `/release.md` | "Base Fred Release" tab |
| `contrib/acme/release.md` | "acme release" tab |

Both tabs are displayed simultaneously. This is intentional: your release notes document your brand-specific additions; the base notes document the open source changes underneath.

---

## What belongs in `contrib/<your-brand>/`

```
frontend/public/contrib/acme/
├── gcu.md              # Terms of use — English
├── gcu.fr.md           # Terms of use — French
├── gdpr.md             # Privacy notice — English
├── gdpr.fr.md          # Privacy notice — French
└── release.md          # Brand-specific release notes
```

These files are committed in your fork's git repository. The open source repository never touches the `contrib/` directory. Your files are never in conflict.

Do not put anything else in your fork's `src/` tree. If you find yourself needing to modify a `.tsx`, `.ts`, `.scss`, or translation `.json` file, stop — this is a signal that the open source codebase is missing a configuration or extension point. Open an issue or a pull request upstream instead.

---

## Meridian (1.5.x) — current intermediate state

In the current Meridian release line, some teams have placed organisation-specific agent code directly inside the fork's `agentic-backend/` source tree. This was unavoidable at the time: Fred did not yet ship a clean agent extension mechanism that could be activated purely through configuration.

This is a known limitation of Meridian, not an intended pattern. It creates the same merge problem described above: every upstream merge requires manual resolution of conflicts in agent code files.

If your fork is in this situation, the pragmatic mitigation is:

1. Keep your agent code isolated in a clearly named subdirectory, e.g. `agentic-backend/agentic_backend/agents/contrib/<your-brand>/`.
2. Register agents via Helm values (`agents_catalog.yaml`) rather than by patching any shared Python module.
3. Plan to migrate to the Constellation model as soon as it is available (see below).

---

## Constellation (2.x) — the target architecture

The upcoming Constellation release (tracked under the `agentic-pod` branch, milestone already tagged in the repository) resolves the agent problem at the architecture level.

In Constellation:

- **Agents** are delivered as independent, installable packages — separate repositories, separate release cycles, separate images.
- **Document processors** follow the same model.
- The core Fred platform becomes a clean runtime that discovers and loads agents through a well-defined plugin contract.

For fork operators this means:

- Your organisation-specific agents live in their own repository, completely outside the Fred source tree.
- The Fred core repository becomes a pure dependency — you consume it, you never patch it.
- Merging upstream Fred updates requires zero conflict resolution, on any file, forever.

**The `contrib/` pattern described in this guide is designed to be forward-compatible with Constellation.** Brand-specific static content (legal notices, release notes) will continue to live under `frontend/public/contrib/<your-brand>/` in Constellation. No migration of that content will be required.

---

## Merge workflow for fork maintainers

Once your fork follows the rules above, the full synchronisation workflow is:

```bash
# On your fork's integration branch
git merge develop

# Expected result: no conflicts on any source file.
# Your contrib/ files are untouched.
# Review, test, and promote to your production branch as usual.
```

If you encounter a conflict on a source file, treat it as a bug — either in your fork (a code override that should not exist) or in the open source codebase (a missing extension point). Do not resolve it silently; fix the root cause.

---

## Checklist before your first clean merge

- [ ] `frontend/public/config.json` has `"releaseBrand": "<your-brand>"`
- [ ] Legal content is in `frontend/public/contrib/<your-brand>/gcu.md` (and language variants)
- [ ] Privacy notice is in `frontend/public/contrib/<your-brand>/gdpr.md`
- [ ] Brand release notes (if any) are in `frontend/public/contrib/<your-brand>/release.md`
- [ ] No `.tsx`, `.ts`, `.scss`, or `.json` file from `src/` exists in your fork's overlay
- [ ] Agent code (Meridian only) is isolated under `contrib/<your-brand>/` and registered via Helm, not via source patches
- [ ] `git merge develop` runs with zero conflicts
