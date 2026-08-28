# Forking Fred — The Right Way

This guide is for teams that deploy Fred under their own branding or with organisation-specific content (legal notices, agents, release notes). It defines the one rule that keeps your fork permanently merge-compatible with the open source `develop` branch.

---

## The cardinal rule

> **A fork must not modify Fred's handwritten source code.** Fork-specific
> work belongs in a supported extension boundary: static content under
> `apps/frontend/public/contrib/<your-brand>/`, a bundled application under
> `apps/applications/<application-id>/`, or an independent agent pod.

If this rule is followed, future upstream merges do not conflict on Fred's
handwritten code. Tracked frontend application artifacts may need to be
regenerated after a merge; they are derived artifacts, not a place for manual
conflict resolution. The Control Plane application catalog is untracked and is
generated automatically by its build, test, and packaging paths.

If this rule is broken, every merge becomes a manual conflict resolution exercise. Over time the fork drifts, the team stops merging, and the fork becomes an unmaintained dead-end.

---

## The `contrib/` mechanism

Fred's frontend resolves content files through a brand-aware cascade. Set your brand name once in `apps/frontend/public/config.json`:

```json
{
  "frontend_basename": "/",
  "releaseBrand": "acme"
}
```

From that point on, every content-aware page tries your brand files first and falls back to the open source defaults:

### Legal pages (substitutive — your file replaces the default)

| Priority | Path tried               | Wins when                    |
| -------- | ------------------------ | ---------------------------- |
| 1        | `contrib/acme/gcu.fr.md` | User language is French      |
| 2        | `contrib/acme/gcu.md`    | Any language, brand fallback |
| 3        | `gcu.fr.md`              | No brand file, French        |
| 4        | `gcu.md`                 | Final fallback               |

Same cascade applies to `gdpr.*.md`.

### Release notes (additive — your file is shown alongside the base)

| File                      | Shown as                |
| ------------------------- | ----------------------- |
| `/release.md`             | "Base Fred Release" tab |
| `contrib/acme/release.md` | "acme release" tab      |

Both tabs are displayed simultaneously. This is intentional: your release notes document your brand-specific additions; the base notes document the open source changes underneath.

---

## What belongs in `contrib/<your-brand>/`

```
apps/frontend/public/contrib/acme/
├── gcu.md              # Terms of use — English
├── gcu.fr.md           # Terms of use — French
├── gdpr.md             # Privacy notice — English
├── gdpr.fr.md          # Privacy notice — French
└── release.md          # Brand-specific release notes
```

These files are committed in your fork's git repository. The open source repository never touches the `contrib/` directory. Your files are never in conflict.

Do not put anything fork-specific in the frontend `src/` tree. If you need a
product page, use the bundled application boundary below. If that boundary is
insufficient and you still need to modify Fred-owned `.tsx`, `.ts`, `.scss`,
or translation `.json` files, stop — the host is missing an extension point.

---

## Bundled product applications

A trusted, team-scoped product page is installed as one isolated directory:

```text
apps/applications/<application-id>/
├── fred-app.json
├── frontend/
│   ├── index.tsx
│   └── Application.module.css
└── backend/
    └── README.md
```

The manifest supplies the stable id, semantic version, localized name and
description, supported icon, host API version, module key, and whether the app
needs a same-origin backend service. It contains no upstream URL, token,
credential, raw HTML, or executable module location.

The `frontend/` module is compiled into Fred's frontend image. It imports React,
its own local files, and
`@fred/application-host` only. Fred supplies the selected collaborative team,
relative navigation, locale, authorized application summary, and a constrained
authenticated request function. The app does not import Fred's private store,
Keycloak object, generated shared clients, or `src/` components.

The `backend/` directory is reserved for an optional, independently built
application service. A service-free application keeps `service_required` set to
`false` and needs no backend runtime or upstream mapping. The included
`apps/applications/example/` package demonstrates that service-free shape; its
backend directory contains documentation only.

After adding or changing a manifest, run:

```bash
cd apps/frontend
make generate-applications
make check-applications
```

Generation refreshes the tracked statically allowlisted frontend registry,
translations, and runtime service contract. It also materializes the local
Control Plane catalog from the same manifest set. Commit the tracked frontend
outputs, but never hand-edit or commit the ignored Control Plane catalog. The
Control Plane recreates its catalog automatically before builds, tests,
packaging, and image creation. The deployment must set
`applications.control-plane-backend.configuration.platform.frontend.feature_flags.enableApplications`
to `true` before the Apps surface is available. The Fred Helm chart treats that
control-plane value as the single authoritative setting and derives the
frontend gateway's `FRONTEND_ENABLE_APPLICATIONS` value from it; do not add a
second chart setting for the frontend container. A platform administrator then
enables `app__<application-id>` for collaborative teams through the Capabilities
page. Personal spaces are outside V1.

For a service-backed application, deployment supplies the application-id to
upstream mapping through the documented frontend environment setting. The
browser sees only `/app-services/<application-id>/teams/<team-id>/...`; the service
must independently validate the bearer, team membership, active installation,
and application entitlement. A bundled application still ships with Fred's
frontend image, so changing it rebuilds that image; independently deployed UI
modules are not yet a supported extension boundary.

---

## Meridian (1.5.x) — legacy intermediate state

In the Meridian release line, some teams placed organisation-specific agent code directly inside the fork's `agentic-backend/` source tree. This was unavoidable at the time: Fred did not yet ship a clean agent extension mechanism.

This was a known limitation, not an intended pattern.

---

## Current architecture (2.x) — independent agent pods

Fred now ships the clean agent extension mechanism that Meridian lacked. **You no longer put agent code inside the Fred source tree at all.**

Instead:

- **Build your agents as an independent pod** using `fred-sdk` + `fred-runtime`. See [fred-samples](https://github.com/ThalesGroup/fred-samples) for a reference implementation.
- Your pod lives in its own repository, has its own release cycle and image, and registers itself with the control plane.
- The Fred core repository becomes a pure dependency — you consume it, you never patch it.
- Merging upstream Fred updates requires zero conflict resolution on any source file.

If your fork still has agent code inside `agentic-backend/`, the migration path is:

1. Extract the agent code into its own repository as a `fred-runtime`-based pod.
2. Register the pod with the control plane (see `apps/fred-agents/` for the wiring pattern).
3. Remove the agent code from your Fred fork.

**The `contrib/` pattern described in this guide remains valid for frontend static content** (legal notices, release notes). Brand-specific static assets continue to live under `apps/frontend/public/contrib/<your-brand>/` with no conflict risk.

---

## Merge workflow for fork maintainers

Once your fork follows the rules above, the synchronisation workflow is:

```bash
# On your fork's integration branch
git merge develop

# Expected result: no conflicts on Fred-owned handwritten source.
# Your contrib/ and uniquely named application directories are untouched.
# If tracked frontend application artifacts changed upstream, regenerate them.
# Review, test, and promote to your production branch as usual.
```

If you encounter a conflict on a handwritten source file, treat it as a bug —
either in your fork (an override that should not exist) or in Fred (a missing
extension point). A conflict in a tracked frontend application artifact is
resolved by keeping the manifests/modules and rerunning
`make generate-applications`, never by editing the generated output. The
ignored Control Plane catalog cannot create a merge conflict.

---

## Checklist before your first clean merge

- [ ] `apps/frontend/public/config.json` has `"releaseBrand": "<your-brand>"`
- [ ] Legal content is in `apps/frontend/public/contrib/<your-brand>/gcu.md` (and language variants)
- [ ] Privacy notice is in `apps/frontend/public/contrib/<your-brand>/gdpr.md`
- [ ] Brand release notes (if any) are in `apps/frontend/public/contrib/<your-brand>/release.md`
- [ ] No `.tsx`, `.ts`, `.scss`, or `.json` file from `src/` exists in your fork's overlay
- [ ] Product UI code, if any, is isolated under `apps/applications/<application-id>/frontend/` and passes `make check-applications`
- [ ] Agent code (Meridian only) is isolated under `contrib/<your-brand>/` and registered via Helm, not via source patches
- [ ] `git merge develop` has no handwritten-source conflicts; tracked frontend application artifacts are regenerated when needed and the Control Plane catalog remains untracked
