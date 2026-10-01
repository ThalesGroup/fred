# Delegated execution — how an agent acts for a person

Current state of how an agent run calls Fred services on a person's behalf.
Normative requirements: the OpenSpec change
[`add-delegated-agent-execution`](../../../openspec/changes/add-delegated-agent-execution/proposal.md).
Provisioning: [`KEYCLOAK.md` §1.6](KEYCLOAK.md#16-delegation-caller-role).
Account status: [`REBAC.md`](REBAC.md#suspended-accounts--suspended).
Activation and rollback: [migration guide](../ops/migrations/2808-delegated-execution.md).

## Model

Delegation is opt-in: everything below applies only with
`security.delegation.act_for_people` on (see [Switches](#switches)). By default
it is off, and the runtime forwards the person's live bearer to every call.

Three questions, three mechanisms:

| Question | Answered by |
| --- | --- |
| Who is the person? | Keycloak — the person's token, checked once at run admission |
| Who is calling, for whom? | The agent backend's workload token (caller) plus a grant `{person, run, agent}` (subject) |
| What is allowed? | OpenFGA — the person's current relations, checked at each call |

No token carries a permission. The person's bearer is used at admission only;
execution keeps neither it nor a refresh token. Every downstream call presents a
renewable client-credentials token carrying the `delegation_caller` role and the
`fred-delegation` audience, and names the person in the grant.

## Flow

1. **Admission.** The runtime verifies the person's token, checks account status
   and team permission, and writes a local run record (person, run, root agent).
   Only admission sets these values; no tool argument or model output can change
   them.
2. **Each call.** A shared provider checks that the run is live and supplies the
   grant; the shared HTTP authentication adapter supplies the workload bearer and
   renews it once on a 401. Child agents reuse the run with their own `agent` value.
3. **Receiver.** It verifies the bearer (signature, issuer, audience, purpose),
   believes the grant only if the caller holds `delegation_caller` and is not a
   login client, then authorizes the *person*. A service-role shortcut never
   applies to a caller holding `delegation_caller`.
4. **End.** The run lives as long as its HTTP response. Completion, human pause,
   disconnect or cancellation ends the run, its children and their credential
   access. A human answer is a fresh admission.

Refusals stop the run with a typed reason: `authority_lost` (403, suspension, or
`account_status_unavailable` 503) or `delegation_unavailable` (no workload token).

## Switches

`security.delegation.act_for_people` (outgoing, agent backends) and
`accept_delegated_calls` (receivers); both default to `false`. With
`act_for_people` off, the runtime forwards the person's live bearer and sends no
grant. With either switch on, every authenticated request checks
`organization#suspended` once and fails closed when OpenFGA cannot answer.

## Known limits

- **Effective rights are the person's, not person ∩ agent.** `agent` in the grant
  attributes the call; no decision reads it. An agent-level ceiling is an open
  question: [`CAPABILITY-SCOPE-CEILING-RFC.md`](../rfc/CAPABILITY-SCOPE-CEILING-RFC.md).
- **The grant is a trusted workload's statement**, not a signed, sender-bound
  token. Its trust rests on caller-role provisioning, ingress rejection of grant
  parameters and encrypted transport. Its fields map to RFC 8693 (`person` → `sub`,
  `agent` → `act`), so a signed token exchange could replace the transport
  without changing authorization.
- **No delegation outlives a response.** Unattended or long-running background
  work acting for a person is not supported.
- **Out of scope:** third-party services that see only a service account, and
  external APIs holding the person's own data (mail, drive), which need
  per-provider consent.
