# Building and deploying a Fred application

A step-by-step walkthrough using this sample as the worked example. Every
command here was run against a live k3d cluster, and every entry in
[Troubleshooting](#troubleshooting) is a failure that actually happened during
that run — not a list of things that might go wrong.

Use it two ways: to deploy this sample, or as the template for your own
application by substituting your `app_id` throughout.

---

## What you are building

Two container images that Fred does not build, plus one optional Python package:

| Piece | What it is | Where Fred meets it |
| --- | --- | --- |
| UI image | static bundle in any web server | `/apps/<app_id>/`, rendered in a frame |
| API image | any HTTP service, any language | `/app-services/<app_id>/` |
| Capability | Python package in the agents pod | gives agents tools to touch your data |

The capability is only needed if agents must read or advance your data. A
UI-only application needs neither it nor the API.

---

## Prerequisites

- A running Fred deployment with `enableApplications: true`
- Platform-admin access, to grant the application to a team
- Somewhere the cluster can pull images from — a registry, or `k3d image import`
  for local work

---

## Step 1 — Write the UI

A static page. Two things about it are not style choices; both cost real
debugging time when missed.

**Serve the bare prefix.** The iframe `src` is `/apps/<app_id>` with **no
trailing slash**, because the control plane normalises it that way. A server
that only handles the directory form will redirect, and see the next point.

**Turn off absolute redirects.** Fred forwards `Location` verbatim. An absolute
redirect carries *your container's* hostname, which the browser cannot resolve.

**Send `Cache-Control: no-store` for the entry point.** Otherwise the browser
keeps serving the previous build from cache, and a deployment that is correct on
the server still shows the old page — including the old bug you just fixed.

`ui/Dockerfile`:

```dockerfile
FROM nginx:1.27-alpine
RUN mkdir -p /usr/share/nginx/html/apps/progress-tracker
COPY index.html /usr/share/nginx/html/apps/progress-tracker/index.html
RUN printf '%s\n' \
  'server {' \
  '  listen 80;' \
  '  root /usr/share/nginx/html;' \
  '  absolute_redirect off;' \
  '  location = /apps/progress-tracker { add_header Cache-Control "no-store"; try_files /apps/progress-tracker/index.html =404; }' \
  '  location /apps/progress-tracker/ {' \
  '    add_header Cache-Control "no-store";' \
  '    try_files $uri $uri/ /apps/progress-tracker/index.html;' \
  '  }' \
  '  location = /healthz { return 200 "ok"; add_header content-type text/plain; }' \
  '}' > /etc/nginx/conf.d/default.conf
```

Build your bundle with `/apps/<app_id>/` as its base path — Fred forwards the
whole prefix upstream, so the absolute asset URLs your bundler bakes in resolve
back through the same route.

---

## Step 2 — Speak the frame protocol

Your page holds no token and names no upstream. It announces itself, receives
context, and asks the host for everything else.

```js
const PROTOCOL_VERSION = "1";

// Announce LAST, after the listener is installed: the host replies with
// fred:context, which is what starts your first load.
parent.postMessage({ type: "fred:ready", protocolVersion: PROTOCOL_VERSION }, "*");

window.addEventListener("message", (event) => {
  const m = event.data;
  if (!m || typeof m !== "object") return;
  if (m.type === "fred:context") {
    const { team, locale } = m.context;   // who is looking at this
    load();
  }
});
```

To reach your own API, ask the host. **The host already prefixes
`/app-services/<app_id>/teams/<team_id>`**, so send only the path below that
root — never repeat the team segment:

```js
// correct
hostFetch("tasks");
// wrong -> /teams/<id>/teams/<id>/tasks -> 404
hostFetch(`teams/${teamId}/tasks`);
```

```js
function hostFetch(path, init = {}) {
  const requestId = `r${++seq}`;          // fresh id per request, never reused
  parent.postMessage({
    type: "fred:request", requestId, path,
    method: init.method || "GET",
    headers: init.body ? { "content-type": "application/json" } : {},
    body: init.body || null,
  }, "*");
  // resolve when fred:response arrives with this requestId
}
```

Never reach outside this channel — no parent DOM, no globals, no shared build.
They work only while the frame is same-origin, and stop the day it is not.

There is **no push channel**. Progress made elsewhere reaches your screen by
polling.

---

## Step 3 — Write the API

Fred strips `/app-services/<app_id>` before proxying, so your service sees
`/teams/<team_id>/...`.

**The gateway authorizes nothing.** It checks only that the `app_id` is
registered and has an upstream, then forwards the caller's `Authorization`
header untouched. Any authenticated user in the realm reaches you. Your service
is the only thing standing between them and your data.

Ask the Control Plane the question it already answers — one call covers both
membership and grant, because grants are team to capability:

```python
async def require_entitled(team_id: str, authorization: str | None = Header(None)) -> str:
    if not authorization:
        raise HTTPException(401, "missing_bearer")
    url = f"{CONTROL_PLANE}/control-plane/v1/teams/{team_id}/applications"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, headers={"authorization": authorization})
    except httpx.HTTPError:
        raise HTTPException(403, "entitlement_check_unavailable")   # fail CLOSED
    if r.status_code == 403:
        raise HTTPException(403, "not_a_team_member")
    if r.status_code != 200:
        raise HTTPException(403, "entitlement_check_failed")
    if not any(i.get("id") == APP_ID for i in r.json().get("items", [])):
        raise HTTPException(403, "app_not_granted_to_team")
    return team_id
```

Use the **caller's** token, not a service credential, and fail closed when the
check itself fails.

`api/Dockerfile` — note the numeric user:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py ./
# Numeric, not a name: a cluster enforcing runAsNonRoot cannot verify a named
# user and refuses to start the container.
RUN useradd --uid 10001 --create-home appuser
USER 10001
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## Step 4 — Build the images

```bash
docker build -t progress-tracker-ui:sample  samples/apps/progress-tracker/ui
docker build -t progress-tracker-api:sample samples/apps/progress-tracker/api
```

## Step 5 — Get them where the cluster can pull

Local k3d — the cluster runs its own containerd and cannot see your Docker
daemon's images:

```bash
k3d image import progress-tracker-ui:sample progress-tracker-api:sample -c fred
```

Anywhere else, push to a registry the nodes can reach. **Image imports do not
survive cluster recreation** — re-import after any `k3d cluster delete`.

## Step 6 — Deploy the workloads

Its own namespace. Fred reaches your services only by DNS name, so they can live
anywhere.

```bash
kubectl apply -f samples/apps/progress-tracker/deploy.yaml
```

Secrets are namespace-scoped, so create yours where the workload runs — and keep
the value out of the repo:

```bash
kubectl create secret generic progress-tracker-opensearch -n sample-apps \
  --from-literal=username=admin \
  --from-literal=password='<the password>'
```

The manifest also expects the shared key the capability authenticates with. One
value, two namespaces: the API reads it, and the agents pod presents it.

```bash
KEY=$(openssl rand -hex 32)
kubectl create secret generic progress-tracker-service -n sample-apps --from-literal=key="$KEY"
kubectl create secret generic progress-tracker-service -n fred        --from-literal=key="$KEY"
```

### The agent half — installing the capability

Only needed if agents must read or write your records. Installing the package
*is* the registration: the pod discovers it at boot through the
`fred.capabilities` entry point, so nothing here edits Fred's own Dockerfile or
its dependency list. An overlay image keeps your capability out of Fred's build:

```dockerfile
ARG BASE_IMAGE=ghcr.io/thalesgroup/fred-agent/fred-agents:0.2
FROM ${BASE_IMAGE}
USER root
COPY . /tmp/capability
RUN /app/venv/bin/pip install --no-cache-dir /tmp/capability && rm -rf /tmp/capability
USER 1000
```

Build it on whatever agents image you actually run, then point the deployment at
it:

```bash
docker build --build-arg BASE_IMAGE=<your agents image> \
  -t fred-agents-with-tracker:sample samples/apps/progress-tracker/capability
k3d image import fred-agents-with-tracker:sample -c fred
kubectl set image deployment/fred-agents -n fred <container>=fred-agents-with-tracker:sample
```

Verify by **importing it**, not by listing entry points — a broken install still
advertises its entry point while the import raises `ModuleNotFoundError`:

```bash
kubectl exec -n fred deploy/fred-agents -- /app/venv/bin/python \
  -c "import fred_capability_progress_tracker.capability as m; print(m.ProgressTrackerCapability)"
```

The capability still needs its own two settings. Without the API address it
contributes no tools at all, quietly; without the key every call it makes is
refused. `--prefix` with `--keys` turns the secret's `key` entry into
`PROGRESS_TRACKER_SERVICE_KEY`.

```bash
kubectl set env deployment/fred-agents -n fred \
  PROGRESS_TRACKER_API_BASE=http://progress-tracker-api.sample-apps.svc.cluster.local:8000
kubectl set env deployment/fred-agents -n fred \
  --from=secret/progress-tracker-service --keys=key --prefix=PROGRESS_TRACKER_SERVICE_
```

**That key is this sample's own invention, not a Fred mechanism.** Fred neither
issues nor validates it, and it bypasses this application's entitlement check
outright for whoever holds it. It exists only because a capability currently has
no platform-supplied way to authenticate an outbound call. The platform answer
belongs to `docs/swift/rfc/DELEGATED-DOWNSTREAM-AUTH-RFC.md`, which is design
only today. Read the README section on it before carrying the idea into a real
application.

**Identity comes from the runtime, never from a tool argument.** The capability
reads `ctx.identity.session_id` and sends it with each write; the UI cannot.
That asymmetry is what lets the application show which entries an agent wrote
and which conversation they came from — attribution you get for free rather than
by trusting the model to report itself honestly.

### Showing conversation history in your application

Your service already holds the caller's bearer, so it can read back the
conversations linked to a record:

```
GET {RUNTIME_BASE}/agents/sessions/{session_id}/messages
Authorization: Bearer <the caller's own token>
```

Forward the **caller's** token, never a service credential. The runtime returns
only rows belonging to the authenticated user, and an empty list for anyone
else's session — indistinguishable from a session that does not exist. That is
what makes this safe to expose in a shared application: the view is per-viewer
by construction, and a teammate's transcript stays unreadable even though the
record itself is shared.

You cannot route the user wherever you like: `fred:navigate` is resolved against
your own base path and an escaping path is dropped silently. To hand a record to
a conversation, send `fred:open-chat`. It carries no destination — the host
chooses one — and an optional session id is honoured only when it matches one of
the viewer's own conversations, so at worst it opens a fresh chat.

**Deferred intent is the way around it that needs no contract change.** Instead
of navigating, record what the user intends and let the agent side pick it up:

1. "Discuss in chat" POSTs a short-lived pending pin — one per team and user,
   keyed on the caller's own subject, with a TTL so a forgotten click cannot
   hijack a conversation hours later.
2. The user opens a chat themselves and just starts talking.
3. On the first tool call of a session with no task yet, the capability claims
   the pin and links the session.

The claim is a conditional delete on the pin's `seq_no`, because OpenSearch has
no transactions: two sessions can both read the pin, only one delete succeeds,
and the loser reports no pin rather than double-claiming. The user's identity
comes from the runtime on the agent side and from the bearer on the app side —
the model never names a task or a session, so a prompt cannot redirect the pin
to someone else's work.

## Step 7 — Register it, in both halves

This is where most first deployments fail. Two places, one `app_id`, and
**nothing cross-checks them**.

**Half 1 — the catalog** (control-plane values). Owns what teams see and the
capability that authorization is granted against. No proxy upstream here:

```yaml
platform:
  frontend:
    feature_flags:
      enableApplications: true
  application_sources:
    - app_id: progress-tracker
      ui_prefix: /apps/progress-tracker      # must be exactly /apps/<app_id>
      version: 0.1.0
      icon: checklist
      display_name:
        en: "Progress Tracker"
      description:
        en: "Track long-running work and the decisions taken along the way."
      enabled: true
```

**Half 2 — the routes** (frontend container env). Owns the server-side
addresses:

```yaml
env:
  - name: FRONTEND_APPLICATIONS_JSON
    value: |
      [
        {
          "app_id": "progress-tracker",
          "ui_upstream": "http://progress-tracker-ui.sample-apps.svc.cluster.local:80",
          "service_upstream": "http://progress-tracker-api.sample-apps.svc.cluster.local:8000",
          "service_required": true
        }
      ]
```

**Both upstreams must be fully qualified.** Fred proxies applications through a
variable `proxy_pass`, which makes nginx resolve the host at request time
through its own resolver — and that path does not apply the pod's DNS search
list. A bare Service name yields `could not be resolved` and a 502, while the
same name works from a shell in the very same pod.

Apply, then roll the pods so they pick up the new config:

```bash
helm upgrade fred deploy/charts/fred -n fred -f <your-values> --wait
kubectl rollout restart deployment/frontend deployment/control-plane-backend -n fred
```

## Step 8 — Grant it to a team

Registration grants nothing. A platform admin enables `app__progress-tracker`
for each collaborative team on the Capabilities page, or:

```bash
curl -X PUT -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"enabled":true}' \
  "$FRED/control-plane/v1/admin/capabilities/app__progress-tracker/teams/$TEAM_ID"
```

## Step 9 — Verify, in this order

Each check isolates one layer, so a failure tells you where to look.

```bash
# 1. the UI image, through Fred — note NO trailing slash
curl -o /dev/null -w "%{http_code}\n" $FRED/apps/progress-tracker            # 200

# 2. fail-closed on an unknown id
curl -o /dev/null -w "%{http_code}\n" $FRED/apps/not-real                    # 404

# 3. the catalog sees it for this team
curl -H "Authorization: Bearer $TOKEN" \
  $FRED/control-plane/v1/teams/$TEAM_ID/applications                         # your app listed

# 4. the API, through Fred
curl -H "Authorization: Bearer $TOKEN" \
  $FRED/app-services/progress-tracker/teams/$TEAM_ID/tasks                   # 200

# 5. open it in Fred — the frame should render
```

## Step 10 — Test with someone who should not have access

**Required, not optional.** Forgetting the entitlement check produces no error,
no warning and no log line: you are in a granted team, so every check you
naturally perform passes. The gap is visible only from outside.

```bash
# a user NOT in the granted team
curl -H "Authorization: Bearer $OUTSIDER" \
  $FRED/app-services/progress-tracker/teams/$TEAM_ID/tasks     # expect 403
```

Repeat for a user who *is* in a team whose team was never granted the app —
that case is the one most often missed.

Before trusting a green result, confirm your negative user is actually
negative: a capability left `default_on` makes every team entitled, so the test
passes for the wrong reason.

---

## Troubleshooting

Every row here was hit for real while deploying this sample.

| Symptom | Cause | Fix |
| --- | --- | --- |
| `Could not load tasks: HTTP 404` in the frame | The UI repeated the team segment; the host already prefixes `/teams/<id>` | Send paths relative to that root — `hostFetch("tasks")` |
| A fixed bug persists in the frame, but `curl` through Fred shows the fix | Browser cached the old entry point | `Cache-Control: no-store` on the HTML; hard-reload once to clear what is already cached |
| Frame shows “did not respond” after ~15s | UI server 301s the bare prefix with an absolute `Location` carrying the container's host | `absolute_redirect off` + serve the bare prefix directly. Browsers cache the 301, so re-fetch that URL after fixing |
| 502, log says `could not be resolved` | Bare Service name in `FRONTEND_APPLICATIONS_JSON` | Use `<svc>.<namespace>.svc.cluster.local` |
| Pod `CreateContainerConfigError`, “cannot verify user is non-root” | Image ends `USER <name>` under `runAsNonRoot` | Use a numeric `USER`, or set `runAsUser` |
| API `ImportError: cannot import name 'AsyncOpenSearch'` | The async client needs the extra | `opensearch-py[async]` |
| First read 500s | Searching an index that does not exist yet | Create the index on startup |
| OpenSearch `AuthenticationException(401)` | Wrong credential, or quotes preserved from a `.env` | Read the deployment's actual secret; note `docker --env-file` keeps quotes literally |
| App in the catalog but frame 404s | Registered in the catalog half only | Add the gateway half |
| Routes serve for an app nobody was granted | Registered in the gateway half only | Keep the gateway list a subset of the catalog |
| `enabled: false` did not stop it | That withdraws it from the catalog, not from the gateway | Remove both halves to retire an application |
