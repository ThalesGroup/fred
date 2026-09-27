# Identity providers

Fred keeps Keycloak as the default identity provider. A deployment can select an
OIDC issuer in its security configuration. OIDC mode uses the issuer's discovery
document at startup for the JWKS and token endpoint; explicit endpoint overrides
are available. The browser login for a non-Keycloak provider still needs its
frontend adapter validated before this configuration can be used end to end.

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
   delegated permission `api://fred-api/access_as_user`, and use authorization
   code with PKCE. Record its client ID. The browser never receives a client
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
  redirect/logout URLs, and a scope that yields an API access token.
- Inspect a person access token and a client-credentials access token for
  issuer, audience, uid, username, roles, and expiry. Configure claim paths
  against those access tokens, not an ID token.
- Give backend service clients the provider's required scope and role grants.
  Configure delegation's audience and caller-role path from the workload token.
- Select `user_directory: local` and test sign-in, user lookup, personal spaces,
  create refusal, and deletion suspension. People absent from the local table
  cannot be found until they sign in.

## Local configuration examples

Each backend has `config/configuration_generic_oidc.example.yaml` and
`config/configuration_mock_oidc.example.yaml`. These contain only `security`
differences. `CONFIG_FILE` expects a complete configuration, so merge an example
with the application's existing `configuration_prod.yaml` into a temporary file;
do not edit the tracked baseline. For example, from the repository root:

```bash
APP=control-plane-backend PROFILE=generic_oidc \
  apps/control-plane-backend/.venv/bin/python - <<'PY'
import os
from pathlib import Path
import yaml

root = Path('apps') / os.environ['APP'] / 'config'
base = yaml.safe_load((root / 'configuration_prod.yaml').read_text())
overlay = yaml.safe_load((root / f"configuration_{os.environ['PROFILE']}.example.yaml").read_text())

def merge(target, source):
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            merge(target[key], value)
        else:
            target[key] = value

merge(base, overlay)
output = Path('/tmp') / f"fred-{os.environ['APP']}-{os.environ['PROFILE']}.yaml"
output.write_text(yaml.safe_dump(base, sort_keys=False))
print(output)
PY
```

Set `CONFIG_FILE` to the printed path when starting that backend. Repeat with
`APP=knowledge-flow-backend` or `APP=fred-agents`, and set `PROFILE=mock_oidc`
for the mock provider. The examples are only configuration fragments; the mock
provider and frontend login still need their own test-bench setup.
