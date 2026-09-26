# Delegated execution: upgrade and optional activation

PR: [#2808](https://github.com/ThalesGroup/fred/pull/2808)

Operational impact: **minor** under the agreed migration policy, because optional
activation requires configuration, IAM and OpenFGA operations. The ordinary
upgrade with delegation disabled requires no new mandatory configuration fields.
This classification is input to release preparation, not a published version.
Evaluate the complete release range from the last deployed tag separately.

## Configuration ownership

The production reference is [the Fred chart values](../../../../deploy/charts/fred/values.yaml),
with its generated `values.schema.json`. DevOps reconcile those values with each
customer's deployment repository. Customer secrets and private values need not be
copied into Fred. `apps/*/config/configuration_prod.yaml` is for local developer
Docker Compose only.

## Upgrade with delegation disabled

- Missing `security.delegation` defaults to both switches being `false`. Existing
  configurations do not need new fields merely to keep the feature off.
- The chart now includes the switches for Control Plane, Knowledge Flow and Fred
  Agents. At `applications.<application>.configuration.security`, the optional
  explicit setting is:

  ```yaml
  delegation:
    act_for_people: false
    accept_delegated_calls: false
  ```

- Do not use `delegation.enabled`; that obsolete key is rejected. Do not deploy
  the local-development `FRED_LOCAL_DELEGATION_FILE` override in production.
- This PR adds no Alembic revision relative to `swift`. Check the full release
  range for other database changes before deployment.
- No delegation-specific IAM provisioning, OpenFGA upgrade or coordinated full
  shutdown is required merely to leave delegation disabled. Apply the normal
  deployment procedure and validate it in staging; mixed-version operation and
  zero downtime have not been established by this PR.

The switches do not disable all changes: service-token renewal and bounded 401
retry, authentication diagnostics, authorization responses and frontend contracts
also change. Deploy matching release components. Do not grant `delegation_caller`
to ordinary service identities as a preparation step: holders lose ordinary
service-role shortcuts even while delegation is off.

Before admitting production traffic, check ordinary login, document access, agent
execution and service-to-service cleanup. Exercise token renewal on a long-running
request. Confirm healthy startup and no unexpected 401/403 responses. Keep previous
chart/image versions and effective values available for rollback.

## Optional activation procedure

1. Record previous effective values, image/chart versions, IAM role assignments
   and OpenFGA store/model identifiers. Preserve authorization tuples. Validate
   the procedure in staging before enabling production traffic.
2. Provision workload credentials and the configured caller role and audience
   (defaults: `delegation_caller` on `fred-delegation`). Verify issuer trust and
   login-client exclusions. See [Keycloak](../../platform/KEYCLOAK.md).
3. Use OpenFGA 1.10 or later. Publish/select a compatible model with `active`,
   `suspended` and `standing_ready` on every participant; reconcile any pinned
   model identifiers. See [account standing](../../platform/REBAC.md#account-standing--active-suspended-and-standing_ready).
4. Stop admission of new agent work and drain or explicitly cancel existing runs
   for this coordinated activation. Do not assume a mixed on/off rollout is safe.
5. Set `accept_delegated_calls: true` on Control Plane and restart it first. Wait
   for successful startup: it validates the model and establishes standing
   readiness. Leave its `act_for_people` false.
6. Enable `accept_delegated_calls` on Knowledge Flow and other receiving services;
   restart affected readers, including workers sharing their configuration, and
   verify readiness. Leave outgoing delegation false on non-agent backends.
7. Set `act_for_people: true` on Fred Agents. Also set `accept_delegated_calls:
   true` on agent runtimes receiving delegated calls; such runtimes require both
   switches. Reconcile custom MCP catalogs: servers used under delegation must
   declare `auth_mode: delegated` and support the grant transport. The chart's
   first-party catalog entries already use that mode. Restart affected runtimes.
8. Verify delegated access for an allowed person, refusal for a suspended or
   unauthorized person, token renewal and cleanup. Resume admission only after
   these checks pass. Failed readiness or authorization checks stop activation.

Configuration is read at startup. Adapt workload names and restart commands to
the customer's deployment. The local `make delegation` helper is not a production
provisioning procedure. For credential changes, follow
[workload secret rotation](../WORKLOAD_SECRET_ROTATION.md).

## Rollback

Stop new delegated work and drain or cancel active runs. Disable outgoing
and incoming delegation on affected services, restart them and verify ordinary
access before resuming traffic. Disable delegation everywhere before selecting
an older OpenFGA model or rolling back to binaries without delegation support.

**Disabling delegation also stops the new account-standing enforcement.** Retained
suspension tuples alone no longer block access: establish the required fallback
access controls before admitting traffic. This is not a security-equivalent
rollback for deployments relying on suspension enforcement.

Restore prior chart/images and effective values as required. Restore IAM role
assignments separately, including removal of newly granted caller roles when
returning to ordinary service identities. A Helm rollback does not restore IAM,
OpenFGA tuples/model selection or database state. Retain compatible model/tuples
unless an explicitly verified recovery procedure requires changing them.

## Verification boundary

Configuration defaults and chart changes were checked against the implementation.
Automated authentication/runtime tests and CI cover code behavior; a production
upgrade, coordinated activation and rollback have not been executed. Customer
operators must validate their deployment procedure in staging. No private customer
configuration is needed to understand this note.
