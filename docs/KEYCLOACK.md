# Agentic → Knowledge Flow authentication (Keycloak) — Quick User Guide

Use this guide to verify that **every instance** (dev, staging, prod) can reuse the same Keycloak clients to let the **Agentic backend** call the **Knowledge Flow** backend securely.

• Keycloak realm: app (URL: http://app-keycloak:8080/realms/app)  
• Shared clients (already created by platform admins):
  – agentic — caller (confidential, service account ON)  
  – knowledge-flow — API audience (confidential, service account OFF)  
• Your web UI continues to use its usual app client. Nothing to change there.

---

## What you need before testing

1) Access to the Keycloak realm app (you don’t need admin rights to run the test).  
2) The client secret for agentic (ask your admin if you don’t have it).  
3) The Knowledge Flow base URL (example below uses http://localhost:8111/knowledge-flow/v1).  
4) curl and jq installed.

Note: You do not need to download any keys from “knowledge-flow”. Keys (JWKS) are per realm.

---

## Quick test (copy/paste these three shell commands)

1) Mint a short-lived service token for the agentic client

   export KEYCLOACK_AGENTIC_TOKEN="<the-agentic-client-secret>"

   TOKEN=$(curl -s -X POST \
     "http://app-keycloak:8080/realms/app/protocol/openid-connect/token" \
     -d "grant_type=client_credentials" \
     -d "client_id=agentic" \
     -d "client_secret=${KEYCLOACK_AGENTIC_TOKEN}" | jq -r .access_token)

2) Sanity check that a token was returned (shows the first 20 characters)

   echo "${TOKEN:0:20}..."

3) Call Knowledge Flow with the bearer (replace the URL if your instance differs)

   curl -i \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"query":"what is punchplatform","top_k":3}' \
     http://localhost:8111/knowledge-flow/v1/vector/search

Expected results:
• Without the Authorization header → 401 Unauthorized  
• With the header above → 200 OK (the body may be an empty list if nothing matches yet)

---

## If something fails

• 401 even with a bearer: the Knowledge Flow service may not be configured to use the app realm, or its container can’t reach Keycloak’s JWKS.  
• invalid_client while minting the token: the agentic client’s secret is wrong, or “Client authentication”/“Service accounts” are not enabled for agentic.  
• Connectivity issues: ensure the Knowledge Flow URL you’re calling is reachable from where you run curl.

That’s all: once the 200 OK response appears with the bearer, the secure Agentic → Knowledge Flow connection is working for this instance using the shared agentic and knowledge-flow clients.
