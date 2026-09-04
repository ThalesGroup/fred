# Forking Fred — The Right Way

This guide is for teams that deploy Fred under their own branding or with organisation-specific content (legal notices, agents, release notes). It defines the one rule that keeps your fork permanently merge-compatible with the open source `develop` branch.

---

## The cardinal rule

> **A fork must not modify Fred's handwritten source code.** Fork-specific
> work belongs in a supported extension boundary: static content under
> `apps/frontend/public/contrib/<your-brand>/`, an independently built and
> deployed application, or an independent agent pod.

If this rule is followed, future upstream merges do not conflict on Fred's
handwritten code — and, since none of these boundaries lives inside the Fred
repository any more, there are no generated artifacts to regenerate after a
merge either.

If this rule is broken, every merge becomes a manual conflict resolution exercise. Over time the fork drifts, the team stops merging, and the fork becomes an unmaintained dead-end.

---

## The `contrib/` mechanism

Static content does not require a fork at all: the stock frontend image fetches
a **theme archive** (logos, icons, legal markdown, `contrib/<brand>/` files)
from your object storage at startup - see "Theme overlay" in
`apps/frontend/README.md`. Keep the files in a fork only when you want them
versioned next to your own code; the cascade below applies either way.

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

These files are committed in your fork's git repository, or shipped in the theme archive instead (see above). The open source repository never touches the `contrib/` directory. Your files are never in conflict.

Do not put anything fork-specific in the frontend `src/` tree. If you need a
product page, use the application boundary below. If that boundary is
insufficient and you still need to modify Fred-owned `.tsx`, `.ts`, `.scss`,
or translation `.json` files, stop — the host is missing an extension point.

---

## Your own applications

A team-scoped product page is **your** container image, built and released by
you, on your own cycle. Fred compiles none of it: there is no directory in this
repository to add, no manifest to author, no generator to run, and nothing
generated to commit. Shipping an application inside Fred's frontend image would
force a Fred rebuild for every change to your product, which is exactly the
coupling this guide exists to remove.

An application is up to two independently deployed services, and Fred exposes
each behind its own prefix:

| Prefix                    | Serves         | Who calls it              |
| ------------------------- | -------------- | ------------------------- |
| `/apps/<app_id>/`         | your UI image  | the browser, in the frame |
| `/app-services/<app_id>/` | your API image | your own UI code          |

Only the UI is mandatory. A UI-only application simply has no service.

### 1. Build the UI image

Serve a static bundle built with `/apps/<app_id>/` as its base path. Fred
forwards that whole prefix upstream, so the absolute asset URLs your bundler
bakes in resolve back through the same route. If your UI has client-side
routes, your own server owns their fallback — Fred's SPA fallback does not
apply inside your prefix.

Your UI is loaded in a frame and talks to the host over `postMessage`. It
announces the protocol version it speaks; Fred validates it and renders an
explicit error state on a mismatch rather than a broken screen. Do not reach
for anything outside that channel — no parent DOM, no globals, no shared
build. Those all happen to work today only because the frame is same-origin,
and the day the UI moves to its own origin they stop working. Treat the
handshake as the entire contract.

### 2. Build the service image, if you need one

Your API sits behind `/app-services/<app_id>/`. Fred strips that prefix and
proxies the rest, so the browser never learns your upstream address.

#### Your service is the only thing authorizing your data

The gateway authorizes **nothing**. Its `/app-services/` block asks two
questions — is this `app_id` registered, and does it have an upstream — and
then forwards the request with the caller's `Authorization` header untouched.
There is no `auth_request`, no entitlement lookup, no team check. Any
authenticated user in the realm reaches your service.

It cannot be otherwise: only your service knows what data it is about to
return and for whom. The gateway sees a path, not a result, so it cannot
authorize the response on your behalf.

So every request handler must answer both questions — is this caller a member
of the team, and was this application granted to that team. You do not have to
implement either: the Control Plane already answers both in one call, because
grants are **team → capability**, never user → capability. Use the *caller's*
token, not a service credential:

```js
// GET /control-plane/v1/teams/<teamId>/applications
//   403          -> caller is not a member of that team
//   200, absent  -> member, but the team was never granted this app
//   200, present -> genuinely entitled
const r = await fetch(
  `${CONTROL_PLANE}/control-plane/v1/teams/${teamId}/applications`,
  { headers: { authorization: req.headers.authorization } },
);

if (r.status === 403) return deny("not_a_team_member");
if (!r.ok) return deny("entitlement_check_unavailable"); // fail CLOSED
const { items = [] } = await r.json();
if (!items.some((a) => a.id === APP_ID)) return deny("app_not_granted_to_team");
```

Fail **closed** when the check itself fails. An unreachable Control Plane must
never mean "allowed".

#### Test it with a user who should not have access

This is a required step, not a nicety. Forgetting the check produces no error,
no warning and no log line: you are a member of a granted team, so every check
you naturally perform passes, and the application looks correct from the only
viewpoint you occupy. The gap is visible only from outside.

Before you ship, create a second user who is **not** in the granted team, get a
token for them, and call your service directly:

```
GET /app-services/<app_id>/teams/<granted-team-id>/...   as the outside user
expected: 403        actual 200 means your data is readable by the whole realm
```

Repeat for a user who *is* in a team but whose team was never granted the app —
that one must be refused too, and it is the case most often missed.

### 3. Register both in deployment configuration

Registration is Helm values, not source. Two blocks, one `app_id`:

```yaml
applications:
  control-plane-backend:
    configuration:
      platform:
        frontend:
          feature_flags:
            enableApplications: true
        application_sources:
          - app_id: acme-forecast
            ui_prefix: /apps/acme-forecast
            version: 1.0.0
            icon: insights
            display_name:
              en: "Forecast"
            description:
              en: "Demand forecasting for the selected team."
            enabled: true
  frontend:
    env:
      - name: FRONTEND_APPLICATIONS_JSON
        value: |
          [
            {
              "app_id": "acme-forecast",
              "ui_upstream": "http://acme-forecast-ui.acme-apps.svc.cluster.local:80",
              "service_upstream": "http://acme-forecast-api.acme-apps.svc.cluster.local:8000",
              "service_required": true
            }
          ]
```

**On Kubernetes, both upstreams must be fully qualified.** A bare Service name
resolves for most workloads because the pod's `search` list completes it, but
the gateway proxies applications through a *variable* `proxy_pass`, which makes
nginx resolve the host at request time through its own `resolver` — and that
path does not apply the search list. A short name yields
`could not be resolved (3: Host not found)` and a 502, while the same name
works from a shell in the very same pod. Write
`<service>.<namespace>.svc.cluster.local`.

The control-plane entry owns what the browser and the catalog see; the frontend
entry owns the server-side addresses nginx proxies to. `app_id` is the only
value you write twice, and the two must agree — nothing checks it for you, so
see "What the registration refuses" below for what each mismatch looks like.

`ui_prefix` is deliberately configuration rather than a convention: pointing it
at an absolute `https://` URL is all that has to change the day you move the UI
to its own origin. Until then it must be exactly `/apps/<app_id>`, and the
control plane rejects anything else, because nginx routes on that path segment
and any other own-origin value would simply 404.

The default `path: /` Ingress rule already carries both prefixes to the
frontend, so registering an application needs no new Ingress path. Add one only
if you want the UI to bypass the frontend hop — see the worked example in
`deploy/charts/fred/values.yaml`.

### Put your application in its own namespace

Deploy your workloads beside Fred, not inside it. Fred's only coupling to an
application is the upstream URL, and Service DNS is namespace-addressable, so
moving an application out of Fred's namespace changes exactly one string:

```
http://acme-forecast-ui.fred.svc.cluster.local:80
                        ↓
http://acme-forecast-ui.acme-apps.svc.cluster.local:80
```

No chart change, no Fred rebuild, no Ingress edit, no RBAC. Because the
fully-qualified form is required anyway (above), the same-namespace and
cross-namespace cases are written identically — there is no migration cost to
starting this way.

Your team then owns its own RBAC, quotas, limits and release cadence, and
cannot disturb Fred's workloads; Fred's namespace stays the stock chart.

One addition the split needs on a hardened cluster: if the cluster default-denies
cross-namespace traffic, allow Fred's frontend to reach your Services on the UI
and service ports. A cluster with no NetworkPolicy needs nothing.

`enableApplications` defaults to `false`, and the Fred Helm chart derives the
frontend gateway's `FRONTEND_ENABLE_APPLICATIONS` from that one control-plane
value; do not add a second chart setting for the frontend container. With the
switch off, both prefixes return 404 and the Apps surface does not mount.

Registration still grants nothing. A platform administrator enables
`app__<app_id>` for each collaborative team on the Capabilities page. Personal
spaces are outside V1.

### What the registration refuses

- An unknown `app_id` returns 404 in both namespaces.
- A registered application with no `service_upstream` returns 503 under
  `/app-services/` — it is unavailable, not unknown.
- `service_required: true` with no `service_upstream` fails container startup.
  A permanent 503 is a deployment mistake, so it is caught at boot.
- An upstream URL must be an origin and nothing more —
  `http(s)://host[:port]`. The gateway forwards the client path to a
  `proxy_pass` that carries no URI part, so a base path would replace the
  request path instead of prefixing it. Credentials, query strings, any path,
  and non-`http(s)` schemes are all rejected at startup.
- An `app_id` must match `^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$` with nothing after
  it, not even a newline, and may not be `default`, `hostnames`, `include`, or
  `volatile`: the gateway emits ids as nginx `map` keys, and those four are
  read as directives instead. Rejected at startup.
- An own-origin `ui_prefix` that is not exactly `/apps/<app_id>` is rejected
  when the control plane loads its configuration.

### What it does not refuse

The two halves are validated independently, so a mismatched `app_id` starts
cleanly and fails later:

- **In the control plane only** — the application appears on the team's Apps
  page, and opening it shows "The application did not respond" after about
  fifteen seconds. That is the same message a genuinely cold service produces,
  so check the gateway registration before debugging your pod.
- **In the gateway only** — both prefixes proxy to your images for an
  application no team was ever granted, because the gateway performs no
  authorization. Keep the gateway list a subset of the control-plane list.
- **`enabled: false`** withdraws the application from the catalog and the UI
  but leaves its gateway routes serving. Remove both halves to retire one.

### Applications are trusted code, and the frame is not a sandbox

Be clear-eyed about the boundary. Today the application frame is **same-origin**
with Fred. A same-origin iframe is a rendering and lifecycle boundary, not a
security boundary: same-origin frames can reach each other's DOM and storage,
so an application UI is not contained by being framed. The `postMessage`
handshake is a _contract_ that keeps the later move to a separate origin cheap;
it is not, on its own, isolation.

So: applications are **trusted code your own fork builds and deploys**, on the
same footing as your agent pods. They are not a sandbox for third-party or
untrusted code, and this boundary must not be offered to anyone you would not
give commit rights to. Two consequences worth stating plainly:

- Your application image must not set `X-Frame-Options: DENY` or a
  `frame-ancestors` policy that excludes Fred's origin, or the frame will not
  render.
- Real isolation requires serving the UI from a separate origin. The
  configuration is already shaped for it — change `ui_prefix` to that origin's
  URL — but until you do, do not treat the frame as a containment mechanism.

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
# Your contrib/ files are untouched, and your applications and agent pods
# are not in this repository at all.
# Review, test, and promote to your production branch as usual.
```

If you encounter a conflict on a handwritten source file, treat it as a bug —
either in your fork (an override that should not exist) or in Fred (a missing
extension point). Application code cannot cause a merge conflict, because none
of it lives here; what can change under you is the frame protocol version, and
a mismatch shows as an explicit error state rather than a broken page.

---

## Checklist before your first clean merge

- [ ] Brand assets travel in a theme archive (`FRONTEND_THEME_URL`) rather than in the fork, unless you need them versioned with your code
- [ ] `apps/frontend/public/config.json` has `"releaseBrand": "<your-brand>"`
- [ ] Legal content is in `apps/frontend/public/contrib/<your-brand>/gcu.md` (and language variants), or in the theme archive
- [ ] Privacy notice is in `apps/frontend/public/contrib/<your-brand>/gdpr.md`, or in the theme archive
- [ ] Brand release notes (if any) are in `apps/frontend/public/contrib/<your-brand>/release.md`, or in the theme archive
- [ ] No `.tsx`, `.ts`, `.scss`, or `.json` file from `src/` exists in your fork's overlay
- [ ] Product UI code, if any, is its own container image serving under `/apps/<app_id>/`, with no file added to this repository
- [ ] Each application is registered in both `platform.application_sources` and `FRONTEND_APPLICATIONS_JSON` under the same `app_id`
- [ ] Agent code (Meridian only) is isolated under `contrib/<your-brand>/` and registered via Helm, not via source patches
- [ ] `git merge develop` has no handwritten-source conflicts
