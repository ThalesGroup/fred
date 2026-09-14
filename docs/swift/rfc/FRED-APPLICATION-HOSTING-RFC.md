# RFC: Team-scoped application hosting

**Status:** Draft, pending sign-off

**Author:** Fred platform team

**Area:** `fred-core`, `control-plane-backend`, `frontend`, deployment

---

## 1. Decision

Fred gains an Apps surface. An application is **one or two container images
that Fred does not build**: a user interface, and optionally an API. Fred
renders the interface inside its own shell and proxies the API, but compiles no
application code and holds no application source.

Registration is deployment configuration. Adding, updating or removing an
application is a configuration change and a redeploy of the owner's images —
never a rebuild of Fred.

Access is team-scoped. Applications reuse the existing enablement workflow and
administration surface, but are first-class `app` resources in OpenFGA rather
than capability objects. The shared catalog keeps `app__<app_id>` as its flat
administrative identifier; authorization uses `app:<app_id>`.

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
- Access is granted per collaborative team through a first-class OpenFGA
  application object, administered on the surface administrators already use.
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
  whether the entry is active. This half owns what teams see, maps the shared
  catalog id `app__<app_id>` to the authorization object `app:<app_id>`, and
  registers no proxy upstream.
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

**Resolved — granted, in the narrowest form that is still useful.** One
message, `fred:open-chat`. The frame names no route: it may attach a session
id, and the host builds the target itself from the team it is already
rendering.

Be precise about what that buys, because an earlier draft of this section
claimed more. The id is a *candidate*, not a destination. The host matches it
against the caller's own session listing and takes the agent instance from the
matched record, never from the message; an id that does not match falls back to
a new conversation, or to the team's agents surface when the agent choice is
ambiguous. The reachable set is therefore bounded by conversations the viewer
already owns and can already open from the sidebar.

That is weaker than "the destinations are fixed when this code is reviewed",
which is what a payload-free message would have delivered and what the earlier
wording implied. The bound now rests on two runtime properties rather than on
the shape of the message: that the session listing is scoped to the caller, and
that an unmatched id falls back rather than failing open. Both are worth naming
here, because changing either widens this exception without touching the frame
contract at all.

The carrier question that blocked this dissolved rather than being answered.
Nothing about the record travels on the message: an application records what
the conversation should be about through its own service, and the receiving
agent capability resolves it from the runtime identity. No session-scoped
context channel was needed after all.

The durable description now lives in `CONTROL-PLANE-PRODUCT-CONTRACT.md` (frame
contract).

## 5. Authorization

Application authorization is now a settled dependency of this still-open
hosting proposal. The shared administration catalog keeps `app__<app_id>`,
while OpenFGA uses the first-class object `app:<app_id>`. Registration alone
grants nothing, and V1 applications are collaborative-team-only.

The current reader, writer, personal-space and model-first rollout contracts
live in `CONTROL-PLANE-PRODUCT-CONTRACT.md` §46 and `REBAC.md`; this RFC does
not duplicate those validated details. The remaining proposal concerns in §8
must build on that authorization boundary rather than treating an application
as a capability object.

### 5.1 Authorization delivery boundary

The current app-type change provides configuration-based registration and
existing team entitlement controls only. Its model has no app-wide active
marker and it requires no lifecycle registry or reconciliation command.
Higher-consistency app admission and independently useful security hardening
remain. The product contract and ReBAC guide carry the current behavior.

Config withdrawal is not global revocation or permission cleanup. A directly
reachable first-party backend can still accept surviving entitlement; re-adding
the same identifier can reuse it. Existing entitlement revocation and route
restrictions remain the available controls.

## 6. Deferred shared resource lifecycle

Global **Deactivate**, later **Activate**, and **Delete** are explicitly
deferred from this application feature. The follow-up must be a generic design
for all or most applicable ReBAC resource types, with documented exceptions
where their ownership or permission models differ.

The open design must cover:

- Desired-state ownership and precedence between configuration and future UI actions.
- Global denial overriding explicit grants and inherited defaults.
- Retained settings during deactivation and their reactivation semantics.
- Trustworthy inventory, deliberate removal and protection against incomplete configuration.
- Exact permission cleanup, unrelated-resource protection and re-registration.
- Uncertain writes, resumable recovery, stale or incompatible writers and cache freshness.
- Migration, mixed-version rollout, rollback and operational verification.

No database registry, global-gate representation, recovery flag or per-type
rollout is selected for the future lifecycle design. A generic cleanup primitive does
not by itself implement safe resource deletion. Workload, gateway and owned
data retirement require separately defined authority as applicable.

The [OpenSpec gap](../../../openspec/changes/first-class-application-rebac/design.md#deferred-gap--shared-resource-lifecycle)
records this boundary. Deployment requires schema and authorization-model
compatibility; incompatible state requires a separately approved state-preserving
migration plan. This RFC supplies no automatic downgrade or deployed-state change.

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

**A separate administration system for applications.** Rejected:
administrators would learn a second workflow, and its enablement state could
drift from the shared administration surface used for team-scoped features.

**Signed packaging with supply-chain attestation.** Appropriate for untrusted
publishers, and disproportionate here. Applications are built by teams who
already hold repository access and already deploy their own agent pods; the
verification cost buys nothing the existing trust boundary does not.

**Implicit team from session context.** Rejected: an explicit team in the route
keeps admission checkable at the boundary and avoids ambiguity when a user
belongs to several teams.

---

## 8. Open questions

1. Shared resource lifecycle in §6: determine applicable resource types, authority,
   global denial, cleanup and recovery without an app-only subsystem.
2. ~~Whether to let an application hand a record to a conversation (§4.5).~~
   Decided — granted as `fred:open-chat`, with the bound and its two runtime
   dependencies recorded in §4.5. Kept in this list only until §4.5 is folded
   into the contract doc and trimmed from here.
3. Serving an application from its own origin. The contract is written to make
   this a configuration change; it needs verifying under an opaque origin before
   the isolation property can be claimed rather than intended.
4. Typed, non-secret per-team application configuration beyond enablement.
5. Where application health belongs relative to existing operational health
   surfaces.
6. Personal-space availability, and how it would interact with the existing
   personal capability class.
7. Future lifecycle UI/API actions and configuration precedence belong to the
   shared design in §6; they are not prerequisites for the app-type feature.

Items 4 through 6 want evidence from more than one independently developed
application before being standardized.

---

## 9. Acceptance

This RFC is complete when §4.5 has a recorded decision and rationale, and §6
has either an owner or an explicit deferral. The app-type delivery boundary
in §5.1 does not claim shared lifecycle implementation. §4.5 in particular
should be decided against a real application that wanted it, not in the abstract.
Anything settled moves into the relevant contract or platform document and is
removed from this RFC rather than amended in place.
