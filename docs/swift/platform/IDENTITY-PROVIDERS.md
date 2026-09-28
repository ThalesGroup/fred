# Identity providers

Fred keeps Keycloak as the default identity provider. A deployment can select an
OIDC issuer in its security configuration. OIDC mode uses the issuer's discovery
document at startup for the JWKS and token endpoint; explicit endpoint overrides
are available. In the browser, Keycloak uses `keycloak-js` and other OIDC
providers use `oidc-client-ts` behind the same authentication service. A new
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
`managed_by_identity_provider`, while deletion suspends the person in Fred.
A non-UUID OIDC uid maps to UUIDv5 using the normalized issuer and claim value;
changing either changes the Fred user ID and personal space. Server-side
refresh of a person's token depends on the provider. For Entra SPA tokens,
enable workload delegation rather than relying on backend person-token refresh.

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
6. Set `FRED_JWT_MAX_LIFETIME_SECONDS=5400` for the backends that validate
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

## Complete local test configurations

The existing `configuration_generic_oidc.example.yaml` and
`configuration_mock_oidc.example.yaml` files are security overlays. Prepare full
configurations for all three backends with the repository script, from the root:

```bash
/usr/bin/python3 scripts/prepare_identity_provider_configs.py
```

This command worked with the system Python on this checkout. On another machine,
use `uv run scripts/prepare_identity_provider_configs.py` to resolve its declared
`pyyaml` and `jsonschema` dependencies. `--profile mock_oidc` selects one profile;
`--output-dir <directory>` changes the output location. Every file is checked
against its application's committed JSON schema before that profile is written.
The script preserves non-security settings and never reads `.env` files.

| Profile | Generated directory | Identity setup |
| --- | --- | --- |
| `keycloak` | `/tmp/fred-idp-tests/keycloak` | Existing Keycloak configuration and directory, unchanged |
| `generic_oidc` | `/tmp/fred-idp-tests/generic_oidc` | Keycloak on port 8080 with the factory generic profile; local directory |
| `mock_oidc` | `/tmp/fred-idp-tests/mock_oidc` | Factory mock issuer on port 8090; local directory and non-UUID subjects |

Each directory contains `configuration_control-plane-backend.yaml`,
`configuration_knowledge-flow-backend.yaml`, and `configuration_fred-agents.yaml`.
These are complete local configurations selected directly with `CONFIG_FILE`.
They retain the baseline Postgres, OpenFGA, Temporal, storage and model settings;
those services and the normal application `.env` credentials must be available.
Regenerate the files after changing a baseline configuration. These localhost
URLs are for applications running on the host, not inside Kubernetes pods.
For Kubernetes with Entra, use
[`values-entra.example.yaml`](../../../deploy/charts/fred/values-entra.example.yaml)
and replace the tenant/application IDs with the customer's registrations.

### Select the identity setup

From the Fred root, with the sibling factory checkout:

```bash
# generic_oidc: change the local realm to flat roles and a fred-api audience.
make -C ../fred-deployment-factory keycloak-generic-oidc STRICT=1

# mock_oidc: start the separate provider instead.
make -C ../fred-deployment-factory mock-oidc-up

# Restore the Keycloak token shape when returning to the keycloak profile.
make -C ../fred-deployment-factory keycloak-generic-oidc-revert
```

Run the command matching the chosen profile. The mock provider is a local test
server with an interactive login page, not a production identity provider.

### Launch Fred

Set these variables in each terminal, from the Fred root:

```bash
export FRED_TEST_ROOT="$PWD"
export FRED_TEST_PROFILE=mock_oidc # or generic_oidc / keycloak
export FRED_TEST_CONFIG_DIR="/tmp/fred-idp-tests/$FRED_TEST_PROFILE"
export FRED_TEST_UV="$FRED_TEST_ROOT/apps/control-plane-backend/.venv/bin/uv"
# OIDC profiles: allow the mock lifetime and ignore a stale Keycloak policy.
if [ "$FRED_TEST_PROFILE" != keycloak ]; then
  export FRED_JWT_MAX_LIFETIME_SECONDS=5400
  export FRED_LOCAL_DELEGATION_FILE=
fi
```

For the Keycloak baseline, use fresh terminals with the usual environment,
without the OIDC overrides above. Start each process in a separate terminal
using the same profile:

```bash
make -C apps/control-plane-backend run UV="$FRED_TEST_UV" \
  CONFIG_FILE="$FRED_TEST_CONFIG_DIR/configuration_control-plane-backend.yaml"

make -C apps/knowledge-flow-backend run UV="$FRED_TEST_UV" \
  CONFIG_FILE="$FRED_TEST_CONFIG_DIR/configuration_knowledge-flow-backend.yaml"

make -C apps/fred-agents run UV="$FRED_TEST_UV" \
  CONFIG_FILE="$FRED_TEST_CONFIG_DIR/configuration_fred-agents.yaml"

make -C apps/control-plane-backend run-worker UV="$FRED_TEST_UV" \
  CONFIG_FILE="$FRED_TEST_CONFIG_DIR/configuration_control-plane-backend.yaml"

make -C apps/knowledge-flow-backend run-worker UV="$FRED_TEST_UV" \
  CONFIG_FILE="$FRED_TEST_CONFIG_DIR/configuration_knowledge-flow-backend.yaml"

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

### Functional changes and checks

| Area | Behavior to test |
| --- | --- |
| Login | `keycloak` retains its existing adapter; `oidc` uses the provider login page, Authorization Code + PKCE, API access tokens, session reload, refresh and provider logout. |
| User management | No additional admin page was added. Existing user searches and member/name displays use the selected directory. |
| Local directory | Only people who have authenticated are listed; usernames, email and names are stored in Postgres. Workload identities are excluded. |
| Account creation | Local mode refuses the create API with HTTP 409 and reason `managed_by_identity_provider`; accounts belong to the provider. |
| Account deletion | Local mode suspends the person in Fred without deleting their provider account; root and wildcard protections remain. |
| Platform roles | Granting a role to an unknown local identity returns 404 and writes no authorization relation. |
| Personal space | Browser and backend use the same configured identity claim. Non-UUID subjects become UUIDv5; changing issuer or identity claim changes the Fred ID. |
| Documents and agent tools | Permissions and OpenFGA rules are unchanged. With delegation enabled, the runtime sends its workload bearer and the person/run/agent grant; document access remains limited by the person's permissions. Test both permitted and forbidden documents. |
| Workload accounts | Each backend has its own M2M provider/client/scope configuration; it obtains tokens from the resolved endpoint. |
| Bundle import | Known usernames resolve from the local directory. Unknown entries requiring account creation fail before authorization writes, including entries with a password. |
| Admin self-test | The Keycloak password/profile probe and credential-expiry scenario are unavailable in OIDC mode. |
| Startup | An OIDC issuer need not have a `/realms/` path. Discovery failure or inconsistent provider/delegation/directory settings stop startup. |

Verification on 2026-09-28: all nine generated configurations passed their JSON
schemas and the backend provider-configuration checks. The baseline profile has the same configuration values as the canonical
production YAMLs, and the OIDC profiles retain all non-security values. This is
configuration verification; the complete browser and document-access walkthroughs
in tasks 10.2–10.5 remain pending.
