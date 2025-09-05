# Agentic → Knowledge Flow authentication (Keycloak) — Quick User Guide

This guide shows how the **Agentic backend** authenticates to the **Knowledge Flow** backend using Keycloak. It also clarifies the **three clients** you should create in your realm and what each one is for.

> **Token Exchange Support**: Fred now supports OAuth2 Token Exchange (RFC 8693) to preserve user identity in service-to-service calls. When a user makes a request to Agentic, it can exchange the user's token for a service token that maintains the user's identity when calling Knowledge Flow.

> Today: we validate signature/expiry/issuer. Audience and roles are **not enforced yet** (coming soon).
> Already working: both **agentic** and **knowledge-flow** clients can mint service tokens for protected, service-to-service calls. In particular, **Agentic calls Knowledge Flow**.

---

## Topology & Clients

- **Realm:** e.g. `fred`  
  Example issuer (what the `iss` claim should start with):
    https://auth-<env>.<your-domain>/auth/realms/fred

- **Keycloak clients (create once):**
  1) **agentic** — caller identity for the Agentic backend  
     - Type: confidential  
     - Service accounts: ON  
     - Used by Agentic to mint client-credentials tokens and call Knowledge Flow.

  2) **knowledge-flow** — API identity for the Knowledge Flow backend  
     - Type: confidential  
     - Service accounts: ON (so KF can call other services / itself when needed)  
     - Acts as KF’s own service identity. In the near future, you may also treat this as the **expected audience** for incoming tokens to KF.

  3) **<your-app-frontend>** — end-user application (web / SPA / mobile)  
     - Typically public (SPA + PKCE) or confidential (server-side web app)  
     - Used for user logins. This client is **not** used for Agentic → KF calls.

> Pick a clear name for the frontend client (e.g., `acme-frontend`). Avoid generic names that look like backends.

---

## Environment variables (by component)

### Knowledge Flow (the API being called)

These let KF validate incoming tokens and mint its own when it needs to call out:

    # Validation (incoming)
    KEYCLOAK_SERVER_URL=https://auth-<env>.<your-domain>
    KEYCLOAK_REALM_NAME=fred
    KEYCLOAK_CLIENT_ID=knowledge-flow

    # Optional: stricter validation & leeway (defaults are permissive for smooth rollout)
    FRED_STRICT_ISSUER=false
    FRED_STRICT_AUDIENCE=false
    FRED_JWT_CLOCK_SKEW=0
    FRED_AUTH_VERBOSE=false   # set true temporarily for deep diagnostics

    # Service-to-service (outgoing, only if KF calls other services)
    KEYCLOAK_KNOWLEDGE_FLOW_CLIENT_SECRET=<secret of the 'knowledge-flow' client>

Notes
- We currently allow tokens where `aud` is just "account" (Keycloak default). We log a soft warning.
  When you’re ready to enforce audience:
    1) Add an Audience mapper on the **agentic** client to include `knowledge-flow` in `aud`.
    2) Set `FRED_STRICT_AUDIENCE=true` on Knowledge Flow.
- `FRED_JWT_CLOCK_SKEW` helps tolerate small clock drift.

### Agentic backend (the caller)

    # Mint service tokens to call KF
    KEYCLOAK_SERVER_URL=https://auth-<env>.<your-domain>
    KEYCLOAK_REALM_NAME=fred
    KEYCLOAK_CLIENT_ID=agentic
    KEYCLOAK_AGENTIC_CLIENT_SECRET=<secret of the 'agentic' client>

    # Where to reach KF (public base routed by ingress)
    KNOWLEDGE_FLOW_BASE=https://<public-host>/knowledge-flow/v1

Notes
- Agentic uses client_credentials with the **agentic** client to get a token and call KF.
- You may use a unified public host (ingress routes `/knowledge-flow` to KF). Using KF’s direct host is also fine (and avoids any UI-level rewrites if present).

### Frontend app (end-user) — not used in Agentic → KF calls

    OIDC_ISSUER=https://auth-<env>.<your-domain>/auth/realms/fred
    OIDC_CLIENT_ID=<your-app-frontend>
    OIDC_REDIRECT_URI=https://<public-host>/callback
    OIDC_POST_LOGOUT_REDIRECT_URI=https://<public-host>/

---

## Server mounts & transports (MCP over HTTP)

In Knowledge Flow (illustrative):

    mcp_prefix = "/knowledge-flow/v1"

    # Exposes HTTP (streamable_http)
    mcp_opensearch_ops = FastApiMCP(
        app,
        name="Knowledge Flow OpenSearch Ops MCP",
        include_tags=["OpenSearch"],
        auth_config=AuthConfig(dependencies=[Depends(get_current_user)]),
    )
    mcp_opensearch_ops.mount_http(mount_path=f"{mcp_prefix}/mcp-opensearch-ops")

    # Optionally also expose SSE if you intend to use that transport:
    # mcp_opensearch_ops.mount_sse(mount_path=f"{mcp_prefix}/mcp-opensearch-ops-sse")

Transport rules (client side)
- streamable_http → use base URL **with** trailing "/"  
  Example: …/mcp-opensearch-ops/  
  Required headers:
    MCP-Version: 2025-03-26
    Accept: application/json
    Authorization: Bearer <token>
- sse / websocket → use base URL **without** trailing "/" unless you mounted a dedicated path.
- Avoid redirects (they can strip Authorization across hosts). Always call the canonical path for the chosen transport.

---

## Verifying Agentic → KF end-to-end

1) Mint a service token as **agentic**:

    KC="https://auth-<env>.<your-domain>/auth/realms/fred/protocol/openid-connect/token"
    TOKEN=$(curl -s -X POST "$KC" \
      -d grant_type=client_credentials \
      -d client_id=agentic \
      -d client_secret='<AGENTIC_SECRET>' | jq -r .access_token)

2) Call the MCP base (streamable_http):

    BASE="https://<public-host>/knowledge-flow/v1/mcp-opensearch-ops/"
    curl -v \
      -H "Authorization: Bearer $TOKEN" \
      -H "MCP-Version: 2025-03-26" \
      -H "Accept: application/json" \
      "$BASE"

Expected: HTTP 200 with a JSON description. In KF logs you should see:
    Processing request of type ListToolsRequest

---

## Token Exchange Configuration

Token Exchange allows Agentic to preserve user identity when making calls to Knowledge Flow. This is especially useful for resource creation where you want the correct author field instead of "service-account-agentic".

### Keycloak Setup for Token Exchange

1. **Enable Token Exchange on agentic client:**
   - Go to Keycloak Admin Console → Clients → agentic
   - Go to Capability config → enable Standard Token Exchange

2. **Verification:**
   ```bash
   # Test token exchange manually
   USER_TOKEN="<user_access_token>"
   AGENTIC_SECRET="<your_agentic_client_secret>"
   
   curl -X POST "https://your-keycloak/realms/fred/protocol/openid-connect/token" \
     -d "grant_type=urn:ietf:params:oauth:grant-type:token-exchange" \
     -d "client_id=agentic" \
     -d "client_secret=$AGENTIC_SECRET" \
     -d "subject_token=$USER_TOKEN" \
     -d "subject_token_type=urn:ietf:params:oauth:token-type:access_token" \
     -d "requested_token_type=urn:ietf:params:oauth:token-type:access_token" \
     -d "audience=knowledge-flow"
   ```

### How It Works

1. User alice logs in via frontend and gets a JWT token
2. Frontend sends request to Agentic with alice's token
3. Agentic extracts alice's token and stores it in RuntimeContext
4. When making MCP calls, Agentic exchanges alice's token for a service token that preserves her identity
5. Knowledge Flow receives the exchanged token and sees alice as the author (not service-account-agentic)

---

## Common failure patterns

- 307 → 401 on first call  
  Wrong slash form or an ingress cross-host redirect.  
  Fix: Use the canonical base (see transport rules) and keep scheme/host identical on redirects (or disable them).

- 400 Bad Request on base  
  Missing MCP headers or wrong base URL join.  
  Fix: For streamable_http, ensure the base ends with "/" and include MCP-Version + Accept.

- 401 after idle  
  Token expired.  
  Fix: Refresh and retry; confirm the issuer in the token exactly matches your realm URL (including `/auth/realms/<realm>`). Consider a small `FRED_JWT_CLOCK_SKEW`.

---

## Audience & roles — today vs. near future

Today
- We verify signature/expiry/issuer.
- `aud` and roles are not enforced; we log soft warnings (e.g., `aud=['account']`).

Soon (recommended hardening)
1) Audience enforcement
   - Add Audience mapper on **agentic** to include `knowledge-flow` in `aud`.
   - Set `FRED_STRICT_AUDIENCE=true` on KF.

2) Role-based access control
   - Add client role mapper on the **knowledge-flow** client (e.g., `admin`, `editor`, `viewer`).
   - Your API reads roles from: `resource_access['knowledge-flow'].roles`.
   - In FastAPI dependencies, require appropriate roles per route.

3) Issuer strictness (optional)
   - If you run multiple Keycloak hosts, keep `FRED_STRICT_ISSUER=false` until DNS/ingress are consistent; then flip to `true`.

---

## Operational logging in KF (what you’ll see)

With `FRED_AUTH_VERBOSE=true`:
- JWT peek: kid=…, iss=…, aud=…, azp=…, exp=…
- JWKS resolved key in … ms
- JWT decoded (safe): sub=…, preferred_username=…, roles=[…]
- On MCP base call: Processing request of type ListToolsRequest → 200 OK

Turn verbosity off after diagnosing.

---

## FAQ

**Why three clients?**  
Separate concerns: Agentic (caller service), Knowledge Flow (API/service identity), and your frontend app (user login). This keeps scopes/roles clean and audit clear.

**Why allow aud='account' initially?**  
It’s Keycloak’s default for service tokens. We keep rollout smooth, then enforce once mappers are in place.

**Can I call KF via the UI host?**  
Yes if ingress routes `/knowledge-flow` to KF. Prefer KF’s direct host if you ever see cross-host redirects that drop Authorization.
