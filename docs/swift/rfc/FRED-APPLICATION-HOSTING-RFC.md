# RFC: Team-scoped application hosting

**Status:** Draft, pending sign-off

**Author:** Fred platform team

**Area:** `control-plane-backend`, `frontend`, deployment

---

## 1. Decision

Fred gains an Apps surface. An application is **one or two container images
that Fred does not build**: a user interface, and optionally an API. Fred
renders the interface inside its own shell and proxies the API, but compiles no
application code and holds no application source.

Registration is deployment configuration. Adding, updating or removing an
application is a configuration change and a redeploy of the owner's images —
never a rebuild of Fred.

Access is team-scoped and reuses the existing capability enablement model
rather than introducing a second entitlement system.

---

## 2. Problem

Teams need product surfaces inside Fred — a dashboard over their agents' data,
a domain-specific console — that Fred itself should not own. Today the only
ways to add one are to modify Fred's frontend source or to fork it. Both bind
the application's release cycle to Fred's: every change to someone else's
product requires rebuilding and redeploying Fred, and every upstream merge
risks conflicting with the fork's additions.

The teams who would write these applications already build and deploy their own
agent pods. They hold repository access and ship their own images. The
extension boundary should look like the one they already use for agents, not
like a plugin system for untrusted publishers.

---

## 3. Goals and non-goals

### 3.1 Goals

- An application ships as its owner's container images, released on the owner's
  cycle, with no Fred rebuild and no Fred source edited.
- Registration is deployment configuration, readable and reversible by an
  operator without touching code.
- Access is granted per collaborative team through the existing capability
  model, and administered on the surface administrators already use.
- The interface is contained: a failing application must not take down the
  Fred shell around it.
- The boundary is written so that serving an application from its own origin
  later is a configuration change, not a redesign.

### 3.2 Non-goals

- An open marketplace, or applications from authors who would not be granted
  repository access. The trust model assumes the same footing as agent pods.
- Personal-space or per-user grants. Admission is scoped to collaborative
  teams.
- A build-time plugin API, shared component library, or any coupling that puts
  application code into Fred's bundle.
- Object-level permissions inside an application. What an application shows a
  member of an entitled team is the application's own concern.

---

## 4. Proposed architecture

### 4.1 Two prefixes, one per image

Fred serves two browser-facing prefixes per application:

| Prefix | Serves | Called by |
| --- | --- | --- |
| `/apps/<app_id>/` | the interface image | the browser, inside the frame |
| `/app-services/<app_id>/` | the API image (optional) | the application's own code |

The whole interface prefix is forwarded upstream so the bundle's own absolute
asset URLs resolve back through the gateway. The service prefix is stripped
before proxying, so the API sees ordinary paths and the browser never learns the
upstream address.

An interface-only application simply has no API; calls to its service prefix
answer unavailable rather than missing.

### 4.2 Registration in two halves

Registration is split by responsibility, and the split is deliberate:

- **Control plane** — the catalog entry an operator authors: the application id,
  the browser-facing prefix, version, icon, localized display strings, and
  whether the entry is active. This half owns what teams see and the capability
  that authorization is granted against. It registers no proxy upstream.
- **Frontend gateway** — the server-side addresses to proxy to. This half never
  reaches the browser and never authorizes anything.

The application id is the only value both halves carry. Keeping proxy
configuration with the process that proxies, and catalog configuration with the
process that authorizes, avoids a second source of truth for either.

Display strings are carried as locale maps rather than translation keys, since
an independently deployed application has no entry in Fred's own bundle.

### 4.3 The frame contract

Fred renders the interface in an iframe and communicates with it **only by
message passing**, over a closed message schema. Anything not in that schema is
dropped before it reaches Fred state, the router or diagnostics.

Compatibility is settled at runtime by a protocol handshake: the frame
announces the version it speaks, Fred validates it and renders an explicit error
state on a mismatch. No build-time digest or compiled-module check is possible,
because Fred never compiles the application.

The host retains what the application must not hold. It owns the bearer
lifecycle, the service root and the team scope; the frame owns only a relative
resource path. A token never crosses into the frame, and the frame never names
an upstream.

Nothing may depend on the frame sharing Fred's origin. Reaching into the parent
document, shared globals or a shared build would work today and stop working the
day an application is served from its own origin, so the contract forbids them.

**How the contract grows.** Applications will reach its limits; that is expected
and is not evidence the boundary is wrong. When an application needs something
the contract does not offer, the answer is to add a message to it — deliberately,
with the constraint stated and reviewed, as §4.5 works through for one case. The
answer is not to remove the boundary.

This is worth stating as a standing rule rather than leaving to §7's one-time
comparison, because the pressure is asymmetric. Each individual limit is
concrete, immediate and easy to argue against; the reasons for the boundary are
diffuse and deferred, so they lose every argument taken one at a time. The
asymmetry that should decide those arguments is that a widened contract is
reversible and reviewable, while removing the frame is neither — it exchanges
this coupling for permanent version lockstep with every fork, forecloses serving
an application from its own origin, and gives up isolation with no path back.

Reopening that trade is legitimate only if applications stop being satellite
surfaces and become primary product screens, where the visual seam costs more
than the coupling. A single unmet requirement is not that.

### 4.4 Routing constraint

While an interface is served from Fred's origin, its browser-facing prefix must
be exactly the prefix derived from its application id. The gateway routes on
that path segment, so any other value cannot reach the application, and the
resulting failure is indistinguishable from a service that is merely slow to
start. This should be rejected when configuration loads, making the mistake
unexpressible rather than merely detectable.

The absolute form stays unconstrained, so that moving an application to its own
origin remains a configuration edit.

### 4.5 Open question: handing a record to a conversation

An application that tracks long-lived work will want to send the user from a
record to a conversation about that record. It cannot, and the containment is
deliberate at three independent points:

- the frame message vocabulary is closed — an unrecognised type is parsed to
  nothing, so an application cannot introduce one;
- the host discards anything the parser rejects, silently, so a frame cannot
  even detect the refusal;
- the one navigation message is confined to the application's own route
  subtree, and an absolute path is rejected outright.

Every workaround is closed with it. Reaching the top window would depend on the
frame being same-origin, which this contract forbids relying on; a target-`_top`
link is inert under the frame's sandbox; and the frame's only outbound call is
routed exclusively to its own service prefix, so it cannot create a session
itself.

That is the correct default. The confinement is what stops a compromised
application from steering the user around the product, and the closed
vocabulary is what makes the contract auditable at all. The question is whether
to grant a single, narrowly scoped exception.

**Shape, if granted.** One additional frame message asking the host to open a
conversation with a record as context. The host — never the frame — decides the
destination, so the frame supplies context and not a route. The obvious
constraints are that it may reach only the conversation surface, only within
the team the frame was handed, and never an arbitrary path.

**Why it is not obviously right.** It would be the first message that moves the
user out of the application's subtree, converting a boundary with no exceptions
into a boundary with one. Boundaries with one exception attract a second. The
alternative costs an application only a lookup: an agent-side tool that lists
the caller's open records and resolves the intended one on the first turn,
which needs no contract change and keeps the containment intact.

**Prerequisite either way.** Navigation alone is not useful; the record's
context has to reach the agent, and how it gets there is a second design
question sitting behind the first.

The obvious candidate is not a fit. `context_prompt_ids` is an ordered list of
**prompt-library references** — personal or team prompt ids, resolved against
the caller's authorized teams and joined as conversation context at execution
time. It is a curated, human-owned, long-lived asset. Routing per-record context
through it would mean minting a library entry for every task, on a completely
different lifecycle, with nothing responsible for removing them. It would
degrade a feature users own in order to carry machine state.

Session attachments are closer, and already do most of the mechanical job: a
session-scoped row holding free text, written server-side, folded into the
system prompt on every turn and never surfaced as a user-editable prompt. What
does not fit is the framing. That text reaches the agent introduced as files the
user attached, with an instruction to retrieve their content through the search
tools — so record context carried this way would describe an attachment that
does not exist, and point the agent at an index that has nothing to return.

The carrier question is therefore narrower than "build something new": either
the attachment channel grows a variant that is honest about not being a file, or
a sibling to it appears. Either way it should be settled before the navigation
message is worth adding, because navigation without context only moves the user
to an agent that still has to ask which record it is looking at.

**Recommendation:** do not grant it yet. Build an application that wants it,
using the lookup approach, and let the friction be measured rather than
predicted. If the first turn of every conversation proves genuinely costly, the
evidence will also say what context the message must carry.

---

## 5. Authorization

Each registered application derives a capability from its id. Registration
alone grants nothing: a platform administrator enables that capability per
collaborative team on the existing administration surface.

Discovery must authorize before reading anything else. A caller who is not a
member of a team is refused without learning whether the team or any
application exists; a member sees only applications their team has been granted.
Personal spaces return nothing.

Grants are held **team to capability**, never user to capability, so any
correct check answers two questions: is this caller a member of the team, and
does the team hold the application.

### 5.1 Open question: where enforcement belongs

The gateway is proposed as pure routing — it checks that an application id is
registered and has an upstream, then forwards the caller's credentials
untouched. Under that design **the application's own API is the only thing
authorizing its data**, and an application that omits the check is readable by
every authenticated principal.

Two properties make this sharper than an ordinary reminder to check
authorization. There is no safety net: the API is code its owners write, in
their own container, and no misconfiguration exists for an operator to notice.
And the failure is invisible from the inside — the author belongs to an entitled
team, so every check they naturally perform passes, and nothing errors or logs.

The alternative is for the gateway to verify entitlement before proxying. It
would be mechanically small, reusing the existing team-subject capability query.
Its costs are not:

1. The gateway stops being pure routing and acquires an authorization
   dependency, which is what allows it to be operationally simple.
2. The control plane enters the hot path of every application API call —
   latency per request, and control-plane unavailability becoming application
   unavailability. A short-lived cache makes the call rare but introduces
   revocation lag.
3. It risks being a confused deputy. The gateway can only authorize the team
   identifier it parses from the request path; it cannot know what the
   application does with that path, or whether the response is scoped to that
   team at all. It would appear to have authorized a response it never saw.

A guarantee that looks stronger than it is may be worse than none, because
application authors would reasonably stop writing their own check.

**Options:** documentation and a mandatory negative test; gateway enforcement;
a short-lived signed entitlement assertion the application verifies; or
enforcement limited to Fred-owned routes, which does not cover the exposure.

This RFC proposes starting with the documented requirement and treating gateway
enforcement as a separate decision, because only the application knows what its
response contains.

---

## 6. Lifecycle

Registration begins as configuration only: an entry removed from configuration
disappears at the next load, and nothing records that it once existed.

A durable lifecycle is required before removal can be considered safe, and is
proposed as follow-up work:

- Durable state keyed by application id. An id seen previously and now absent
  becomes a tombstone — unavailable to teams even if authorization relations
  remain, but visible to administrators for cleanup.
- A tombstoned id that reappears enters a pending state and cannot be listed,
  loaded or proxied until an administrator re-establishes its relations. A
  version update that stays continuously registered must not create a new
  generation or discard valid grants.
- Removal is two-stage: revoke access, confirm no team retains it, then remove
  the registration.

The source boundary discovery reads from should be defined narrowly enough that
a durable implementation can replace a configured one without changing the
discovery service or the API contract.

**Related asymmetry to resolve:** because the two halves are independent,
deactivating a catalog entry stops teams seeing an application but does not stop
the gateway serving its routes. Retiring an application requires removing both.

---

## 7. Alternatives considered

**Compile applications into Fred's frontend.** Simplest to build and the reason
this RFC exists: it binds every application change to a Fred release, and forces
forks to modify Fred-owned source.

**Runtime module federation.** Avoids the frame and gives tighter integration,
but requires the application to share Fred's framework and build assumptions,
and permanently forecloses serving an application from its own origin. It does
not remove coupling so much as invert it: instead of an application rebuilding
when its own code changes, every application rebuilds when Fred upgrades its
framework, router or design system. With forks on independent cadences that is a
standing coordination cost rather than a one-off. Rejected as a standing
position, not only as a design-time comparison — see §4.3.

**A separate entitlement system for applications.** Rejected: administrators
would learn a second model, and grants would drift from the capability model
already used for every other team-scoped feature.

**Signed packaging with supply-chain attestation.** Appropriate for untrusted
publishers, and disproportionate here. Applications are built by teams who
already hold repository access and already deploy their own agent pods; the
verification cost buys nothing the existing trust boundary does not.

**Implicit team from session context.** Rejected: an explicit team in the route
keeps admission checkable at the boundary and avoids ambiguity when a user
belongs to several teams.

---

## 8. Open questions

1. Where authorization for the application API belongs (§5.1). This is the
   decision with the widest consequences and should be settled explicitly.
2. The durable registration and removal lifecycle (§6), including the catalog
   and gateway asymmetry.
3. Whether to let an application hand a record to a conversation (§4.5). It is
   the first exception to the subtree confinement, so it is a boundary decision
   rather than a convenience.
4. Serving an application from its own origin. The contract is written to make
   this a configuration change; it needs verifying under an opaque origin before
   the isolation property can be claimed rather than intended.
5. Typed, non-secret per-team application configuration beyond enablement.
6. Where application health belongs relative to existing operational health
   surfaces.
7. Personal-space availability, and how it would interact with the existing
   personal capability class.

Items 5 through 7 want evidence from more than one independently developed
application before being standardized.

---

## 9. Acceptance

This RFC is complete when §5.1 and §4.5 each have a recorded decision and
rationale, and §6 has either an owner or an explicit deferral. §4.5 in
particular should be decided against a real application that wanted it, not in
the abstract. Anything settled moves into the relevant contract or platform
document and is removed from this RFC rather than amended in place.
