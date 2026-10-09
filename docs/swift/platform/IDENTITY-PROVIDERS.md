# Identity providers

Fred keeps Keycloak as the default identity provider. A deployment can select an
OIDC issuer in its security configuration. OIDC mode uses the issuer's discovery
document at startup for the JWKS and token endpoint; explicit endpoint overrides
are available. In the browser, Keycloak and other OIDC providers use the same
`oidc-client-ts` lifecycle behind the existing authentication service. A new
provider still needs a live sign-in, refresh and logout check before rollout.

## Settings

Set these in the `security` block of each backend. The user block identifies
people; `m2m` identifies each backend's confidential client.

| Setting | Default | OIDC use |
| --- | --- | --- |
| `user.provider`, `m2m.provider` | `keycloak` | `oidc` |
| `user.realm_url`, `m2m.realm_url` | required Keycloak realm URL | OIDC issuer URL |
| `user.audience` | `user.client_id` | API application ID in access tokens |
| `user.scope` | unset | delegated API scope requested by the UI |
| `user.jwks_url`, `user.token_url`, `m2m.token_url` | unset | optional discovery overrides |
| `user.roles_claim` | `resource_access.<client_id>.roles` | claim path such as `[roles]` |
| `user.claims.uid` | `sub` | `oid` for Entra; a non-UUID OIDC value becomes a deterministic UUID |
| `user.claims.username` | `preferred_username` | set to a claim present in access tokens |
| `user.claims.email`, `given_name`, `family_name` | matching claim names | adjust if the provider differs |
| `m2m.scope` | unset | API app ID URI plus `/.default` for Entra |
| `user_directory` | `keycloak` | `local` |

The settings are optional except the existing client IDs and issuer/realm URLs.
The defaults preserve the Keycloak behavior. In OIDC mode, Fred rejects a
Keycloak directory, `delegation.service_accounts_only: true`, and active
delegation without `delegation.caller_roles_claim` at startup.

The local directory stores only people who have signed in. It does not create
or delete accounts at the identity provider: creation returns
`managed_by_identity_provider`, while deletion suspends the person in Fred, including when delegation is disabled. Enforced OpenFGA services validate account-status support at startup. A local delete returns 403 `account_suspension_disabled` if enforcement is disabled; an unavailable account-status check returns 503 `account_status_unavailable`.
A non-UUID OIDC uid maps to UUIDv5 using the normalized issuer and claim value;
changing either changes the Fred user ID and personal space. Server-side
refresh of a person's token depends on the provider. For Entra SPA tokens,
enable workload delegation rather than relying on backend person-token refresh.

For both browser providers, definitive renewal refusals (`invalid_grant`,
`login_required`, `interaction_required`, `consent_required`,
`account_selection_required`) clear Fred's access/refresh tokens and stored OIDC
user. Network/provider outages and timeouts preserve an unexpired bearer and
permit retry; an expired bearer is never returned. A delayed renewal cannot
restore a refused session or replace a newer accepted generation.

Local imports require unambiguous exact usernames. If distinct local IDs share a
referenced username, preflight fails with `ambiguous_username` before writing
bundle rows or roles. Collisions on names outside the bundle do not block it.
Refresh the old owner's profile or reconcile snapshots against the provider;
Fred never chooses an owner by row order or deletes a conflicting identity.
A unique snapshot can still be stale; uniqueness does not verify current IdP
ownership. Existing case-sensitive resolution is preserved.

## Microsoft Entra ID recipe

1. Create a **Fred API** app registration. Set its Application ID URI to
   `api://fred-api`, expose delegated scope `access_as_user`, set
   `requestedAccessTokenVersion` to `2`, and define application roles
   `service_agent` and `delegation_caller` with Application as an allowed member
   type. Configure optional access-token claims `email`, `given_name`, and
   `family_name` if Fred needs them. Record the API application's GUID.
2. Create a **Fred UI** SPA registration. Register the exact browser redirect
   and post-logout URLs (for local development, `http://localhost:5173/`), grant
   delegated permission `api://fred-api/access_as_user` and `offline_access`,
   and use authorization code with PKCE. Record its client ID. The browser never receives a client
   secret.
3. Create separate confidential registrations for **runtime**, **knowledge
   flow**, and **control plane**. Grant each the Fred API `service_agent`
   application role and grant `delegation_caller` to the runtime client. Grant
   administrator consent for the API application permissions and configure a
   credential for each confidential client. Keep credentials in the deployment
   secret store.
4. Configure each backend's `security.user` with `provider: oidc`,
   `realm_url: https://login.microsoftonline.com/<tenant-id>/v2.0`,
   `client_id: <Fred UI client ID>`, `audience: <Fred API GUID>`,
   `scope: api://fred-api/access_as_user`, `claims.uid: oid`, and
   `roles_claim: [roles]`. Set `security.user_directory: local`.
5. Configure each backend's `security.m2m` with `provider: oidc`, the same
   issuer, its own confidential `client_id`, its existing `secret_env_var`,
   and `scope: api://fred-api/.default`. On the runtime set
   `delegation.act_for_people: true`; on receivers set
   `delegation.accept_delegated_calls: true`. Where delegation is used, set
   `caller_roles_claim: [roles]`, `audience: <Fred API GUID>`, and
   `service_accounts_only: false`.
6. Set `FRED_JWT_MAX_LIFETIME_SECONDS=6000` for the backends that validate
   Entra access tokens. Verify the actual token lifetime and claims in the
   test tenant before rollout.

Microsoft's [API registration guide](https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-configure-app-expose-web-apis),
[SPA authorization code guide](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow),
[application-permission scope guide](https://learn.microsoft.com/en-us/entra/identity-platform/scopes-oidc),
and [optional-claims guide](https://learn.microsoft.com/en-us/entra/identity-platform/optional-claims)
explain the Entra-side setup.

## Generic OIDC checklist

- Confirm the issuer's discovery document reports the exact issuer URL and
  valid JWKS and token endpoints. Fred checks the issuer at startup.
- Confirm browser code flow with PKCE, CORS for the token endpoint, exact
  redirect/logout URLs, and a scope that yields an API access token. The UI
  requests `openid profile offline_access` along with the configured API scope;
  confirm that refresh tokens or silent authorization work for this provider.
- Inspect a person access token and a client-credentials access token for
  issuer, audience, uid, username, roles, and expiry. Configure claim paths
  against those access tokens, not an ID token.
- Give backend service clients the provider's required scope and role grants.
  Configure delegation's audience and caller-role path from the workload token.
- Select `user_directory: local` and test sign-in, user lookup, personal spaces,
  create refusal, and deletion suspension. People absent from the local table
  cannot be found until they sign in.

## Terms of use before platform access

The three reference `configuration_prod.yaml` files require `app.gcu_version: v1`.
Generated Keycloak, generic OIDC, mock OIDC and ZITADEL profiles use that version.
Keep the same version in all three backends; restart them after changing it.

After sign-in, `GcuGuard` displays the terms before the platform-admin bootstrap
and the application. The acceptance button becomes available after scrolling to
the end of the text. `POST /control-plane/v1/gcu` stores the current version in
Fred's shared user database. Human endpoints using `get_current_user` return
HTTP 403 (`user_not_accept_gcu`) until that version has been accepted.
This applies to administrators too. Previously accepted `v1` is retained.

Public configuration and the authenticated user-details/acceptance endpoints
remain reachable to complete this flow. Service endpoints using
`get_current_user_or_service` admit service identities without interactive
acceptance; delegated calls rely on the person's acceptance at run admission.

## Complete local test configurations

Example overlays for `generic_oidc`, `mock_oidc`, `entra` and `zitadel` live in
`../fred-deployment-factory/examples/identity-providers/<backend>/`. Clone that
repository next to Fred. Generate complete Keycloak, generic OIDC or mock OIDC
configurations from the Fred repository root:

```bash
/usr/bin/python3 scripts/prepare_identity_provider_configs.py
```

On another machine, `uv run scripts/prepare_identity_provider_configs.py` resolves
the declared `pyyaml` and `jsonschema` dependencies. By default the script
generates the three profiles that need no tenant IDs. Select one profile with
`--profile`; `--output-dir` changes the destination. The generator validates
every complete YAML against its application schema. It preserves non-security
settings and does not read `.env` files.

For a real Entra tenant, register the clients described above, then supply their
**public** identifiers to the generator:

```bash
/usr/bin/python3 scripts/prepare_identity_provider_configs.py --profile entra \
  --entra-tenant TENANT_ID --entra-ui-client UI_CLIENT_ID \
  --entra-api-client API_CLIENT_ID_GUID \
  --entra-control-plane-client CONTROL_PLANE_CLIENT_ID \
  --entra-knowledge-flow-client KNOWLEDGE_FLOW_CLIENT_ID \
  --entra-runtime-client RUNTIME_CLIENT_ID
```

Set `ENTRA_CONTROL_PLANE_CLIENT_SECRET`, `ENTRA_KNOWLEDGE_FLOW_CLIENT_SECRET`
and `ENTRA_AGENTIC_CLIENT_SECRET` in the respective backend and worker
process environments. Set `FRED_JWT_MAX_LIFETIME_SECONDS=6000` on all three
backends. The generated YAML contains no secret values. The six arguments are
required; the generator will not publish an Entra profile with placeholder IDs.

For ZITADEL, run the factory provisioner. It registers clients, assigns roles,
checks workload tokens and generates complete configurations and a private
credential file from its dynamic project and client IDs:

```bash
make -C ../fred-deployment-factory zitadel-configure SWIFT_SRC="$PWD"
```

The factory `configuration_zitadel.example.yaml` files show the expected settings for
each backend. Their placeholder IDs are illustrative; use the factory-generated
files for tests.

| Profile | Complete configuration directory | Provider setup |
| --- | --- | --- |
| `keycloak` | `/tmp/fred-idp-tests/keycloak` | Existing Keycloak settings |
| `generic_oidc` | `/tmp/fred-idp-tests/generic_oidc` | Factory strict generic profile on port 8080 |
| `mock_oidc` | `/tmp/fred-idp-tests/mock_oidc` | Factory mock issuer on port 8090 |
| `entra` | `/tmp/fred-idp-tests/entra` | Your Entra tenant and registered clients |
| `zitadel` | `/tmp/fred-idp-tests/zitadel` | Factory provisioner on port 8091 |

Each directory contains `configuration_control-plane-backend.yaml`,
`configuration_knowledge-flow-backend.yaml`, `configuration_fred-agents.yaml`
and `conversation_policy_catalog.yaml`. Select the matching YAML with
`CONFIG_FILE`. The generated files retain baseline Postgres, OpenFGA, Temporal,
storage and model settings; those services and normal application credentials
must be available. Regenerate after changing a baseline configuration. Localhost
URLs are for applications running on the host, not inside Kubernetes pods.
For Kubernetes with Entra, use
[`values-entra.example.yaml`](../../../deploy/charts/fred/values-entra.example.yaml).

### Local launch

Start the Docker infrastructure and prepare the chosen provider in the sibling
`fred-deployment-factory` checkout. Generate complete configs with the command
above, or use `make -C ../fred-deployment-factory zitadel-configure SWIFT_SRC="$PWD"`
for ZITADEL. Then follow the manual launch below. Stop running Fred applications
before changing profiles; the provider switch does not reset Fred data.

### Manual launch

Select one profile in each of six terminals, from the Fred root:

```bash
cd /path/to/fred
export FRED_TEST_PROFILE=keycloak
# Or: export FRED_TEST_PROFILE=generic_oidc
# Or: export FRED_TEST_PROFILE=mock_oidc
# Or: export FRED_TEST_PROFILE=zitadel
```

Prepare the matching provider as described above and in the factory guide.
Stop the six applications before switching profiles; keep the infrastructure
running. Then set these variables in each terminal:

```bash
export FRED_TEST_ROOT="$PWD"
export FRED_TEST_CONFIG_DIR="/tmp/fred-idp-tests/$FRED_TEST_PROFILE"
export FRED_TEST_UV="$FRED_TEST_ROOT/apps/control-plane-backend/.venv/bin/uv"
if [ "$FRED_TEST_PROFILE" = zitadel ]; then
  . "$FRED_TEST_CONFIG_DIR/service-credentials.env"
fi
# OIDC profiles: allow the mock lifetime and ignore a stale Keycloak policy.
if [ "$FRED_TEST_PROFILE" != keycloak ]; then
  export FRED_JWT_MAX_LIFETIME_SECONDS=6000
  export FRED_LOCAL_DELEGATION_FILE=
else
  unset FRED_JWT_MAX_LIFETIME_SECONDS
  export FRED_LOCAL_DELEGATION_FILE="$FRED_TEST_ROOT/apps/control-plane-backend/config/.delegation.local.json"
fi
```

For Keycloak, the delegation file must already exist (`make delegation` at
Fred's root prepares the local files). The two other backends automatically
select their own local delegation file when running the Keycloak profile:
use the per-component override shown below. Start each process in its own
terminal using the same profile:

```bash
make -C apps/control-plane-backend run PORT=8222 UV="$FRED_TEST_UV" \
  CONFIG_FILE="$FRED_TEST_CONFIG_DIR/configuration_control-plane-backend.yaml"

make -C apps/knowledge-flow-backend run PORT=8111 UV="$FRED_TEST_UV" \
  FRED_LOCAL_DELEGATION_FILE="${FRED_LOCAL_DELEGATION_FILE/control-plane-backend/knowledge-flow-backend}" \
  CONFIG_FILE="$FRED_TEST_CONFIG_DIR/configuration_knowledge-flow-backend.yaml"

make -C apps/fred-agents run PORT=8000 UV="$FRED_TEST_UV" \
  FRED_LOCAL_DELEGATION_FILE="${FRED_LOCAL_DELEGATION_FILE/control-plane-backend/fred-agents}" \
  CONFIG_FILE="$FRED_TEST_CONFIG_DIR/configuration_fred-agents.yaml"

# This Makefile's run-worker recipe hardcodes configuration_worker.yaml.
# Prepare dependencies with make, then select the worker profile explicitly.
make -C apps/control-plane-backend dev UV="$FRED_TEST_UV"
(cd apps/control-plane-backend && \
  ENV_FILE="$FRED_TEST_ROOT/apps/control-plane-backend/config/.env" \
  CONFIG_FILE="$FRED_TEST_CONFIG_DIR/configuration_control-plane-backend.yaml" \
  "$FRED_TEST_UV" run python -m control_plane_backend.main_worker)

make -C apps/knowledge-flow-backend run-worker UV="$FRED_TEST_UV" \
  FRED_LOCAL_DELEGATION_FILE="${FRED_LOCAL_DELEGATION_FILE/control-plane-backend/knowledge-flow-backend}" \
  CONFIG_FILE="$FRED_TEST_CONFIG_DIR/configuration_knowledge-flow-backend.yaml"

VITE_BACKEND_URL=http://localhost:8000 \
VITE_BACKEND_URL_FRED_AGENTS=http://localhost:8000 \
make -C apps/frontend run
```

The frontend obtains its provider settings from the control plane; no separate
frontend OIDC YAML or SPA client secret is needed. Register its redirect/logout
URL `http://localhost:5173/` with the chosen provider. The runtime uses `agentic`,
Knowledge Flow uses `knowledge-flow`, and the control plane uses `control-plane`
as workload clients; their credentials retain the existing environment names.
The workers use the same complete configuration as their corresponding API.

Apply the database migrations before using the local directory. Follow the
factory's `docs/LOCAL-DEVELOPMENT.md` bootstrap/import walkthrough. In
`generic_oidc`, call the factory's `local-testing/scripts/warm-local-directory.sh`
after the API is running and before importing the demo bundle. With the mock,
people must first sign in through the mock page; importing accounts from the
Keycloak demo does not create matching mock identities automatically.

### Immediate checks after startup

1. Check listeners (the default Fred runtime uses **8000**, not 8020):

   ```bash
   ss -ltnp | rg ':(5173|8000|8111|8222)\b'
   ```

   Expect frontend 5173, Fred Agents 8000, Knowledge Flow 8111, Control Plane
   8222. In the baseline catalog, 8020 belongs to the separate `/dt/agents/v2`
   runtime. Do not point `/fred` at that port.
2. Check logs: all three APIs remain alive; Fred Agents reports
   `runtime_startup outcome=completed reason=ready`. Control Plane worker reports
   `Control-plane Temporal worker running`; Knowledge Flow worker reports
   `ready to receive ingestion jobs`. Both workers connect to localhost:7233.
   The Control Plane worker's `Configuration file` must name the selected
   generated YAML, not `configuration_worker.yaml`.
3. Open http://localhost:5173/ in a fresh browser session. Keycloak and generic
   OIDC use accounts in realm **app**, not master; mock OIDC uses its own login
   page. Confirm login completes and reload keeps the session.
4. On a fresh platform, prepare the root administrator secret:

   ```bash
   make -C apps/control-plane-backend bootstrap-token
   cat apps/control-plane-backend/target/bootstrap-token
   ```

   Enter it in Fred's bootstrap screen while logged in as the intended root
   administrator. This is a one-time operation; never paste the secret into
   logs or a shared report.
5. Check the personal space, team list, libraries and an authorized document.
   A new ordinary account may have no team permissions yet. Give it the intended
   membership, then confirm it can access permitted documents and cannot access
   a private document belonging to another account.
6. Run a conversation using an accessible document. With delegation enabled,
   look for `delegated_run_admitted` in Fred Agents and
   `delegation.grant.accepted` in the receiving backend. Record any 401/403 and
   its reason before changing settings.
7. Sign out and sign back in with the second user. Check account separation.
   In generic/mock mode, confirm both authenticated people appear in the local
   user lookup, while service accounts do not.
8. `/evaluation/v1/tasks` returning `ECONNREFUSED` on 8336 means the optional
   evaluator is absent. Missing samples on 8010, RAG runtime on 8013 or DT
   runtime on 8020 likewise require their separate services; these six commands
   do not start them. A conversation assigned to an absent runtime cannot run.

### Functional changes and checks

| Area | Behavior to test |
| --- | --- |
| Login | Both provider settings use the common OIDC adapter and provider login page, Authorization Code + PKCE, API access tokens, session reload, refresh and provider logout. |
| User management | No additional admin page was added. Existing user searches and member/name displays use the selected directory. |
| Local directory | Only people who have authenticated are listed; usernames, email and names are stored in Postgres. Workload identities are excluded. |
| Account creation | Local mode refuses the create API with HTTP 409 and reason `managed_by_identity_provider`; accounts belong to the provider. |
| Account deletion | Local mode suspends the person in Fred without deleting their provider account; root and wildcard protections remain. |
| Platform roles | Granting a role to an unknown local identity returns 404 and writes no authorization relation. |
| Personal space | Browser and backend use the same configured identity claim. Non-UUID subjects become UUIDv5; changing issuer or identity claim changes the Fred ID. |
| Documents and agent tools | Permissions and OpenFGA rules are unchanged. With delegation enabled, the runtime sends its workload bearer and the person/run/agent grant; document access remains limited by the person's permissions. Test both permitted and forbidden documents. |
| Workload accounts | Each backend has its own M2M provider/client/scope configuration; it obtains tokens from the resolved endpoint. |
| Bundle import | Known usernames resolve from the local directory. Unknown entries requiring account creation fail before authorization writes, including entries with a password. |
| Admin self-test | The password/profile probe remains Keycloak-only. The credential-expiry scenario now uses the current session for both Keycloak and OIDC. |
| Startup | An OIDC issuer need not have a `/realms/` path. Discovery failure or inconsistent provider/delegation/directory settings stop startup. |

Verification on 2026-09-28: all nine generated configurations passed their JSON
schemas and the backend provider-configuration checks. The baseline profile has the same configuration values as the canonical
production YAMLs, and the OIDC profiles retain all non-security values. This is
configuration verification; the complete browser and document-access walkthroughs
in tasks 10.2–10.5 remain pending.

### Admin JWT diagnostic

In **Administration → Self-test**, choose **Check JWT authentication (three APIs)**.
The existing step report checks session refresh, representative protected GETs
on Control Plane, Knowledge Flow and Fred Agents, and their rejection of missing,
malformed and signature-altered tokens. Only HTTP 401 passes rejection checks;
a 403, 404 or unavailable service fails. Public Control Plane configuration and
health must work without a bearer. Explicit probes omit cookies and have a
15-second timeout; tokens are never included in report details.

The diagnostic also compares browser/backend user IDs, opens the matching
personal space, and checks that the current person appears in the OIDC local
directory. This samples each API's authentication boundary; it does not enumerate
all endpoints. Run the existing functional document/agent scenario to exercise
delegated calls and document scoping, and the expiration scenario for a real
protected call after the captured session credential expires. Expiration is
available in OIDC mode too, with the existing bounded wait and confirmation.

Account isolation needs a second session; workload JWT claims, wrong issuer or
audience, and crafted delegation grants remain covered by backend tests. These
are explicitly reported as additional coverage, not claimed as a browser pass.

### ZITADEL local profile

`make -C ../fred-deployment-factory zitadel-configure SWIFT_SRC="$PWD"` starts an isolated provider on localhost:8091 and generates configs plus
private service credentials under `/tmp/fred-idp-tests/zitadel/`. Source
`service-credentials.env` in each backend terminal; the frontend uses the
provider settings from Control Plane. See the factory's `docs/LOCAL-DEVELOPMENT.md` for console credentials and
user creation. Stop Fred before switching profiles. Provider identities and
platform bootstrap state follow the same rules as the separate mock; existing
Fred data is preserved. Use a fresh browser session and test CGU, personal space,
JWT rejection, local user lookup and document delegation.

## Agreed follow-up: one OIDC browser flow and pre-CGU profiles

Implemented on 2026-09-29 in
[`add-identity-provider-portability`](../../../openspec/changes/add-identity-provider-portability/tasks.md),
section 11; automated checks pass, browser verification remains pending:

- Use `OidcBrowserSession` for Keycloak and other OIDC providers, preserving
  existing configuration and identity defaults. Keep Keycloak administration
  and directory functions separate from browser authentication.
- With `user_directory: local`, record the human profile on the first
  authenticated control-plane request, including `/user` shown before CGU
  acceptance. Leaving the CGU page must not prevent that profile from appearing.
- Recording a profile does not accept terms or grant access: CGU-protected
  requests remain HTTP 403 until acceptance, including for administrators.
  Service/delegated identities do not create human profiles through this path.

`/user` and `/gcu` use `get_current_user_before_gcu` to snapshot a human profile
without accepting terms. The old `keycloak-js` browser lifecycle and dependency
have been removed. An existing browser session may need a fresh login after
this change because the old adapter used a different token store.

## Platform admission policy

The shared administrator-owned admission policy applies to supported OIDC providers. Provider identity mapping produces the stable Fred user UUID before admission. Bounded verified human facts are internal and excluded from principal serialization and repr/logs. Only active-rule selected values are persisted for delegated admission, which cannot use the workload's attributes. Administrators edit and activate the live SQL rule in the UI; no admission deployment setting or seed is required. Discovery exposes names/types only. The canonical activation and first-party SDK instructions are in [the migration note](../ops/migrations/2965-platform-access-planning.md).
