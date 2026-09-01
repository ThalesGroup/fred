# Sample application — progress tracker

A minimal, end-to-end example of a Fred application: the user records a task,
then advances it by **talking to agents**, and the application keeps the record
so the work survives across days and separate conversations.

It exists to show the mechanics, not the business case. Everything here is
deliberately small enough to read in one sitting.

> **Fred does not build this.** Nothing under `samples/` is referenced by any
> Fred build target, and nothing in Fred's source imports it. That is the point:
> an application is its owner's images, and this one is no different. If a build
> path ever starts including `samples/`, the sample has stopped being a sample.

---

## What it demonstrates

| Concern | How |
| --- | --- |
| An application is its owner's images | `ui/` and `api/`, built and deployed independently |
| The frame holds no credential | the UI asks the host; the host attaches the bearer |
| The service authorizes itself | every handler asks the Control Plane; the gateway does not |
| Agents advance durable state | a capability with tools, not an app-driven pipeline |
| A conversation finds its record | the session id is pinned on first resolution |
| Human-in-the-loop | the decision is a record the user made and agents later trust |

## The three pieces

```
ui/           static page, served at /apps/progress-tracker/
api/          FastAPI service, reached at /app-services/progress-tracker/
capability/   the agent tools, installed into the agents pod
```

All three live here, together. The capability deliberately does **not** sit in
`libs/` beside Fred's own capability packages: those ship with the platform and
are supported surface, and this one is sample scaffolding. A capability is just
a pip-installable package, so where it lives is a statement about ownership, not
a technical requirement.

Install it into the agents pod the way a fork would install its own:

```bash
uv pip install -e samples/apps/progress-tracker/capability
```

## How a conversation finds its task

The agent never has to be told which record it is on, and the user never types
an id.

1. `find_task` asks the API for the task pinned to **this conversation**. The
   session id comes from `ctx.identity.session_id`, supplied by the runtime.
2. On a new conversation there is no pin, so the agent calls `list_open_tasks`
   and asks which one the user means — once.
3. `pin_task` links the conversation to the record. Every later turn in that
   session resolves with no question, indefinitely.

The session id is **never a tool parameter**. The SDK keeps identity out of the
schema the model sees, so a prompt cannot redirect an agent onto another
conversation's task.

Over weeks a record accumulates the conversations that touched it, which the UI
shows as a conversation count.

## Why the decision record is trustworthy

`record_decision` writes through the API, not straight to storage. That matters:
the API verifies the caller before writing, so "the user decided X" is backed by
an authenticated request rather than by text an agent read in a chat and chose
to believe. An agent writing the record directly would be trusting its own
output.

## Storage: read this before copying the pattern

**This sample stores records in OpenSearch, and that is a deliberate simplification
you should not carry into production for the decision records themselves.**

OpenSearch is a search index, not a transactional store. It has no
transactions, no unique constraints, and last-write-wins on concurrent updates.
Two agents advancing the same task at the same time will silently lose one
write, and nothing will surface it. Over weeks, with several agents touching one
record, that is not a hypothetical.

For a sample — where the point is the architecture and the data is disposable —
it is fine, and it keeps the example to one datastore that the local stack
already runs.

For anything real, put the **authoritative decision records in a transactional
store** and keep OpenSearch as the search and display projection. The API here
is written with its storage confined to a handful of functions precisely so that
swap stays small.

## The service key is this sample's own, not a Fred mechanism

The capability calls this application's API as *itself*, authenticating with a
shared secret, `PROGRESS_TRACKER_SERVICE_KEY`, that the operator creates and
wires into both the API and the agents pod.

**Fred knows nothing about that key.** It appears in three files, all of them
here. The control plane does not issue, validate or rotate it, the gateway never
sees it, and no platform document mentions it. Copying this sample gives you a
pattern, not an integration.

It exists because there is currently no alternative. `fred-sdk` declares a
`TokenProviderPort` and exposes it to capabilities as
`ctx.services.token_provider`, but nothing in the platform implements or injects
it. An earlier version of this capability read that port, found `None` every
time, and sent no credential at all.

Two reasons not to standardise on it before that changes:

- The key is a **full bypass** of the entitlement check. That path returns the
  team without asking the control plane anything, which is considerable
  authority for a static environment variable with no rotation story.
- Every application doing this invents a different secret, and nothing makes
  them consistent, revocable together, or auditable.

The platform answer belongs to
`docs/swift/rfc/DELEGATED-DOWNSTREAM-AUTH-RFC.md` (AUTH-TX). It is design only
today, and it names the same root cause: the pod holds one fixed-lifetime
credential and cannot renew it for downstream calls. When that lands, this key
should be deleted rather than generalised.

## Register it

Two halves, one `app_id`. See `docs/swift/platform/FORKING_GUIDE.md` for the
full explanation, including why both upstreams must be fully qualified.

Control plane:

```yaml
platform:
  frontend:
    feature_flags:
      enableApplications: true
  application_sources:
    - app_id: progress-tracker
      ui_prefix: /apps/progress-tracker
      version: 0.1.0
      icon: checklist
      display_name:
        en: "Progress Tracker"
      description:
        en: "Track long-running work and the decisions taken along the way."
      enabled: true
```

Frontend gateway:

```
FRONTEND_APPLICATIONS_JSON: |
  [
    {
      "app_id": "progress-tracker",
      "ui_upstream": "http://progress-tracker-ui.<namespace>.svc.cluster.local:80",
      "service_upstream": "http://progress-tracker-api.<namespace>.svc.cluster.local:8000",
      "service_required": true
    }
  ]
```

Then a platform administrator grants `app__progress-tracker` to a team.
Registration alone grants nothing.

The API needs `CONTROL_PLANE_BASE` (for the entitlement check) and the
OpenSearch connection. The capability needs `PROGRESS_TRACKER_API_BASE`; without
it, it contributes no tools rather than failing at call time.

## Before you ship anything modelled on this

Create a user who is **not** in the granted team, get a token, and call the API
directly:

```
GET /app-services/progress-tracker/teams/<granted-team>/tasks   as the outside user
expected 403 — a 200 means your data is readable by the whole realm
```

Repeat for a user who *is* in a team that was never granted the app. Forgetting
the entitlement check produces no error and no log line, because from inside a
granted team everything looks correct. That test is the only way to see it.


## Handing a task to a conversation

An application cannot route the user anywhere it likes: `fred:navigate` is
bounded to its own subtree and an escaping path is silently dropped. The one
exception is `fred:open-chat`, which names no destination — the host decides
where it lands, and honours a session id only after matching it against the
viewer's own conversations.

"Discuss in chat" records a short-lived pending pin, then asks the host to open
a conversation — resuming the one this task was last discussed in when that
conversation belongs to the viewer, and starting a fresh one otherwise. The
first tool call of an unlinked session claims the pin and links it, so there is
nothing for the user to type. A conversation that is already linked drops the
pin instead of claiming it, so a spent intent cannot capture the next chat.

The pin is keyed on team plus the caller's subject and expires, so a click that
is never followed up simply lapses. Claiming is a conditional delete, so two
conversations starting at once cannot both take it.
